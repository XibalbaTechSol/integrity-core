"""Durable, signed, chained decision receipts for a gate process (integrity-core B2).

The receipt *format* -- signing domain, hash chain, checkpoint, Merkle root, offline verification -- is
`core.receipts` (SDK contract C4), shared by every gate and by `integrity-cli`'s independent verifier.
This module is the *emitting side* that contract deliberately leaves to each gate: a writer that is safe
under concurrent requests, survives a crash, refuses to continue a log it cannot verify, bounds its memory
by rotating into epochs, and says plainly when a decision could not be recorded. It was written for
Xibalba Shield's gate daemon (xibalba-shield `shield/gate_receipts.py`) and moved here so that
`bcc_middleware` does not get a second copy of the hardest-to-get-right 300 lines in the repository.

Layout on disk
--------------
Two JSON Lines files per log, both created ``0600`` inside a ``0700`` directory:

``receipts.jsonl``
    One signed receipt per line, in `seq` order. A line is written and ``fsync``-ed *before* the caller is
    told the receipt exists, so a receipt a client was told about is on disk.
``checkpoints.jsonl``
    One signed checkpoint per line. A checkpoint commits to the Merkle root over the first `tree_size`
    receipts; holding one (or an anchored copy, B4) is what lets a verifier detect *tail truncation*, which
    a bare hash chain cannot show.

Without `rotation` the two files sit directly in the directory and the log runs forever (Shield's layout).
With a `RotationPolicy` the directory holds numbered **epochs**, ``epoch-000001/``, ``epoch-000002/``, ...,
each its own log with its own `log_id` (``<base>.e000001``) and a fresh chain from ``seq`` 0. An epoch is
closed -- with a final checkpoint covering every receipt in it -- when it reaches `max_receipts` or
`max_age_seconds`, and the next opens. See "Epochs" below.

Failure posture (stated per module, as this repository requires)
----------------------------------------------------------------
* **Starting up fails closed.** A log that does not verify end to end with the configured key -- a bad
  signature, a gap, a broken link, a missing tail after a checkpoint, a different log id, a rotated key, a
  missing epoch in the middle -- raises `ReceiptSetupError`; the process must not start with it. Silently
  continuing, or starting a fresh log beside the old one, would erase exactly the evidence the log exists to
  preserve. There is no auto-repair of a log that fails verification.
* **One narrow, deliberate exception: a torn final line.** A crash mid-write leaves a last line with no
  trailing newline. Callers are answered only *after* the newline and ``fsync``, so that record was never
  acknowledged to anyone; it is discarded with a warning and the file truncated to the last complete line.
  Anything else wrong with a line is corruption.
* **Recording fails loudly, and does not advance the chain.** If a receipt cannot be written (disk full, I/O
  error) `record` raises `ReceiptWriteError` and the in-memory chain is *not* advanced, so the next success is
  still contiguous. Whether the *decision* then stands (strict or lenient) is the caller's policy; this
  module never decides policy. A write that fails part-way is rolled back by truncating the file to its prior
  length; if even that fails the writer marks itself broken and refuses all further records rather than
  append after unknown bytes.
* **A new file's directory entry is ``fsync``-ed too.** Syncing a file does not make its *name* durable; after
  a crash the first receipt of a new log could otherwise be acknowledged and then simply not exist.

Epochs (bounding memory and checkpoint cost)
--------------------------------------------
`core.receipts.ReceiptLog` holds every receipt of a log in memory and recomputes the Merkle root over all of
them at each checkpoint, so one eternal log grows without bound. Rotation caps both at one epoch. It needs
**no change to the receipt format or to any verifier**: each epoch is an ordinary log. What it costs, stated:

* Nothing in the files links epoch *N* to epoch *N+1*. At start-up the numbering must be contiguous, so
  deleting an epoch from the *middle* is refused, but deleting the *newest* epoch(s), or the whole
  directory, cannot be detected from the files. Anchoring each closed epoch's final checkpoint (B4) is what
  closes that, and is `[PLANNED]` for gates.
* Only the newest epoch is verified at start-up (verifying all of them is O(total) and a restart should not
  scale with history). `verify_epoch_directory` does the full audit offline.

Other known limits
------------------
* Deleting `checkpoints.jsonl`, or truncating *both* files of a log consistently, cannot be detected from the
  files alone (same remedy: anchoring).
* Rotating the signing key starts a new log: `ReceiptLog.resume` trusts only the configured key, so an old log
  fails with UNTRUSTED_SIGNER. That is refusal, not silent re-signing.
* Same-uid processes can read and append to these files like any other file of the user; the signature, not the
  file mode, is what makes a receipt authentic.

Privacy
-------
A receipt carries the agent's DID, the event class, the decision, a reason code and control ids. The gate/device
and the action are HMAC-SHA256 values under an organization-held key (`hmac_identifier`), so what they name never
appears in the file in the clear; the caller passes the *strings to hash*, never the hash. Content never reaches
this module.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Collection, Mapping, Optional, Sequence

from ..did import Keypair
from .receipts import ReceiptError, ReceiptLog, hmac_identifier, receipt_hash, verify_log

logger = logging.getLogger(__name__)

RECEIPTS_FILENAME = "receipts.jsonl"
CHECKPOINTS_FILENAME = "checkpoints.jsonl"

#: Receipts between automatic checkpoints. A clean close always writes a final one.
DEFAULT_CHECKPOINT_EVERY = 100

#: `hmac_identifier` refuses shorter keys; checked here too so the operator gets a sentence naming the file
#: rather than a bare ValueError from deep in the SDK.
MIN_HMAC_KEY_BYTES = 32

_EPOCH_DIR_RE = re.compile(r"^epoch-(\d{6})$")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class ReceiptSetupError(Exception):
    """The receipt log or its keys cannot be used; the process must not start with them."""


class ReceiptWriteError(Exception):
    """One decision could not be recorded. The chain was not advanced."""


@dataclass(frozen=True)
class ReceiptRef:
    """What a gate tells its caller about a recorded receipt."""

    seq: int
    hash: str
    #: The log (epoch) the receipt is in. `seq` alone is ambiguous once logs rotate.
    log_id: str = ""


@dataclass(frozen=True)
class RotationPolicy:
    """When to close an epoch. At least one bound is required; the first reached wins."""

    max_receipts: Optional[int] = None
    max_age_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.max_receipts is None and self.max_age_seconds is None:
            raise ValueError("a RotationPolicy needs max_receipts, max_age_seconds, or both")
        if self.max_receipts is not None and self.max_receipts < 1:
            raise ValueError("max_receipts must be at least 1")
        if self.max_age_seconds is not None and self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")


def derive_log_id(prefix: str, hmac_key: bytes, gate_id: str) -> str:
    """A stable log id for one gate that does not contain the gate id.

    `log_id` is written into every receipt in the clear, so deriving it as ``f"...:{gate_id}"`` would put the
    raw id in the file the HMAC identifiers exist to keep it out of -- which Shield's first version did, and
    only a live run against the real file showed. The id is the first 16 hex digits of the same HMAC the
    receipts use for the gate, so it is stable for a gate and key, differs between gates, and reveals nothing
    without the key. Rotating the HMAC key therefore starts a new log, which the writer refuses to mix with the
    old one -- the same outcome as rotating the signing key.
    """
    return f"{prefix}:" + hmac_identifier(hmac_key, "device", gate_id).removeprefix("hmac-sha256:")[:16]


def _require_private(path: Path, what: str) -> None:
    """Refuse a secret that other local users can read."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise ReceiptSetupError(f"cannot read {what} {path}: {exc}") from exc
    if mode & 0o077:
        raise ReceiptSetupError(f"{what} {path} is accessible to other users (mode {mode:04o}); run `chmod 600 {path}`")


