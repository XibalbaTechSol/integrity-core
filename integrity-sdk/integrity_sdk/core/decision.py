"""The decision contract (SDK contract C3): one way to turn a policy result into an action.

Both gates -- Shield on the device and BCC in the middleware -- evaluate the
same signed pack and pass the evaluator's raw result through `resolve`, so a
given result means the same thing wherever it is enforced. The rules:

- ``permit`` means permitted. (Shield previously read its OPA ``allow`` rule as
  "some rule matched", which turned an unmatched event into a deny that a
  mocked test hid.)
- When no rule matches (OPA returns an undefined result), the pack's declared
  default for that event class applies: ``deny``, ``log_only`` or ``permit``.
  Tool calls under a regulated pack declare ``deny``; device sensor events
  declare ``log_only``.
- Anything the gate cannot interpret fails closed: an evaluator error, a
  missing pack, an event class the pack does not declare, or a result that is
  not exactly ``{"decision", "reason_code"[, "controls"]}`` with known values.
- Reason codes starting ``INTEGRITY_`` are reserved for the gate itself, so a
  policy cannot impersonate a gate-level outcome in a receipt.
- ``shadow`` mode records the would-be decision but never blocks, so a pack can
  be replayed against live traffic before it is enforced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

DECISION_CONTRACT = "integrity.decision/1"

PERMIT = "permit"
DENY = "deny"
LOG_ONLY = "log_only"
DECISIONS = frozenset({PERMIT, DENY, LOG_ONLY})
NO_MATCH_DEFAULTS = DECISIONS  # what a pack may declare for an unmatched event class

ENFORCE = "enforce"
SHADOW = "shadow"
MODES = frozenset({ENFORCE, SHADOW})

RESERVED_REASON_PREFIX = "INTEGRITY_"
REASON_NO_MATCH = "INTEGRITY_NO_MATCH"
REASON_EVALUATOR_ERROR = "INTEGRITY_EVALUATOR_ERROR"
REASON_MALFORMED_DECISION = "INTEGRITY_MALFORMED_DECISION"
REASON_UNKNOWN_EVENT_CLASS = "INTEGRITY_UNKNOWN_EVENT_CLASS"
REASON_NO_PACK = "INTEGRITY_NO_PACK"

_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RESULT_KEYS = frozenset({"decision", "reason_code", "controls"})


class _NoMatch:
    """Sentinel for "the evaluator returned an undefined result" (no rule matched)."""

    _instance: Optional["_NoMatch"] = None

    def __new__(cls) -> "_NoMatch":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NO_MATCH"


NO_MATCH = _NoMatch()


@dataclass(frozen=True)
class Decision:
    """A resolved decision, ready to be enforced and written into a receipt."""

    decision: str
    reason_code: str
    mode: str
    controls: Tuple[str, ...] = field(default_factory=tuple)
    pack_hash: Optional[str] = None

    @property
    def blocks(self) -> bool:
        """Whether the gate must stop the action: only a deny, and only when enforcing."""
        return self.mode == ENFORCE and self.decision == DENY


def _malformed(mode: str, pack_hash: Optional[str]) -> Decision:
    return Decision(DENY, REASON_MALFORMED_DECISION, mode, (), pack_hash)


def resolve(
    event_class: str,
    result: Any,
    *,
    event_defaults: Optional[Mapping[str, str]],
    mode: str = ENFORCE,
    pack_hash: Optional[str] = None,
    evaluator_error: Optional[BaseException] = None,
) -> Decision:
    """Resolve an evaluator result under the decision contract.

    `event_defaults` is the loaded pack's ``event_class -> no_match default``
    map (``LoadedPack.event_defaults``), or None when no verified pack is
    loaded. `result` is the evaluator's value for the pack entrypoint, or
    `NO_MATCH` (``None`` is accepted as the same thing) when it was undefined.
    """
    if mode not in MODES:
        raise ValueError(f"unknown gate mode {mode!r}")  # a configuration bug, not a policy outcome
    if event_defaults is None:
        return Decision(DENY, REASON_NO_PACK, mode, (), pack_hash)
    if evaluator_error is not None:
        return Decision(DENY, REASON_EVALUATOR_ERROR, mode, (), pack_hash)
    default = event_defaults.get(event_class)
    if default is None:
        return Decision(DENY, REASON_UNKNOWN_EVENT_CLASS, mode, (), pack_hash)
    if default not in NO_MATCH_DEFAULTS:
        return _malformed(mode, pack_hash)  # a verified pack cannot get here; defend anyway

    if result is NO_MATCH or result is None:
        return Decision(default, REASON_NO_MATCH, mode, (), pack_hash)

    if not isinstance(result, Mapping) or not set(result) <= _RESULT_KEYS:
        return _malformed(mode, pack_hash)
    decision = result.get("decision")
    reason_code = result.get("reason_code")
    controls = result.get("controls", [])
    if decision not in DECISIONS:
        return _malformed(mode, pack_hash)
    if not isinstance(reason_code, str) or not _REASON_RE.fullmatch(reason_code):
        return _malformed(mode, pack_hash)
    if reason_code.startswith(RESERVED_REASON_PREFIX):
        return _malformed(mode, pack_hash)
    if not isinstance(controls, (list, tuple)) or not all(isinstance(c, str) and c for c in controls):
        return _malformed(mode, pack_hash)
    return Decision(decision, reason_code, mode, tuple(controls), pack_hash)
