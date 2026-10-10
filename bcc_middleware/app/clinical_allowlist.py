"""Hot-reloaded clinical-agent allowlist for the signed policy pack.

Why this exists
---------------
`policies/bcc.rego` unions a few static demo agents with a runtime OPA *data document*
(`data.clinical_allowlist.agents`). A signed pack cannot carry that document: it is immutable
once signed and `integrity_sdk.core.opa.OpaClient` owns what OPA holds. So the pack reads the
extra agents from `input.clinical_allowlist`, and this module is where BCC gets them: a small
JSON file the operator edits, re-read when it changes.

    {"agents": ["did:integrity:...", "did:integrity:..."]}

Failure posture: FAIL CLOSED
----------------------------
This list grants authority (an agent on it may commit clinical intents), so every way it can be
wrong resolves to *fewer* authorized agents, never more:

* **No file configured** -> no extra agents. This matches `bcc.rego` with no data document.
* **File missing or unreadable, invalid JSON, wrong shape, or a non-string entry** -> no extra
  agents, logged at ERROR, and `status()["error"]` says why (surfaced by `/health`).
* **A later bad edit does NOT keep the last good list.** "Keep last good" is the usual hot-reload
  choice, and it is wrong here: an operator who removes a revoked agent and, in the same edit,
  breaks the JSON would leave the revoked agent authorized with nothing to say so. Denying the
  extra agents until the file parses is the conservative failure, and it is loud.

The cost is stated: a typo in this file stops every non-static agent from committing clinical
intents until it is fixed. The static agents in the pack are unaffected.

Reloading
---------
The file is stat-ed on every call (cheap) and re-read when its (inode, size, mtime) changes, and
at least every `MAX_STALE_SECONDS` regardless, so a rewrite that leaves all three unchanged still
takes effect within a bounded time. Atomic replacement (write a temp file, `rename` over it) is
the recommended way to edit it: readers never see a half-written file, and the inode changes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Upper bound on how long a rewrite that preserved (inode, size, mtime) can go unnoticed.
MAX_STALE_SECONDS = 5.0


class ClinicalAllowlist:
    """Thread-safe view of the allowlist file. Safe to call from `asyncio.to_thread`."""

    def __init__(self, path: str | os.PathLike[str] | None, *, max_stale_seconds: float = MAX_STALE_SECONDS) -> None:
        self._path: Optional[Path] = Path(path) if path else None
        self._max_stale = max_stale_seconds
        self._lock = threading.Lock()
        self._signature: object = object()  # never equal to a real signature, so the first call loads
        self._loaded_at = 0.0
        self._agents: tuple[str, ...] = ()
        self._error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return self._path is not None

    def current(self) -> list[str]:
        """The agents authorized right now (a fresh list; the caller may keep or mutate it)."""
        if self._path is None:
            return []
        with self._lock:
            signature = self._stat_signature()
            now = time.monotonic()
            if signature != self._signature or now - self._loaded_at >= self._max_stale:
                self._reload(signature, now)
            return list(self._agents)

    def status(self) -> dict[str, object]:
        """Non-sensitive state for `/health`: whether it is configured, healthy, and how many entries."""
        self.current()
        with self._lock:
            return {"configured": self._path is not None, "ok": self._error is None, "error": self._error,
                    "agents": len(self._agents)}

    # ---------------------------------------------------------------------------- internals

    def _stat_signature(self) -> object:
        try:
            info = self._path.stat()  # type: ignore[union-attr]
        except OSError:
            return None
        return (info.st_ino, info.st_size, info.st_mtime_ns)

    def _reload(self, signature: object, now: float) -> None:
        self._signature = signature
        self._loaded_at = now
        previous = self._agents
        agents, error = self._read()
        self._agents, self._error = agents, error
        if error is not None:
            # Fail closed: do NOT fall back to `previous`. See the module docstring.
            logger.error("clinical allowlist %s unusable, authorizing NO extra agents: %s", self._path, error)
        elif agents != previous:
            logger.info("clinical allowlist %s loaded: %d extra agent(s)", self._path, len(agents))

    def _read(self) -> tuple[tuple[str, ...], Optional[str]]:
        try:
            raw = self._path.read_bytes()  # type: ignore[union-attr]
        except OSError as exc:
            return (), f"cannot read file: {exc.strerror or type(exc).__name__}"
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return (), f"not valid JSON: {type(exc).__name__}"
        if not isinstance(document, dict) or set(document) != {"agents"} or not isinstance(document["agents"], list):
            return (), 'expected exactly {"agents": [...]}'
        entries = document["agents"]
        if not all(isinstance(entry, str) and entry.strip() == entry and entry for entry in entries):
            return (), "every agent must be a non-empty string without surrounding whitespace"
        return tuple(sorted(set(entries))), None
