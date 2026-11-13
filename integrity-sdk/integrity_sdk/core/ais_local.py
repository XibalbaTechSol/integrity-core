"""A local Agent Integrity Score computed from a gate's own receipts (L0: no chain, token or oracle).

This closes the AIS loop on one machine:

    gate decision --> signed receipt --> LocalReceiptScorer --> control zone --> gate's zone mask

The score is not a new formula. Each agent's recent receipts become an `AISInputs` and are evaluated by
`evaluate_ais_v1_geometric`; the zone comes from `evaluate_control_zone` under a `ZonePolicy`, the same
functions the Oracle's reference implementation is checked against. What is local is only *which
evidence* is used: the receipts this gate wrote, and nothing else.

What a receipt can honestly measure
-----------------------------------
A receipt records the policy pack's decision about one action. That supports one AIS axis:

* **Compliance** (`S_C`): `p` is the share of the agent's recent scored decisions that were violations.

Receipts say nothing about grounding (were claims backed by evidence), graph contribution, or
routing entropy, so those axes are given **weight 0** (`LOCAL_RECEIPT_WEIGHTS`) rather than a
made-up value. A zero-weight axis does not annihilate the geometric mean, so the result is
`min(S_C, tier ceiling)`. It is labelled `LOCAL_RECEIPT_PROFILE` everywhere it is reported so it is
never mistaken for an Oracle AIS computed from all four axes.

Which receipts count
--------------------
==========================================  ============  ===============================================
receipt                                     counts as     why
==========================================  ============  ===============================================
``decision: permit``                        clean
``decision: deny`` / ``log_only``           violation     the pack refused it, or would have (shadow);
                                                          this includes ``INTEGRITY_NO_MATCH``: an action
                                                          outside the signed graph *is* the violation
``reason_code: AIS_ZONE_RESTRICTED``        not counted   the zone mask's own denial. Counting it would
                                                          let a red zone keep itself red: every blocked
                                                          call would lower the score that blocked it
``INTEGRITY_EVALUATOR_ERROR`` /             not counted   a fault of the gate, not conduct of the agent
``INTEGRITY_MALFORMED_DECISION`` /
``INTEGRITY_NO_PACK``
any other decision value                    not counted
==========================================  ============  ===============================================

The window is the last `window_size` counted decisions per agent (optionally also bounded by age), so
a violation stops counting once enough clean decisions follow it: a red agent that keeps to what red
permits (reads and escalations, which the pack allows) climbs back out. Recovery to green from
yellow/red needs the policy's `recovery` threshold (hysteresis), not merely `green`.

Cold start: an agent with fewer than `min_observations` counted decisions has **no score** and the zone
is `unknown`. The caller decides what unknown means (Shield's mask: `unknown_as`, default yellow). A
new agent is never computed red merely for having no history.

Known limits (by design at L0, not fixed here)
----------------------------------------------
* The agent id is whatever the caller says it is. A restricted agent that switches to a new id starts
  again at cold start. Binding ids to keys is identity work (L1), not scoring.
* Count-based windows can be diluted: many cheap clean calls push violations out of the window sooner.
  `max_age_seconds` bounds this in time; weighting by action class needs the class on every receipt.
* The tier ceiling is applied before the zone is read (as in the Oracle), so for low tiers only a
  large violation share shows in the zone. See `ZonePolicy`.
* Receipts are read from the gate's own owner-only log and are not re-verified here; the writer
  refuses to start on a log that does not verify.

Stdlib only, like the rest of `integrity_sdk.core`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from calendar import timegm
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Tuple

from .ais_reward import (
    AISControlZone,
    AISInputs,
    ZonePolicy,
    evaluate_ais_v1_geometric,
    evaluate_control_zone,
    normalize_tier,
)
from .decision import DENY, LOG_ONLY, PERMIT

logger = logging.getLogger(__name__)

LOCAL_RECEIPT_PROFILE = "ais-local/receipts-compliance-1"

#: (w_E, w_G, w_S, w_C): only compliance is observable from receipts. See the module docstring.
LOCAL_RECEIPT_WEIGHTS: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

#: The zone mask's own denial (Shield `gate_zone.REASON_ZONE_RESTRICTED`). Never a violation.
REASON_ZONE_RESTRICTED = "AIS_ZONE_RESTRICTED"
#: Gate faults: decisions the agent did not cause.
GATE_FAULT_REASON_CODES = frozenset({
    "INTEGRITY_EVALUATOR_ERROR", "INTEGRITY_MALFORMED_DECISION", "INTEGRITY_NO_PACK",
})
EXCLUDED_REASON_CODES = frozenset({REASON_ZONE_RESTRICTED}) | GATE_FAULT_REASON_CODES

CLEAN, VIOLATION = "clean", "violation"

DEFAULT_WINDOW_SIZE = 50
DEFAULT_MIN_OBSERVATIONS = 10


def classify_receipt(receipt: Mapping[str, Any]) -> Optional[str]:
    """`clean`, `violation`, or None when the receipt does not count toward the score."""
    if receipt.get("reason_code") in EXCLUDED_REASON_CODES:
        return None
    decision = receipt.get("decision")
    if decision == PERMIT:
        return CLEAN
    if decision in (DENY, LOG_ONLY):
        return VIOLATION
    return None


def _receipt_epoch_seconds(receipt: Mapping[str, Any]) -> Optional[float]:
    value = receipt.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        return float(timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return None


@dataclass(frozen=True)
class LocalScorerSettings:
    """How the local scorer reads receipts. Every default is documented in the module docstring."""

    window_size: int = DEFAULT_WINDOW_SIZE
    min_observations: int = DEFAULT_MIN_OBSERVATIONS
    #: Decisions older than this are dropped from the window. None: count-bounded only.
    max_age_seconds: Optional[float] = None
    #: Verification tier for agents not in `agent_tiers`. Required: there is no safe implicit tier.
    default_tier: int = 0
    agent_tiers: Mapping[str, int] = None  # type: ignore[assignment]
    zone_policy: ZonePolicy = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if isinstance(self.window_size, bool) or not isinstance(self.window_size, int) or self.window_size < 1:
            raise ValueError(f"window_size must be a positive integer, got {self.window_size!r}")
        if (isinstance(self.min_observations, bool) or not isinstance(self.min_observations, int)
                or not 1 <= self.min_observations <= self.window_size):
            raise ValueError(
                f"min_observations must be an integer in 1..window_size ({self.window_size}), got {self.min_observations!r}")
        if self.max_age_seconds is not None and (
                isinstance(self.max_age_seconds, bool) or not isinstance(self.max_age_seconds, (int, float))
                or self.max_age_seconds <= 0):
            raise ValueError(f"max_age_seconds must be a positive number or None, got {self.max_age_seconds!r}")
        for label, tier in (("default_tier", self.default_tier), *((self.agent_tiers or {}).items())):
            if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 3:
                raise ValueError(f"tier for {label!r} must be an integer 0..3, got {tier!r}")
        object.__setattr__(self, "agent_tiers", dict(self.agent_tiers or {}))
        object.__setattr__(self, "zone_policy", self.zone_policy or ZonePolicy())

    def tier_for(self, agent_id: str) -> int:
        return normalize_tier(self.agent_tiers.get(agent_id, self.default_tier))


@dataclass(frozen=True)
class LocalScore:
    """One agent's local score. `zone` is `"unknown"` and `ais` is None during cold start."""

    agent_id: str
    zone: str
    ais: Optional[float]
    did_tier: int
    observations: int
    violations: int
    profile: str = LOCAL_RECEIPT_PROFILE

    @property
    def violation_share(self) -> Optional[float]:
        return self.violations / self.observations if self.observations else None

    def to_dict(self) -> Dict[str, object]:
        return {
            "agent_id": self.agent_id, "zone": self.zone, "ais": self.ais, "did_tier": self.did_tier,
            "observations": self.observations, "violations": self.violations, "profile": self.profile,
        }


