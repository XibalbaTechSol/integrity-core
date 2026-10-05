"""Redacted, verifiable decision correlation for Hermes, Cortex and Shield.

DecisionTrace is an observability contract, not an enforcement contract.  The
envelope intentionally contains identifiers, policy references and bounded
metadata only.  It never carries prompts, completions, tool arguments or
chain-of-thought.  Jev providers may annotate a trace, but cannot decide an
action or create an Integrity receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .jcs import canonical_bytes
from .merkle import keccak256, leaf_hash, merkle_proof, merkle_root, verify_leaf

DECISION_TRACE_VERSION = "integrity.decision-trace/1"
DECISION_ENVELOPE_VERSION = "integrity.decision-envelope/1"
TRACE_LEAF_KIND = "decision-trace"
GENESIS_PARENT = "0x" + "00" * 32

_FORBIDDEN_KEYS = frozenset({
    "prompt", "completion", "messages", "chain_of_thought", "reasoning", "tool_args",
    "tool_arguments", "stdout", "stderr", "file_content", "secret", "token", "password",
})


class DecisionTraceError(ValueError):
    """A trace or advisory violates the local contract."""


def _reject_raw_content(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in _FORBIDDEN_KEYS or any(part in normalized for part in ("chain_of_thought", "tool_arg")):
                raise DecisionTraceError(f"raw content field is forbidden: {path}.{key}")
            _reject_raw_content(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_raw_content(child, f"{path}[{index}]")
    elif isinstance(value, str) and len(value) > 2048:
        raise DecisionTraceError(f"metadata value exceeds bounded size at {path}")


def _hash_document(document: Mapping[str, Any]) -> str:
    return "0x" + keccak256(canonical_bytes(dict(document))).hex()


@dataclass(frozen=True)
class DecisionEnvelope:
    """One observed state transition, with no raw model content."""

    tenant_id: str
    agent_id: str
    trace_id: str
    event_id: str
    event_type: str
    timestamp: str
    session_id: str | None = None
    turn_id: str | None = None
    invocation_id: str | None = None
    tool_call_id: str | None = None
    parent_event_hash: str = GENESIS_PARENT
    policy_ref: str | None = None
    policy_decision: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    redaction_status: str = "redacted"
    causal_claim: bool = False

    def __post_init__(self) -> None:
        for name in ("tenant_id", "agent_id", "trace_id", "event_id", "event_type", "timestamp"):
            if not getattr(self, name):
                raise DecisionTraceError(f"{name} is required")
        if self.redaction_status != "redacted":
            raise DecisionTraceError("DecisionTrace requires redaction_status='redacted'")
        if self.causal_claim:
            raise DecisionTraceError("DecisionTrace cannot make causal claims")
        _reject_raw_content(self.metadata)

    def body(self) -> dict[str, Any]:
        return {
            "envelope_version": DECISION_ENVELOPE_VERSION,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "trace_id": self.trace_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "invocation_id": self.invocation_id,
            "tool_call_id": self.tool_call_id,
            "parent_event_hash": self.parent_event_hash,
            "policy_ref": self.policy_ref,
            "policy_decision": self.policy_decision,
            "metadata": dict(self.metadata),
            "redaction_status": self.redaction_status,
            "causal_claim": False,
        }

    @property
    def event_hash(self) -> str:
        return _hash_document(self.body())

    @property
    def leaf(self) -> bytes:
        return leaf_hash(TRACE_LEAF_KIND, bytes.fromhex(self.event_hash[2:]))


@dataclass(frozen=True)
class DecisionTrace:
    """An append-only trace with parent-link and Merkle verification."""

    trace_id: str
    tenant_id: str
    agent_id: str
    events: tuple[DecisionEnvelope, ...] = ()

    def append(self, event: DecisionEnvelope) -> "DecisionTrace":
        if event.trace_id != self.trace_id or event.tenant_id != self.tenant_id or event.agent_id != self.agent_id:
            raise DecisionTraceError("trace event namespace mismatch")
        expected = self.events[-1].event_hash if self.events else GENESIS_PARENT
        if event.parent_event_hash != expected:
            raise DecisionTraceError("trace parent link mismatch")
        if any(existing.event_id == event.event_id for existing in self.events):
            raise DecisionTraceError("duplicate trace event")
        return DecisionTrace(self.trace_id, self.tenant_id, self.agent_id, self.events + (event,))

    @property
    def root(self) -> str | None:
        return "0x" + merkle_root([event.leaf for event in self.events]).hex() if self.events else None

    def proof(self, index: int) -> list[str]:
        leaves = [event.leaf for event in self.events]
        return ["0x" + item.hex() for item in merkle_proof(leaves, index)]

    def verify(self) -> bool:
        previous = GENESIS_PARENT
        for event in self.events:
            if event.parent_event_hash != previous:
                return False
            previous = event.event_hash
        return True

    def verify_inclusion(self, index: int, proof: Sequence[str], root: str | None = None) -> bool:
        if not 0 <= index < len(self.events):
            return False
        candidate = root or self.root
        if not candidate:
            return False
        return verify_leaf(bytes.fromhex(candidate[2:]), self.events[index].leaf,
                           [bytes.fromhex(item[2:] if item.startswith("0x") else item) for item in proof])


@dataclass(frozen=True)
class DecisionTraceEvidence:
    """Offline-verifiable trace root with an optional reference to an existing receipt."""

    trace_id: str
    root: str
    event_count: int
    receipt_hash: str | None = None
    checkpoint_root: str | None = None


def build_trace_evidence(trace: DecisionTrace, receipt: Mapping[str, Any] | None = None) -> DecisionTraceEvidence:
    if not trace.events or not trace.root:
        raise DecisionTraceError("cannot build evidence for an empty trace")
    linked_receipt_hash = None
    checkpoint_root = None
    if receipt is not None:
        from .receipts import receipt_hash as _receipt_hash
        linked_receipt_hash = _receipt_hash(receipt)
        reference = receipt.get("checkpoint_reference")
        if isinstance(reference, Mapping):
            checkpoint_root = reference.get("root")
    return DecisionTraceEvidence(trace.trace_id, trace.root, len(trace.events), linked_receipt_hash, checkpoint_root)


def verify_trace_evidence(
    trace: DecisionTrace,
    evidence: DecisionTraceEvidence,
    receipt: Mapping[str, Any] | None = None,
) -> bool:
    if not trace.verify() or trace.trace_id != evidence.trace_id or trace.root != evidence.root:
        return False
    if len(trace.events) != evidence.event_count:
        return False
    if evidence.receipt_hash is not None:
        if receipt is None:
            return False
        from .receipts import receipt_hash as _receipt_hash
        if _receipt_hash(receipt) != evidence.receipt_hash:
            return False
    return True


@dataclass(frozen=True)
class JevAnalysis:
    provider_id: str
    status: str
    risk_category: str | None = None
    transition_probabilities: Mapping[str, float] = field(default_factory=dict)
    recommended_escalation: bool = False
    observed_event_hash: str | None = None
    causal_claim: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"available", "unavailable", "rejected"}:
            raise DecisionTraceError("invalid Jev analysis status")
        if self.causal_claim:
            raise DecisionTraceError("Jev analysis cannot make causal claims")
        if any(not 0 <= float(value) <= 1 for value in self.transition_probabilities.values()):
            raise DecisionTraceError("transition probabilities must be between 0 and 1")
        if len(self.transition_probabilities) > 32:
            raise DecisionTraceError("too many transition probabilities")


class JevProvider(Protocol):
    provider_id: str

    def analyze(self, event: DecisionEnvelope) -> JevAnalysis:
        ...


class FixtureJevProvider:
    """Deterministic local provider used by tests, demos and offline pilots."""

    provider_id = "jev.fixture.v1"

    def analyze(self, event: DecisionEnvelope) -> JevAnalysis:
        risk = str(event.metadata.get("risk_hint", "low"))
        category = risk if risk in {"low", "medium", "high", "critical"} else "unknown"
        probabilities = {"continue": 0.8, "escalate": 0.2} if category in {"low", "unknown"} else {"continue": 0.35, "escalate": 0.65}
        return JevAnalysis(self.provider_id, "available", category, probabilities,
                           recommended_escalation=category in {"high", "critical"},
                           observed_event_hash=event.event_hash)


__all__ = [
    "DECISION_ENVELOPE_VERSION", "DECISION_TRACE_VERSION", "GENESIS_PARENT", "TRACE_LEAF_KIND",
    "DecisionEnvelope", "DecisionTrace", "DecisionTraceError", "DecisionTraceEvidence", "build_trace_evidence",
    "verify_trace_evidence", "JevAnalysis", "JevProvider",
    "FixtureJevProvider",
]