def load_hmac_key(path: str | os.PathLike[str]) -> bytes:
    """Read the organization-held HMAC key: raw bytes, at least `MIN_HMAC_KEY_BYTES`, mode 0600.

    Used byte for byte, with no stripping or decoding, so `head -c 32 /dev/urandom` and
    `openssl rand -hex 32` both work and mean the same thing every time.
    """
    key_path = Path(path)
    _require_private(key_path, "receipt HMAC key")
    key = key_path.read_bytes()
    if len(key) < MIN_HMAC_KEY_BYTES:
        raise ReceiptSetupError(f"receipt HMAC key {key_path} is {len(key)} bytes; at least {MIN_HMAC_KEY_BYTES} are required")
    return key


def load_signer(path: str | os.PathLike[str]) -> Keypair:
    """Read the Ed25519 receipt-signing key (PEM) without ever creating one.

    Deliberately read-only: a helper that mints a replacement key when it cannot read the old one destroys an
    identity.
    """
    key_path = Path(path)
    _require_private(key_path, "receipt signing key")
    try:
        return Keypair.from_pem(key_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ReceiptSetupError(f"receipt signing key {key_path} is not a readable Ed25519 PEM: {exc}") from exc


def _fsync_directory(directory: Path) -> None:
    """Make the directory's entries (new file names) durable. Best effort: not every platform allows it."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _read_jsonl(path: Path, what: str) -> list[dict[str, Any]]:
    """Parse a JSON Lines file, discarding (and truncating away) one torn final line.

    Only a final line with no trailing newline is treated as a crash artifact. A complete line that is not a
    JSON object is corruption and refuses start-up.
    """
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        keep = data.rfind(b"\n") + 1
        logger.warning("%s %s ended in an incomplete line (%d bytes, never acknowledged); discarding it", what, path, len(data) - keep)
        with path.open("r+b") as handle:
            handle.truncate(keep)
        data = data[:keep]
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(data.split(b"\n")[:-1], start=1):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReceiptSetupError(f"{what} {path} line {number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ReceiptSetupError(f"{what} {path} line {number} is not a JSON object")
        rows.append(row)
    return rows


def _epoch_numbers(directory: Path) -> list[int]:
    return sorted(int(m.group(1)) for entry in directory.iterdir() if (m := _EPOCH_DIR_RE.match(entry.name)) and entry.is_dir())


def epoch_log_id(base_log_id: str, number: int) -> str:
    return f"{base_log_id}.e{number:06d}"


def _parse_timestamp(value: str) -> float:
    return float(calendar.timegm(time.strptime(value, _TIMESTAMP_FORMAT)))


class _Log:
    """One chain on disk: its two files, the in-memory `ReceiptLog`, and the durable-append machinery.

    Not thread-safe by itself; `GateReceiptWriter` holds the lock.
    """

    def __init__(self, directory: Path, *, signer: Keypair, log_id: str, checkpoint_every: int, clock: Callable[[], float]) -> None:
        self.directory = directory
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.checkpoint_every = checkpoint_every
        self.broken = False
        receipts_path, checkpoints_path = directory / RECEIPTS_FILENAME, directory / CHECKPOINTS_FILENAME
        existed = receipts_path.exists() and checkpoints_path.exists()

        receipts = _read_jsonl(receipts_path, "receipt log")
        checkpoints = _read_jsonl(checkpoints_path, "checkpoint log")
        # `ReceiptLog.resume` verifies against whatever log id the receipts carry; it does not compare it
        # with the one configured. Without this, a process configured for one gate would resume, and happily
        # extend, another gate's log.
        for row in (*receipts, *checkpoints):
            if row.get("log_id") != log_id:
                raise ReceiptSetupError(
                    f"{directory} holds log {row.get('log_id')!r}, but this process is configured for log {log_id!r}; "
                    "use a different receipt directory"
                )
        try:
            self.log = ReceiptLog.resume(signer, log_id, receipts, checkpoints)
        except ReceiptError as exc:
            raise ReceiptSetupError(
                f"the existing receipt log in {directory} does not verify with the configured key ({exc}); "
                "refusing to extend it. Move it aside deliberately if it should be retired."
            ) from exc

        self.since_checkpoint = len(receipts) - (checkpoints[-1]["tree_size"] if checkpoints else 0)
        self.receipts_fd = os.open(receipts_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        self.checkpoints_fd = os.open(checkpoints_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        if not existed:
            _fsync_directory(directory)
        self.receipts_size = os.fstat(self.receipts_fd).st_size
        self.checkpoints_size = os.fstat(self.checkpoints_fd).st_size
        # An epoch's age runs from its first receipt (so a restart does not reset it); an empty one from now.
        self.opened_at = _parse_timestamp(receipts[0]["timestamp"]) if receipts else clock()

    # ---------------------------------------------------------------------------- state

    @property
    def count(self) -> int:
        return len(self.log.receipts)

    def append_durably(self, fd: int, size: int, document: Mapping[str, Any]) -> int:
        """Write one line and fsync it; on failure restore the file to `size` and re-raise.

        If the rollback itself fails the log is marked broken, because appending after unknown bytes would
        corrupt it silently.
        """
        line = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            view = memoryview(line)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        except OSError:
            try:
                os.ftruncate(fd, size)
            except OSError:
                self.broken = True
                logger.critical("receipt log could not be rolled back after a failed write; writer disabled")
            raise
        return size + len(line)

    def append(self, **fields: Any) -> dict[str, Any]:
        try:
            receipt = self.log.append(**fields)
        except (ReceiptError, ValueError) as exc:
            raise ReceiptWriteError(f"receipt rejected by the SDK: {exc}") from exc
        try:
            self.receipts_size = self.append_durably(self.receipts_fd, self.receipts_size, receipt)
        except OSError as exc:
            # The SDK appended in memory first. Undo that, or the next receipt would chain to one that is
            # not on disk and the log would fail its own verification.
            self.log.receipts.pop()
            raise ReceiptWriteError(f"could not write the receipt: {exc}") from exc
        self.since_checkpoint += 1
        return receipt

    def checkpoint(self) -> dict[str, Any]:
        try:
            checkpoint = self.log.checkpoint()
        except ValueError as exc:  # an empty log
            raise ReceiptWriteError(str(exc)) from exc
        try:
            self.checkpoints_size = self.append_durably(self.checkpoints_fd, self.checkpoints_size, checkpoint)
        except OSError as exc:
            self.log.checkpoints.pop()
            raise ReceiptWriteError(f"could not write the checkpoint: {exc}") from exc
        self.since_checkpoint = 0
        return checkpoint

    def close(self) -> None:
        for fd in (self.receipts_fd, self.checkpoints_fd):
            try:
                os.close(fd)
            except OSError:
                pass


class GateReceiptWriter:
    """Append-only, thread-safe receipt log for one gate process.

    One lock covers "build receipt, write it, advance the chain": two concurrent requests that both read the
    same head would otherwise sign two receipts with one `seq` and one `prev_hash`, forking the chain.
    """

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        signer: Keypair,
        hmac_key: bytes,
        log_id: str,
        checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
        rotation: Optional[RotationPolicy] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(hmac_key) < MIN_HMAC_KEY_BYTES:
            raise ReceiptSetupError(f"receipt HMAC key must be at least {MIN_HMAC_KEY_BYTES} bytes")
        if checkpoint_every < 1:
            raise ReceiptSetupError("checkpoint_every must be at least 1")
        self._signer = signer
        self._hmac_key = hmac_key
        self._checkpoint_every = checkpoint_every
        self._rotation = rotation
        self._clock = clock
        self._base_log_id = log_id
        self._lock = threading.Lock()
        self._closed = False
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

        if rotation is None:
            self._epoch_number: Optional[int] = None
            self._current = self._open(self.directory, log_id)
        else:
            self._epoch_number = self._latest_epoch_number()
            self._current = self._open(self._epoch_dir(self._epoch_number), epoch_log_id(log_id, self._epoch_number))

    # ----------------------------------------------------------------------- opening

    def _open(self, directory: Path, log_id: str) -> _Log:
        return _Log(directory, signer=self._signer, log_id=log_id, checkpoint_every=self._checkpoint_every, clock=self._clock)

    def _epoch_dir(self, number: int) -> Path:
        return self.directory / f"epoch-{number:06d}"

    def _latest_epoch_number(self) -> int:
        """The newest epoch to resume, after checking the numbering has no hole. 1 when the directory is empty."""
        numbers = _epoch_numbers(self.directory)
        if not numbers:
            return 1
        if numbers != list(range(1, numbers[-1] + 1)):
            missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
            raise ReceiptSetupError(
                f"{self.directory} is missing epoch(s) {missing} in the middle of its history; refusing to start. "
                "Restore them, or move the whole directory aside deliberately."
            )
        return numbers[-1]

    # ----------------------------------------------------------------- introspection

    @property
    def signer_key(self) -> str:
        """The multibase public key a verifier must trust (`integrity verify --trusted-signer`)."""
        return self._current.log.signer_key

    @property
    def log_id(self) -> str:
        """The current log's id (the current epoch's, when rotating)."""
        return self._current.log.log_id

    @property
    def epoch(self) -> Optional[int]:
        return self._epoch_number

    @property
    def receipt_count(self) -> int:
        """Receipts in the current log (the current epoch's, when rotating)."""
        with self._lock:
            return self._current.count

    # ---------------------------------------------------------------------- rotation

    def _epoch_is_full(self) -> bool:
        policy = self._rotation
        if policy is None:
            return False
        if policy.max_receipts is not None and self._current.count >= policy.max_receipts:
            return True
        return policy.max_age_seconds is not None and self._current.count > 0 and (
            self._clock() - self._current.opened_at >= policy.max_age_seconds
        )

    def _rotate_locked(self) -> None:
        """Close the current epoch (final checkpoint first) and open the next.

        The next epoch is created BEFORE the old one is closed, so a failure to create it leaves the old
        epoch open and the writer in a consistent state; the record that triggered the rotation fails, and the
        next one tries again.
        """
        assert self._rotation is not None and self._epoch_number is not None
        old = self._current
        if old.since_checkpoint > 0:
            old.checkpoint()  # ReceiptWriteError propagates: an epoch is never closed without covering its tail
        number = self._epoch_number + 1
        try:
            fresh = self._open(self._epoch_dir(number), epoch_log_id(self._base_log_id, number))
        except (OSError, ReceiptSetupError) as exc:
            raise ReceiptWriteError(f"could not open epoch {number}: {exc}") from exc
        _fsync_directory(self.directory)
        old.close()
        self._current, self._epoch_number = fresh, number
        logger.info("receipt epoch %d closed (%d receipts); epoch %d opened", number - 1, old.count, number)

    # ----------------------------------------------------------------------- writing

    def record(
        self,
        *,
        agent_did: str,
        device_id: str,
        action: str,
        event_class: str,
        pack_hash: str,
        decision: str,
        reason_code: str,
        mode: str,
        controls: Sequence[str] = (),
        timestamp: Optional[str] = None,
    ) -> ReceiptRef:
        """Sign, persist and return a receipt for one decision, or raise `ReceiptWriteError`.

        `device_id` (the gate or device) and `action` are the *strings to hash*; they are hashed here under the
        organization key, so a caller cannot forget to. The action string should bind what was decided about
        (e.g. a tool name and an input digest, or an intent type and a state hash): it then identifies this
        exact call to someone holding the key and the original, and nothing to anyone else. `timestamp` is for
        deterministic tests and replays; production callers omit it.
        """
        device_hmac = hmac_identifier(self._hmac_key, "device", device_id)
        action_hmac = hmac_identifier(self._hmac_key, "action", action)
        with self._lock:
            if self._closed:
                raise ReceiptWriteError("the receipt writer is closed")
            if self._current.broken:
                raise ReceiptWriteError("the receipt writer is disabled after an unrecoverable write failure")
            if self._epoch_is_full():
                self._rotate_locked()
            current = self._current
            receipt = current.append(
                agent_did=agent_did, device_id_hmac=device_hmac, action_hmac=action_hmac, event_class=event_class,
                pack_hash=pack_hash, decision=decision, reason_code=reason_code, mode=mode, controls=controls,
                timestamp=timestamp,
            )
            if current.since_checkpoint >= self._checkpoint_every:
                try:
                    current.checkpoint()
                except ReceiptWriteError as exc:
                    # The receipt is already durable; failing it now would report a recorded decision as
                    # unrecorded. The next record retries the checkpoint.
                    logger.error("periodic checkpoint failed: %s", exc)
            return ReceiptRef(seq=receipt["seq"], hash=receipt_hash(receipt), log_id=current.log.log_id)

    def checkpoint(self) -> dict[str, Any]:
        """Sign and persist a checkpoint over every receipt in the current log (the value B4 anchors)."""
        with self._lock:
            if self._closed or self._current.broken:
                raise ReceiptWriteError("the receipt writer is not accepting writes")
            return self._current.checkpoint()

    def close(self) -> None:
        """Write a final checkpoint if receipts arrived since the last one, then release the files."""
        with self._lock:
            if self._closed:
                return
            if self._current.since_checkpoint > 0 and not self._current.broken:
                try:
                    self._current.checkpoint()
                except ReceiptWriteError as exc:
                    logger.error("final checkpoint failed: %s", exc)
            self._closed = True
            self._current.close()


# ------------------------------------------------------------------- offline audit of an epoch directory


@dataclass(frozen=True)
class EpochAudit:
    number: int
    log_id: str
    receipts: int
    closed: bool  # True when its newest checkpoint covers every receipt


def verify_epoch_directory(directory: str | os.PathLike[str], *, base_log_id: str, trusted_signers: Collection[str]) -> list[EpochAudit]:
    """Fully verify every epoch under `directory` with the SDK's own `verify_log`. Raises `ReceiptError`/`ReceiptSetupError`.

    This is the O(total) audit the writer's start-up deliberately does not do. It checks, for each epoch: the
    numbering is contiguous from 1; every receipt and checkpoint carries that epoch's log id; the whole chain and
    its newest checkpoint verify; and every epoch except the newest is *closed*, i.e. its newest checkpoint covers
    all of its receipts (an epoch closed without covering its tail is an epoch whose tail could be cut unseen).
    It cannot tell that the newest epoch(s), or the whole directory, were removed: that needs anchoring (B4).
    """
    root = Path(directory)
    numbers = _epoch_numbers(root)
    if not numbers:
        raise ReceiptSetupError(f"{root} holds no epochs")
    if numbers != list(range(1, numbers[-1] + 1)):
        raise ReceiptSetupError(f"{root} is missing epoch(s) {sorted(set(range(1, numbers[-1] + 1)) - set(numbers))}")
    audits: list[EpochAudit] = []
    for number in numbers:
        folder = root / f"epoch-{number:06d}"
        expected = epoch_log_id(base_log_id, number)
        receipts = _read_readonly(folder / RECEIPTS_FILENAME)
        checkpoints = _read_readonly(folder / CHECKPOINTS_FILENAME)
        for row in (*receipts, *checkpoints):
            if row.get("log_id") != expected:
                raise ReceiptSetupError(f"epoch {number} carries log {row.get('log_id')!r}, expected {expected!r}")
        verify_log(receipts, trusted_signers=trusted_signers, checkpoint=checkpoints[-1] if checkpoints else None)
        closed = bool(checkpoints) and checkpoints[-1]["tree_size"] == len(receipts)
        if number != numbers[-1] and not closed:
            raise ReceiptSetupError(f"epoch {number} is not the newest but its checkpoints do not cover all {len(receipts)} receipts")
        audits.append(EpochAudit(number=number, log_id=expected, receipts=len(receipts), closed=closed))
    return audits


def _read_readonly(path: Path) -> list[dict[str, Any]]:
    """Like `_read_jsonl` but never modifies the file: an audit must not repair what it is auditing."""
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
    rows = []
    for number, line in enumerate(data.split(b"\n")[:-1], start=1):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReceiptSetupError(f"{path} line {number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ReceiptSetupError(f"{path} line {number} is not a JSON object")
        rows.append(row)
    return rows
