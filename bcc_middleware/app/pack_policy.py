"""BCC's signed-pack policy: verify a pack, install it, decide through the shared contract.

This is stage 2 of the staged migration in docs/design/bcc-shared-pack-migration.md. Until now BCC
decided with `policies/bcc.rego` and trusted a boolean `allow`. Here the same decision comes from a
*signed pack* (`packs/bcc`) evaluated through `integrity_sdk.core` -- the path Xibalba Shield's gate
already uses -- so a verdict means the same thing in both gates and a receipt can name a pack hash
that was actually verified.

How it is used (app/main.py::_policy_outcome)
---------------------------------------------
* **Dual-run** (`BCC_POLICY_PACK_DIR` set, `BCC_POLICY_ENGINE=rego`, the default): `bcc.rego` still
  decides. The pack is evaluated beside it on every request and any disagreement is logged and counted
  (`DualRunStats`, surfaced by `/health`). The pack can never change a response in this mode.
* **Pack mode** (`BCC_POLICY_ENGINE=pack`): the pack decides and `bcc.rego` is not consulted.
  Flipping the setting back is the rollback.

Failure postures (this repository states one per module)
-------------------------------------------------------
* **Loading is fail-closed.** `load_pack` verifies the signature against the configured trusted
  signers, the manifest, every file hash, expiry and (if configured) the pinned pack hash, and it
  returns the verified bytes that are then installed -- OPA never runs a byte that was not verified.
  Any failure raises `PackPolicyError`. In pack mode the service refuses to start. In dual-run it keeps
  deciding with `bcc.rego`, logs at ERROR, and `/health` says the pack is not loaded.
* **Evaluation is fail-closed.** In pack mode an unreachable OPA, a malformed result or a reserved
  reason code is a *deny* (`BCC_POLICY_ENGINE_UNAVAILABLE` for the infrastructure cases, never counted
  against the agent's circuit breaker), exactly as `opa_client.evaluate` behaves for `bcc.rego`. A
  result the shared `resolve()` cannot interpret denies. Only a `permit` (or `log_only`) allows.
* **A dedicated OPA.** `OpaClient.install` replaces every policy under one fixed id prefix, and every
  pack's file is `policy.rego`, so two gates pointed at one OPA overwrite each other's pack. BCC takes
  `BCC_PACK_OPA_URL` and refuses to fall back to `OPA_URL`.
* **If the pack's OPA forgets the pack** (it restarted), a query returns "undefined", which `resolve()`
  correctly turns into the pack's default deny. That would deny everything until BCC restarted, so one
  undefined result triggers a throttled re-install (`REINSTALL_MIN_INTERVAL_SECONDS`) and a retry. If
  the pack is genuinely absent the answer is still deny.

Hot reload (`PackPolicy.reload`, `POST /v1/admin/policy-pack/reload`)
--------------------------------------------------------------------
A new pack can replace the running one without a restart. The posture is **all-or-nothing, keep the old pack on
any failure**:

* The candidate is verified FIRST (signature against the startup trusted signers, manifest, every file hash, expiry,
  declared event class) and must hash to the `expected_pack_hash` the operator names. Nothing is touched until it passes.
* Only then is it installed into the dedicated OPA. If the install fails, the previous pack is put back; if that also
  fails, every decision denies (the client holds no installed pack) until a reload succeeds or the service restarts, and
  the failure is logged CRITICAL. A failed reload never leaves a half-installed pack enforcing.
* Each decision takes ONE snapshot of the pack, so the pack hash it reports, its defaults, and the policy OPA evaluated
  are the same pack. A decision never mixes two packs.
* While the swap runs, new decisions wait (bounded by `SWAP_WAIT_SECONDS`) rather than being denied; a decision already
  in flight when OPA's policy is replaced fails closed (`PackPolicyError` -> BCC_POLICY_ENGINE_UNAVAILABLE, never charged
  to the agent). Nothing can be *allowed* by the wrong pack.
* What a reload does NOT change: the trusted signers and the OPA URL (startup configuration -- changing who may sign
  policy is not something a runtime call should do). A reload also does not update `BCC_POLICY_PACK_HASH` in the
  environment: if you pin it, update the pin when you reload, or the next restart will (correctly) refuse the new pack.

What is NOT here: receipts for the reload itself ([PLANNED]: the swap is logged and counted on /health, but is not a
signed receipt).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from integrity_sdk.core import decision as d
from integrity_sdk.core.opa import OpaClient, OpaError
from integrity_sdk.core.packs import LoadedPack, PackError, load_pack

from app.clinical_allowlist import ClinicalAllowlist
from app.config import Settings
from app.opa_client import OPADecision

logger = logging.getLogger(__name__)

#: The event class every BCC commitment is evaluated under (declared by `packs/bcc/pack.yaml`).
EVENT_CLASS = "agent.tool_call"

#: Intent types that need an authorized agent, a verified tier and an active on-chain BAA. The decision
#: contract has no `requires_baa` output, so the gate keeps this set itself. It is pinned to `bcc.rego`
#: and to the pack's behaviour by tests/test_pack_policy.py: a sixth type added in one place and not the
#: others fails the build instead of silently skipping the BAA check.
CLINICAL_INTENT_TYPES = frozenset({
    "EMR_WRITE", "DISPENSE_MEDICATION", "BILLING_SUBMISSION", "SECURE_EMR_WRITE", "CLINICAL_DATA_ACCESS",
})

#: Do not re-install the pack into OPA more often than this, however many requests see it missing.
REINSTALL_MIN_INTERVAL_SECONDS = 5.0

#: How long a decision waits for an in-progress pack swap before failing closed.
SWAP_WAIT_SECONDS = 5.0

#: Reported by the pack for a request it could not read (no string agent_id / intent_type). It has no
#: counterpart in bcc.rego, which allows such a request -- a known, pinned divergence, not a bug.
MALFORMED_CODE = "BCC_MALFORMED_COMMITMENT"


class PackPolicyError(Exception):
    """The pack could not be loaded, or could not be evaluated. Callers treat this as fail-closed."""


def requires_baa(intent_type: str) -> bool:
    return intent_type in CLINICAL_INTENT_TYPES


@dataclass(frozen=True)
class PackVerdict:
    allow: bool
    reason_code: str
    controls: tuple[str, ...]


@dataclass(frozen=True)
class ReloadResult:
    changed: bool
    previous_hash: str
    pack_hash: str
    name: str
    version: str


@dataclass
class DualRunStats:
    """Counters for the dual-run comparison. Not security state: they only inform the cutover."""

    compared: int = 0
    divergences: int = 0
    pack_errors: int = 0
    last_divergence: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record(self, *, divergence: Optional[str] = None, error: bool = False) -> None:
        with self._lock:
            if error:
                self.pack_errors += 1
                return
            self.compared += 1
            if divergence is not None:
                self.divergences += 1
                self.last_divergence = divergence

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {"compared": self.compared, "divergences": self.divergences,
                    "pack_errors": self.pack_errors, "last_divergence": self.last_divergence}


class PackPolicy:
    """One verified, installed pack and the means to evaluate commitments against it."""

    def __init__(self, pack: LoadedPack, client: OpaClient, allowlist: ClinicalAllowlist) -> None:
        self._pack = pack
        self._client = client
        self._allowlist = allowlist
        # One lock for everything that installs into OPA: a reload, and the re-install after OPA forgets the pack.
        # Two installs interleaving could leave OPA holding a different pack than the one this object enforces.
        self._reload_lock = threading.Lock()
        # Cleared for the duration of a swap; decisions wait on it (bounded) instead of querying a half-swapped OPA.
        self._swap_ready = threading.Event()
        self._swap_ready.set()
        self.reloads = 0
        self.last_reload: Optional[dict[str, object]] = None
        # -inf, not 0.0: time.monotonic() can be tiny right after boot, which would throttle the first re-install.
        self._last_reinstall = float("-inf")
        self.stats = DualRunStats()

    # --------------------------------------------------------------------------- loading

    @staticmethod
    def _verify(settings: Settings, expected_pack_hash: Optional[str]) -> LoadedPack:
        """Verify the configured pack directory against the trusted signers, or raise `PackPolicyError`. Installs nothing."""
        if not settings.policy_pack_dir:
            raise PackPolicyError("BCC_POLICY_PACK_DIR is not set")
        if not settings.trusted_pack_signers:
            raise PackPolicyError("BCC_TRUSTED_PACK_SIGNERS is required with a policy pack: refusing to trust any signer")
        if not settings.pack_opa_url:
            raise PackPolicyError(
                "BCC_PACK_OPA_URL is required with a policy pack. There is no fallback to OPA_URL: two gates' packs "
                "share a policy id, so a shared OPA would have each overwrite the other's pack"
            )
        try:
            pack = load_pack(
                settings.policy_pack_dir,
                trusted_signers=sorted(settings.trusted_pack_signers),
                expected_pack_hash=expected_pack_hash,
            )
        except PackError as exc:
            raise PackPolicyError(f"policy pack {settings.policy_pack_dir} failed verification: {exc}") from exc
        if EVENT_CLASS not in pack.event_defaults:
            raise PackPolicyError(f"policy pack {pack.manifest['name']} does not declare event class {EVENT_CLASS!r}")
        return pack

    @classmethod
    def load(cls, settings: Settings, allowlist: Optional[ClinicalAllowlist] = None) -> "PackPolicy":
        """Verify and install the configured pack, or raise `PackPolicyError` saying what is missing."""
        pack = cls._verify(settings, settings.policy_pack_hash)
        client = OpaClient(settings.pack_opa_url, timeout_seconds=settings.opa_timeout_seconds)
        try:
            client.install(pack)
        except OpaError as exc:
            raise PackPolicyError(f"could not install the verified pack into {settings.pack_opa_url}: {exc}") from exc
        logger.info("policy pack %s %s (%s) installed", pack.manifest["name"], pack.manifest["version"], pack.pack_hash)
        return cls(pack, client, allowlist or ClinicalAllowlist(settings.clinical_allowlist_file))

    def reload(self, settings: Settings, *, expected_pack_hash: str) -> ReloadResult:
        """Replace the running pack with the one now in `settings.policy_pack_dir`, or change nothing.

        `expected_pack_hash` is required: the operator states exactly which pack they mean to run, so a file swapped on
        disk by someone else cannot be activated by a reload that merely says "reload". Raises `PackPolicyError`; the
        previous pack keeps enforcing unless the message says it could not be restored.
        """
        if not expected_pack_hash:
            raise PackPolicyError("expected_pack_hash is required to reload")
        if not self._reload_lock.acquire(blocking=False):
            raise PackPolicyError("a reload (or a pack re-install) is already in progress; try again")
        try:
            candidate = self._verify(settings, expected_pack_hash)  # raises before anything is touched
            previous = self._pack
            if candidate.pack_hash == previous.pack_hash:
                return ReloadResult(False, previous.pack_hash, candidate.pack_hash, self.name, self.version)
            self._swap_ready.clear()
            try:
                try:
                    self._client.install(candidate)
                except OpaError as exc:
                    # OpaClient.install clears its installed state first, so put the PREVIOUS pack back.
                    try:
                        self._client.install(previous)
                    except OpaError as restore_exc:
                        logger.critical(
                            "pack reload failed (%s) AND the previous pack could not be restored (%s): every decision "
                            "denies until a reload succeeds or the service restarts", exc, restore_exc,
                        )
                        raise PackPolicyError(
                            f"reload failed ({exc}) and the previous pack could not be restored ({restore_exc}); "
                            "decisions deny until a reload succeeds or the service restarts"
                        ) from exc
                    raise PackPolicyError(f"reload failed, previous pack {previous.pack_hash} kept: {exc}") from exc
                self._pack = candidate  # one reference assignment: decisions that start after this see the new pack
            finally:
                self._swap_ready.set()
            self.reloads += 1
            self.last_reload = {"from": previous.pack_hash, "to": candidate.pack_hash, "at": time.time()}
            logger.warning("policy pack reloaded: %s -> %s (%s %s)", previous.pack_hash, candidate.pack_hash,
                           candidate.manifest["name"], candidate.manifest["version"])
            return ReloadResult(True, previous.pack_hash, candidate.pack_hash,
                                str(candidate.manifest["name"]), str(candidate.manifest["version"]))
        finally:
            self._reload_lock.release()

    # ------------------------------------------------------------------------ properties

    @property
    def pack_hash(self) -> str:
        return self._pack.pack_hash

    @property
    def name(self) -> str:
        return str(self._pack.manifest["name"])

    @property
    def version(self) -> str:
        return str(self._pack.manifest["version"])

    @property
    def allowlist(self) -> ClinicalAllowlist:
        return self._allowlist

    # ------------------------------------------------------------------------ evaluation

    def _query(self, pack: LoadedPack, pack_input: Mapping[str, Any]) -> Any:
        try:
            return self._client.query(pack, pack_input)
        except OpaError as exc:
            raise PackPolicyError(f"pack evaluation failed: {exc}") from exc
        except (OSError, ValueError) as exc:  # URLError is an OSError; a bad body is a ValueError
            raise PackPolicyError(f"pack evaluation failed: {type(exc).__name__}: {exc}") from exc

    def decide_sync(self, opa_input: Mapping[str, Any]) -> PackVerdict:
        """Decide one commitment. Blocking (urllib); use `decide` from async code."""
        # The gate-owned keys go LAST so nothing in `opa_input` can override them: `event_class` selects the
        # rules and `clinical_allowlist` grants authority. Both come from here, never from the commitment.
        pack_input = {**opa_input, "event_class": EVENT_CLASS, "clinical_allowlist": self._allowlist.current()}
        if not self._swap_ready.wait(SWAP_WAIT_SECONDS):
            raise PackPolicyError("a policy pack swap is taking too long; failing closed")
        pack = self._pack  # ONE snapshot: the hash, the defaults and the evaluated policy are the same pack
        raw = self._query(pack, pack_input)
        if raw is d.NO_MATCH and self._reinstall_if_forgotten(pack):
            raw = self._query(pack, pack_input)
        decision = d.resolve(
            EVENT_CLASS, raw, event_defaults=pack.event_defaults, mode=d.ENFORCE, pack_hash=pack.pack_hash
        )
        return PackVerdict(allow=not decision.blocks, reason_code=decision.reason_code, controls=decision.controls)

    async def decide(self, opa_input: Mapping[str, Any]) -> PackVerdict:
        return await asyncio.to_thread(self.decide_sync, opa_input)

    def _reinstall_if_forgotten(self, pack: LoadedPack) -> bool:
        """After an "undefined" result, put `pack` back (at most once per interval). True if it did.

        Does nothing if `pack` is no longer the enforced one (a reload replaced it meanwhile): re-installing the OLD pack
        then would silently undo the reload.
        """
        with self._reload_lock:
            if pack is not self._pack:
                return False
            now = time.monotonic()
            if now - self._last_reinstall < REINSTALL_MIN_INTERVAL_SECONDS:
                return False
            self._last_reinstall = now
            try:
                self._client.install(pack)
            except OpaError as exc:
                raise PackPolicyError(f"pack re-install failed: {exc}") from exc
            logger.warning("policy pack %s was not in OPA (restart?); re-installed it", pack.pack_hash)
            return True

    # ------------------------------------------------------------------------- comparing

    @staticmethod
    def divergence(old: OPADecision, new: PackVerdict, intent_type: str) -> Optional[str]:
        """How `bcc.rego`'s answer and the pack's differ, or None if they agree.

        Agree means: the same verdict; the same BAA requirement; and, when both deny, a pack reason code
        that is one of the codes `bcc.rego` reported (the pack names the highest-priority one). The pack's
        MALFORMED code is the one deliberate exception: `bcc.rego` allows an unreadable request.
        """
        if old.allow != new.allow:
            return f"verdict: bcc.rego allow={old.allow}, pack allow={new.allow} ({new.reason_code})"
        if old.requires_baa != requires_baa(intent_type):
            return f"requires_baa: bcc.rego {old.requires_baa}, gate constant {requires_baa(intent_type)}"
        if not old.allow and new.reason_code != MALFORMED_CODE:
            old_codes = {message.split(":", 1)[0] for message in old.violations}
            if new.reason_code not in old_codes:
                return f"reason: pack said {new.reason_code}, bcc.rego reported {sorted(old_codes)}"
        return None

    def health(self) -> dict[str, object]:
        return {"name": self.name, "version": self.version, "hash": self.pack_hash,
                "allowlist": self._allowlist.status(), "dual_run": self.stats.snapshot(),
                "reloads": self.reloads, "last_reload": self.last_reload}
