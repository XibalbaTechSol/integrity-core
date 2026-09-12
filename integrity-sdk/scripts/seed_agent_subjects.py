"""
Seeds `agent_subjects.jsonl` with the two real correspondences the tri-repo
audit (2026-09-12) actually found on this machine's identity stores. NOT run
automatically by any test or CI step -- `record_mapping`'s
`created_by_principal` is meant to be the human who reviewed the evidence,
not the session that wrote the code. Run this yourself once, after reading
it, so the `created_by_principal` below reflects a real decision you made
rather than a session's own audit summary quoting itself as the reviewer.

Usage:
    cd integrity-sdk && .venv/bin/python scripts/seed_agent_subjects.py

Edit `PRINCIPAL` below to your own identifier first if you want something
other than your email in the audit trail.
"""

from integrity_sdk.agent_subject import (
    MappingType,
    SubjectConflictError,
    record_mapping,
)

PRINCIPAL = "jacob.v.universe@gmail.com"


def main() -> None:
    try:
        m1 = record_mapping(
            source_identifier="xibalba-shield",
            target_identifier="shield-replacement",
            mapping_type=MappingType.SAME_SUBJECT,
            basis=(
                "F2 reconciliation (tri-repo audit 2026-09-12): xibalba-shield "
                "(SDK store, did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4, "
                "unregistered on Base Sepolia, the label live processes actually use) and "
                "shield-replacement (CLI store, did:integrity:b3324032..., also unregistered) "
                "are two different label strings for what the user confirmed is the same "
                "intended Shield agent, created under the CLI's now-superseded flat storage "
                "before F2 unified both stores onto one location."
            ),
            created_by_principal=PRINCIPAL,
        )
        print(f"recorded: {m1.mapping_id} xibalba-shield <same_subject> shield-replacement")
    except SubjectConflictError as exc:
        print(f"skipped (already recorded / conflict): {exc}")

    try:
        m2 = record_mapping(
            source_identifier="xibalba",
            target_identifier="xibalba-healthcare-cli",
            mapping_type=MappingType.DISTINCT_SUBJECT,
            basis=(
                "F2 reconciliation (tri-repo audit 2026-09-12): SDK's 'xibalba' "
                "(did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861, "
                "general.integrity, registered Base Sepolia) and CLI's 'xibalba' -- renamed "
                "xibalba-healthcare-cli on migration -- "
                "(did:integrity:f96ae072..., healthcare.integrity, ComplianceGate.vertical()==1 "
                "verified via `cast call vertical()`, also registered Base Sepolia, ~21h apart) "
                "are two genuinely distinct, independently registered identities that only "
                "coincidentally shared the label 'xibalba' under the old CLI-only flat storage. "
                "User confirmed these are legitimately different registrations, not a collision "
                "to merge."
            ),
            created_by_principal=PRINCIPAL,
        )
        print(f"recorded: {m2.mapping_id} xibalba <distinct_subject> xibalba-healthcare-cli")
    except SubjectConflictError as exc:
        print(f"skipped (already recorded / conflict): {exc}")


if __name__ == "__main__":
    main()
