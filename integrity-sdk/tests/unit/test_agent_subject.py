from __future__ import annotations

import pytest

from integrity_sdk import agent_subject as subj


@pytest.fixture(autouse=True)
def _did_env(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))


def test_record_mapping_persists_alongside_did_home(tmp_path):
    record = subj.record_mapping(
        source_identifier="xibalba-shield",
        target_identifier="shield-replacement",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="human review: both are the Shield device agent, relabeled after F2 migration",
        created_by_principal="jacob.v.universe@gmail.com",
    )
    assert record.mapping_id
    assert (tmp_path / "dids" / "agent_subjects.jsonl").exists()

    fetched = subj.list_mappings("xibalba-shield")
    assert len(fetched) == 1
    assert fetched[0].mapping_id == record.mapping_id


def test_same_subject_resolves_to_shared_canonical_id():
    subj.record_mapping(
        source_identifier="xibalba-shield",
        target_identifier="shield-replacement",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="human review",
        created_by_principal="jacob.v.universe@gmail.com",
    )
    a = subj.resolve_subject("xibalba-shield")
    b = subj.resolve_subject("shield-replacement")
    assert a == b


def test_distinct_subject_is_not_merged_by_resolve():
    subj.record_mapping(
        source_identifier="xibalba",
        target_identifier="xibalba-healthcare-cli",
        mapping_type=subj.MappingType.DISTINCT_SUBJECT,
        basis="on-chain vertical() differs: general.integrity vs healthcare.integrity",
        created_by_principal="jacob.v.universe@gmail.com",
    )
    assert subj.resolve_subject("xibalba") == "xibalba"
    assert subj.resolve_subject("xibalba-healthcare-cli") == "xibalba-healthcare-cli"
    assert subj.are_distinct("xibalba", "xibalba-healthcare-cli")


def test_conflicting_mapping_type_is_rejected():
    subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.DISTINCT_SUBJECT,
        basis="reviewed as different",
        created_by_principal="p",
    )
    with pytest.raises(subj.SubjectConflictError):
        subj.record_mapping(
            source_identifier="a",
            target_identifier="b",
            mapping_type=subj.MappingType.SAME_SUBJECT,
            basis="attempted contradiction",
            created_by_principal="p",
        )


def test_recording_the_same_relationship_twice_is_idempotent():
    first = subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="reviewed",
        created_by_principal="p",
    )
    second = subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="reviewed again",
        created_by_principal="p",
    )
    assert first.mapping_id == second.mapping_id
    assert len(subj.list_mappings("a")) == 1


def test_revoke_then_reverse_declaration_succeeds():
    original = subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.DISTINCT_SUBJECT,
        basis="initially reviewed as different",
        created_by_principal="p",
    )
    subj.revoke_mapping(
        original.mapping_id,
        reason="further evidence showed this was a mistaken review",
        created_by_principal="p",
    )
    reversed_record = subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="corrected after revocation",
        created_by_principal="p",
    )
    assert subj.resolve_subject("a") == subj.resolve_subject("b")
    history = subj.list_mappings("a")
    assert len(history) == 3  # original, revocation, corrected
    assert reversed_record.predecessor_mapping_id is None


def test_revoke_unknown_mapping_id_raises_keyerror():
    with pytest.raises(KeyError):
        subj.revoke_mapping("does-not-exist", reason="n/a", created_by_principal="p")


def test_unrelated_label_resolves_to_itself():
    assert subj.resolve_subject("never-mapped") == "never-mapped"


def test_transitive_merge_across_a_distinct_declaration_is_rejected():
    subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="reviewed",
        created_by_principal="p",
    )
    subj.record_mapping(
        source_identifier="b",
        target_identifier="c",
        mapping_type=subj.MappingType.DISTINCT_SUBJECT,
        basis="reviewed as different",
        created_by_principal="p",
    )
    with pytest.raises(subj.SubjectConflictError):
        subj.record_mapping(
            source_identifier="a",
            target_identifier="c",
            mapping_type=subj.MappingType.SAME_SUBJECT,
            basis="would silently merge a with c through b's distinct edge",
            created_by_principal="p",
        )


def test_transitive_same_subject_chain_shares_canonical_id():
    subj.record_mapping(
        source_identifier="a",
        target_identifier="b",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="reviewed",
        created_by_principal="p",
    )
    subj.record_mapping(
        source_identifier="b",
        target_identifier="c",
        mapping_type=subj.MappingType.SAME_SUBJECT,
        basis="reviewed",
        created_by_principal="p",
    )
    assert subj.resolve_subject("a") == subj.resolve_subject("b") == subj.resolve_subject("c")