UNKNOWN_ZONE = "unknown"


def score_window(outcomes: Iterable[str], *, did_tier: int, settings: LocalScorerSettings,
                 prev_zone: Optional[AISControlZone] = None, agent_id: str = "") -> Tuple[LocalScore, Optional[AISControlZone]]:
    """Pure: the score and zone for one agent's window of `clean`/`violation` outcomes.

    Returns the `LocalScore` and the zone to carry forward as hysteresis state (None during cold start,
    so that state is not invented before there is evidence).
    """
    window = list(outcomes)
    n = len(window)
    violations = sum(1 for o in window if o == VIOLATION)
    if n < settings.min_observations:
        return LocalScore(agent_id, UNKNOWN_ZONE, None, did_tier, n, violations), None
    components = evaluate_ais_v1_geometric(AISInputs(
        entropy_variance=0.0, grounding_ratio=1.0, graph_contribution=0.0,
        penalty_severity=violations / n, zk_coverage_ratio=0.0, did_tier=did_tier,
        weights=LOCAL_RECEIPT_WEIGHTS,
    ))
    zone = evaluate_control_zone(components.ais_final, did_tier=did_tier, prev_zone=prev_zone,
                                 policy=settings.zone_policy)
    return LocalScore(agent_id, zone.value, components.ais_final, did_tier, n, violations), zone


