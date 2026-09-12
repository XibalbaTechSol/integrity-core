"""
AgentSubject mapping (spec §4.1/§9.2, Gate 1 bullet 1).

Storage unification (tri-repo audit 2026-09-12, F2) put every DID under one
location and layout, but proved it cannot answer the question `AgentSubject`
actually needs to answer: "are these two labels the same logical agent?"
Two real cases from that audit motivate this module directly:

  - `xibalba-shield` and `shield-replacement` are two *different label
    strings* for what a human treats as the same intended agent -- no amount
    of storage-path matching detects that, because the labels never collide.
  - `xibalba` (SDK, `did:integrity:68fed133...`, general.integrity) and
    `xibalba-healthcare-cli` (CLI, `did:integrity:f96ae072...`,
    healthcare.integrity, `ComplianceGate.vertical()==1`) are two genuinely
    *different* agents that happen to share a label -- collision by
    coincidence, not by intent.

Per spec §4.2, this correspondence "MUST be explicit, auditable, versioned,
and lossless for historical references" -- i.e. it cannot be inferred, only
declared by a human (or another out-of-band authority) and recorded. This
module is that record, not a resolver that guesses.

Storage: an append-only JSONL file, `agent_subjects.jsonl`, alongside the
per-agent directories under `did.did_home()` (`$INTEGRITY_DID_HOME`, default
`~/.integrity/did/`) -- same root the tri-repo audit's F2 fix already made
authoritative for identity storage, so this doesn't introduce a second
config surface. Append-only mirrors §9.1's "MUST be additive, versioned,
replay-safe" -- a correction is a new record with `predecessor_mapping_id`
set, never an edit to a prior line. Each record follows §9.2's mapping-record
field set verbatim.

Field mapping onto §9.2's generic (source_namespace, source_identifier) ->
(target_namespace, target_identifier) shape:

  source_namespace / source_identifier: the local label being declared, e.g.
    ("integrity-did-label", "xibalba-shield").
  target_namespace / target_identifier: the AgentSubject this label belongs
    to. There is no separate subject-registry table -- a subject IS the set
    of labels transitively linked by `MappingType.SAME_SUBJECT` records, and
    its `target_identifier` is whichever label was declared canonical when
    the first mapping for that group was recorded (see `resolve_subject`).

`MappingType.DISTINCT_SUBJECT` records a reviewed non-identity (the `xibalba`
case) so a future migration or tool can't silently assume "same label
therefore same agent" -- it can check for an explicit denial first.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .did import did_home


class MappingType(str, Enum):
    SAME_SUBJECT = "same_subject"
    DISTINCT_SUBJECT = "distinct_subject"


class MappingStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class SubjectConflictError(RuntimeError):
    """Raised when a new mapping would contradict an existing, non-revoked
    declaration -- e.g. declaring SAME_SUBJECT for a pair already declared
    DISTINCT_SUBJECT, or vice versa. Per §9.2, a mapping records a *reviewed*
    relationship; silently overwriting a prior review would defeat the point
    of keeping history at all. Callers must revoke the conflicting record
    first (an explicit, auditable act) before recording the opposite claim.
    """


@dataclass
class MappingRecord:
    mapping_id: str
    source_namespace: str
    source_identifier: str
    target_namespace: str
    target_identifier: str
    mapping_type: MappingType
    basis: str
    created_at: float
    created_by_principal: str
    status: MappingStatus = MappingStatus.ACTIVE
    predecessor_mapping_id: Optional[str] = None
    revocation_reason: Optional[str] = None
    evidence_refs: list = field(default_factory=list)

    def to_json(self) -> dict:
        d = dict(self.__dict__)
        d["mapping_type"] = self.mapping_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_json(cls, d: dict) -> "MappingRecord":
        # Append-only file kept forever -- a future field added to this
        # dataclass must not make older *readers* choke on newer lines (or,
        # symmetrically, an older writer's line choke on `cls(**d)` here if a
        # field was since added with no default). Filter to known fields
        # rather than passing the raw dict through.
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        d["mapping_type"] = MappingType(d["mapping_type"])
        d["status"] = MappingStatus(d.get("status", "active"))
        return cls(**d)


def _default_subjects_path() -> Path:
    override = os.getenv("INTEGRITY_AGENT_SUBJECTS_FILE")
    if override:
        return Path(override).expanduser()
    return did_home() / "agent_subjects.jsonl"


def _read_all(path: Path) -> list[MappingRecord]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(MappingRecord.from_json(json.loads(line)))
    return records


def _append(path: Path, record: MappingRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record.to_json(), sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _effective_active_records(records: list[MappingRecord]) -> list[MappingRecord]:
    """A record's own `status` field is fixed at write time and never edited
    (append-only), so a REVOKED/SUPERSEDED record does not retroactively
    change its predecessor's stored status -- the predecessor line on disk
    still literally reads "active". The deactivation is expressed instead by
    a later record's `predecessor_mapping_id` pointing back at it. Resolve
    that indirection here rather than at every call site."""
    deactivated_ids = {
        r.predecessor_mapping_id
        for r in records
        if r.status != MappingStatus.ACTIVE and r.predecessor_mapping_id
    }
    return [
        r
        for r in records
        if r.status == MappingStatus.ACTIVE and r.mapping_id not in deactivated_ids
    ]


def _active_relationship(
    records: list[MappingRecord], a: str, b: str
) -> Optional[MappingRecord]:
    """Most recent non-revoked/non-superseded record declaring a relationship
    between labels `a` and `b`. Deliberately direction-insensitive -- "a and
    b are the same subject" (or "are distinct") is a symmetric claim
    regardless of which label was written as source vs. target."""
    latest = None
    for r in _effective_active_records(records):
        if {r.source_identifier, r.target_identifier} == {a, b}:
            latest = r
    return latest


def _connected_component(
    records: list[MappingRecord], label: str, mapping_type: MappingType
) -> set:
    """Every label transitively reachable from `label` via active edges of
    `mapping_type` only -- used both by `resolve_subject` (SAME_SUBJECT) and
    by the cross-type conflict check in `record_mapping` below."""
    adjacency: dict[str, set] = {}
    for r in _effective_active_records(records):
        if r.mapping_type != mapping_type:
            continue
        adjacency.setdefault(r.source_identifier, set()).add(r.target_identifier)
        adjacency.setdefault(r.target_identifier, set()).add(r.source_identifier)

    component = {label}
    stack = [label]
    while stack:
        node = stack.pop()
        for neighbor in adjacency.get(node, ()):
            if neighbor not in component:
                component.add(neighbor)
                stack.append(neighbor)
    return component


def record_mapping(
    *,
    source_identifier: str,
    target_identifier: str,
    mapping_type: MappingType,
    basis: str,
    created_by_principal: str,
    evidence_refs: Optional[list] = None,
    source_namespace: str = "integrity-did-label",
    target_namespace: str = "integrity-did-label",
    path: Optional[Path] = None,
) -> MappingRecord:
    """Declare a reviewed relationship between two labels. Fails closed
    (`SubjectConflictError`) rather than silently overwriting if an active
    record already declares the opposite relationship between the same pair
    -- per §9.2, "a mapping MUST NOT be treated as proof" on its own, and
    correcting one requires `revoke_mapping` first, not a quiet second write.
    """
    subjects_path = path or _default_subjects_path()
    existing = _read_all(subjects_path)

    conflict = _active_relationship(existing, source_identifier, target_identifier)
    if conflict is not None and conflict.mapping_type != mapping_type:
        raise SubjectConflictError(
            f"{source_identifier!r} and {target_identifier!r} already have an "
            f"active {conflict.mapping_type.value!r} mapping ({conflict.mapping_id}); "
            f"revoke it first before recording {mapping_type.value!r}"
        )
    if conflict is not None and conflict.mapping_type == mapping_type:
        # Already declared -- return the existing record rather than writing
        # a redundant duplicate line.
        return conflict

    if mapping_type == MappingType.SAME_SUBJECT:
        # Reject a SAME_SUBJECT edge that would transitively merge two labels
        # already reviewed as distinct through some other path -- e.g. a≡b,
        # b≡c already recorded, now declaring a≠c would be a direct conflict
        # above, but declaring a≡c here after b≠c was recorded independently
        # needs this transitive check instead of just the direct-pair one.
        comp_source = _connected_component(existing, source_identifier, MappingType.SAME_SUBJECT)
        comp_target = _connected_component(existing, target_identifier, MappingType.SAME_SUBJECT)
        for x in comp_source:
            for y in comp_target:
                distinct_edge = _active_relationship(existing, x, y)
                if distinct_edge is not None and distinct_edge.mapping_type == MappingType.DISTINCT_SUBJECT:
                    raise SubjectConflictError(
                        f"cannot merge {source_identifier!r} and {target_identifier!r} as the "
                        f"same subject -- {x!r} and {y!r} already have an active distinct_subject "
                        f"mapping ({distinct_edge.mapping_id}); revoke it first"
                    )

    record = MappingRecord(
        mapping_id=str(uuid.uuid4()),
        source_namespace=source_namespace,
        source_identifier=source_identifier,
        target_namespace=target_namespace,
        target_identifier=target_identifier,
        mapping_type=mapping_type,
        basis=basis,
        created_at=time.time(),
        created_by_principal=created_by_principal,
        evidence_refs=evidence_refs or [],
    )
    _append(subjects_path, record)
    return record


def revoke_mapping(
    mapping_id: str,
    *,
    reason: str,
    created_by_principal: str,
    path: Optional[Path] = None,
) -> MappingRecord:
    """Append a REVOKED record whose `predecessor_mapping_id` points at the
    record being revoked. The original line is never edited or deleted --
    append-only per §9.1."""
    subjects_path = path or _default_subjects_path()
    existing = _read_all(subjects_path)
    original = next((r for r in existing if r.mapping_id == mapping_id), None)
    if original is None:
        raise KeyError(f"no mapping record with mapping_id={mapping_id!r}")

    revocation = MappingRecord(
        mapping_id=str(uuid.uuid4()),
        source_namespace=original.source_namespace,
        source_identifier=original.source_identifier,
        target_namespace=original.target_namespace,
        target_identifier=original.target_identifier,
        mapping_type=original.mapping_type,
        basis=original.basis,
        created_at=time.time(),
        created_by_principal=created_by_principal,
        status=MappingStatus.REVOKED,
        predecessor_mapping_id=original.mapping_id,
        revocation_reason=reason,
    )
    _append(subjects_path, revocation)
    return revocation


def list_mappings(
    identifier: Optional[str] = None, *, path: Optional[Path] = None
) -> list[MappingRecord]:
    """Full history (including revoked/superseded lines) for one label, or
    every record if `identifier` is omitted."""
    subjects_path = path or _default_subjects_path()
    records = _read_all(subjects_path)
    if identifier is None:
        return records
    return [
        r
        for r in records
        if r.source_identifier == identifier or r.target_identifier == identifier
    ]


def resolve_subject(identifier: str, *, path: Optional[Path] = None) -> str:
    """Canonical subject id for `identifier`: the lexicographically smallest
    label in its connected component under active SAME_SUBJECT edges. A
    label with no SAME_SUBJECT mapping is its own subject. DISTINCT_SUBJECT
    edges are never followed -- `record_mapping` refuses to create a
    SAME_SUBJECT edge that would merge two labels already reviewed as
    distinct (see the transitive check there), so this traversal never needs
    to defend against that case itself.

    WARNING: this return value is NOT a stable identifier. Adding a new
    SAME_SUBJECT edge later can pull in a lexicographically smaller label and
    change which string this function returns for an *existing* label whose
    own mappings never changed. Do not persist this value elsewhere as a
    subject's permanent id -- persist the (source_identifier,
    target_identifier, mapping_id) triple from the actual mapping record
    instead, and call this function fresh each time a canonical grouping is
    needed.
    """
    subjects_path = path or _default_subjects_path()
    records = _read_all(subjects_path)
    component = _connected_component(records, identifier, MappingType.SAME_SUBJECT)
    return min(component)


def are_distinct(a: str, b: str, *, path: Optional[Path] = None) -> bool:
    """True if an active DISTINCT_SUBJECT record exists between `a` and `b`.
    Used to fail closed before any tooling merges two labels that a human has
    already reviewed and declared different -- the `xibalba` case."""
    subjects_path = path or _default_subjects_path()
    records = _read_all(subjects_path)
    r = _active_relationship(records, a, b)
    return r is not None and r.mapping_type == MappingType.DISTINCT_SUBJECT