class LocalReceiptScorer:
    """Per-agent rolling windows over observed receipts, and the zone each window implies.

    Thread-safe: `observe` and `score` may be called from different request threads.
    """

    def __init__(self, settings: Optional[LocalScorerSettings] = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self.settings = settings or LocalScorerSettings()
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: Dict[str, Deque[Tuple[Optional[float], str]]] = {}
        self._zones: Dict[str, AISControlZone] = {}

    def observe(self, receipt: Mapping[str, Any]) -> bool:
        """Add one receipt. Returns whether it counted toward its agent's score."""
        outcome = classify_receipt(receipt)
        agent_id = receipt.get("agent_did")
        if outcome is None or not isinstance(agent_id, str) or not agent_id:
            return False
        with self._lock:
            window = self._windows.get(agent_id)
            if window is None:
                window = self._windows[agent_id] = deque(maxlen=self.settings.window_size)
            window.append((_receipt_epoch_seconds(receipt), outcome))
        return True

    def observe_all(self, receipts: Iterable[Mapping[str, Any]]) -> int:
        return sum(1 for r in receipts if self.observe(r))

    def _current_outcomes(self, agent_id: str) -> List[str]:
        window = self._windows.get(agent_id, ())
        max_age = self.settings.max_age_seconds
        if max_age is None:
            return [o for _, o in window]
        cutoff = self._clock() - max_age
        # An undated receipt cannot be shown to be recent, so with an age bound it does not count.
        return [o for ts, o in window if ts is not None and ts >= cutoff]

    def score(self, agent_id: str) -> LocalScore:
        """The agent's current score and zone. Advances the agent's hysteresis state."""
        with self._lock:
            tier = self.settings.tier_for(agent_id)
            result, zone = score_window(self._current_outcomes(agent_id), did_tier=tier, settings=self.settings,
                                        prev_zone=self._zones.get(agent_id), agent_id=agent_id)
            if zone is None:
                self._zones.pop(agent_id, None)
            else:
                self._zones[agent_id] = zone
            return result

    def agents(self) -> List[str]:
        with self._lock:
            return sorted(self._windows)


class ReceiptLogTail:
    """Reads the complete lines appended to a receipts JSONL file since the last read.

    A final line without its newline is a write in progress (or a torn tail the writer will truncate)
    and is left for the next read. If the file shrinks or is replaced, reading starts again from the
    top; callers that keep derived state should rebuild it (`reset` is True on the read where this
    happened). A complete line that is not a JSON object is skipped and logged, never raised: a scorer
    must not take the gate down.
    """

    def __init__(self, path: os.PathLike[str] | str) -> None:
        self.path = Path(path)
        self._offset = 0
        self._identity: Optional[Tuple[int, int]] = None

    def read_new(self) -> Tuple[List[Dict[str, Any]], bool]:
        """`(new receipts, reset)`. Missing file: `([], False)`."""
        try:
            handle = self.path.open("rb")
        except FileNotFoundError:
            return [], False
        with handle:
            stat = os.fstat(handle.fileno())
            identity = (stat.st_dev, stat.st_ino)
            reset = False
            if self._identity is not None and (identity != self._identity or stat.st_size < self._offset):
                self._offset, reset = 0, True
            self._identity = identity
            handle.seek(self._offset)
            data = handle.read()
        complete = data[: data.rfind(b"\n") + 1]
        self._offset += len(complete)
        rows: List[Dict[str, Any]] = []
        for line in complete.split(b"\n")[:-1]:
            try:
                row = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                logger.warning("skipping a receipt line in %s that is not valid JSON", self.path)
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows, reset


class ReceiptLogZoneSource:
    """`agent_id -> LocalScore`, kept current by tailing one receipts file before each answer.

    This is the piece a gate plugs into its zone mask: Shield wraps it as a zone provider.
    """

    def __init__(self, receipts_path: os.PathLike[str] | str, settings: Optional[LocalScorerSettings] = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self._settings = settings or LocalScorerSettings()
        self._clock = clock
        self._tail = ReceiptLogTail(receipts_path)
        self._lock = threading.Lock()
        self.scorer = LocalReceiptScorer(self._settings, clock=clock)

    def refresh(self) -> int:
        """Read whatever was appended since the last refresh. Returns how many receipts counted."""
        with self._lock:
            rows, reset = self._tail.read_new()
            if reset:
                self.scorer = LocalReceiptScorer(self._settings, clock=self._clock)
            return self.scorer.observe_all(rows)

    def score(self, agent_id: str) -> LocalScore:
        self.refresh()
        return self.scorer.score(agent_id)

    def __call__(self, agent_id: str) -> LocalScore:
        return self.score(agent_id)
