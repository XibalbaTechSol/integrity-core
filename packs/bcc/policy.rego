package integrity.pack

import rego.v1

# bcc_middleware's pre-execution policy (bcc_middleware/policies/bcc.rego) in the shared decision
# contract (integrity.decision/1): one `decision` value with ONE reason code.
#
# STAGE 1 OF THE BCC MIGRATION. bcc_middleware does not load this pack yet; it still queries
# bcc.rego. integrity-sdk/tests/unit/test_core_bcc_pack_equivalence.py runs both against a real OPA
# over a generated corpus and fails if they ever disagree, so this port cannot drift while both exist.
#
# How this differs from bcc.rego, and why each difference is deliberate:
#
# 1. One reason code, not a set of messages. bcc.rego collects every violation message and denies if
#    there are any; the contract carries a single `reason_code`. When several rules fire, the denial
#    reports the highest-priority one, by the fixed order in `_priority`. The set of denials is
#    unchanged (deny iff any rule fires); only which code is reported when several do is defined here.
#    Each code is the prefix bcc.rego already put before the colon in its message.
# 2. The clinical allowlist is `input.clinical_allowlist`, not `data.clinical_allowlist.agents`. A
#    signed pack is immutable and `OpaClient` owns what is installed in OPA, so a runtime data
#    document cannot be loaded beside it. The gate supplies the list as input instead. It is still
#    gate-supplied, not agent-supplied: a caller must never forward an agent's own claim here.
# 3. `requires_baa` is not an output. The decision contract admits exactly
#    {decision, reason_code, controls}, so the BAA signal moves to the gate, which keeps the same
#    clinical intent set in code and pins it to this file with a test (stage 2).
# 4. Free-text violation detail (agent id, tier numbers) is not in the result. The gate can format it
#    from its own input; a signed pack's result stays a stable code.
#
# 5. A commitment with no string `agent_id` or no string `intent_type` is denied outright
#    (BCC_MALFORMED_COMMITMENT, reported first). In Rego a rule that reads an absent field, or
#    negates a membership test on one (`not input.agent_id in S` is undefined, not true), silently
#    does not fire, so on such input bcc.rego allows: its allowlist rule is inert without an agent_id,
#    its tier and tool-risk rules cannot build their messages, and every intent_type rule is inert
#    without an intent_type. bcc_middleware never sends such a request (both are required, validated
#    fields), so this is not a live bypass; the pack simply refuses to treat "nothing matched because
#    nothing was there" as "permitted". Found by the equivalence harness, which pins the divergence.
#
# What is unchanged, deliberately and including its weaknesses: every rule's condition, the
# fail-closed defaults (a missing `verification_tier` is tier 0), and the "defense in depth, not
# DLP" status of the regex rules on `intent_type`. See bcc.rego for the reasoning behind each.

_clinical_intent_types := {
	"EMR_WRITE",
	"DISPENSE_MEDICATION",
	"BILLING_SUBMISSION",
	"SECURE_EMR_WRITE",
	"CLINICAL_DATA_ACCESS",
}

_static_clinical_agents := {
	"did:integrity:agent_scribe_01",
	"did:integrity:agent_billing_v1",
	"did:integrity:guardian_admin",
}

# Gate-supplied extra agents (see difference 2). Absent means none.
_authorized_clinical_agents := _static_clinical_agents | {a | some a in object.get(input, "clinical_allowlist", [])}

# Every rule below adds its code to this set; the decision is deny iff the set is non-empty.
_violations contains "BCC_MALFORMED_COMMITMENT" if not is_string(object.get(input, "agent_id", null))

_violations contains "BCC_MALFORMED_COMMITMENT" if not is_string(object.get(input, "intent_type", null))

_violations contains "HIPAA_ACCESS_CONTROL_VIOLATION" if {
	input.intent_type in _clinical_intent_types
	not object.get(input, "agent_id", "") in _authorized_clinical_agents
}

# A missing verification_tier must fail closed as tier 0, not leave the comparison undefined (which
# would make the rule silently not fire and so fail OPEN). Same reasoning as bcc.rego.
default _verification_tier := 0

_verification_tier := input.verification_tier

_min_tier_by_intent_type := {
	"DISPENSE_MEDICATION": 1,
	"BILLING_SUBMISSION": 1,
	"SECURE_EMR_WRITE": 1,
	"EMR_WRITE": 1,
	"CLINICAL_DATA_ACCESS": 1,
}

_violations contains "VERIFICATION_TIER_INSUFFICIENT" if {
	required := _min_tier_by_intent_type[input.intent_type]
	_verification_tier < required
}

_suspicious_patterns := {"exfiltrat", "backdoor", "spoof", "bypass"}

_violations contains "POLICY_VIOLATION" if {
	some pattern in _suspicious_patterns
	contains(lower(input.intent_type), pattern)
}

_violations contains "HIPAA_TECHNICAL_SAFEGUARD_FAILURE" if {
	regex.match(`\d{3}-\d{2}-\d{4}`, input.intent_type)
}

_agent_tool_prefixes := {"claude_tool", "hermes_tool"}

_is_agent_tool if {
	some prefix in _agent_tool_prefixes
	startswith(input.intent_type, sprintf("%v:", [prefix]))
}

_high_risk_tool_classes := {
	"destructive",
	"credential",
	"chain_write",
	"privileged",
	"financial",
}

_tool_risk_class := class if {
	_is_agent_tool
	parts := split(input.intent_type, ":")
	count(parts) >= 3
	class := parts[2]
}

_violations contains "TOOL_RISK_TIER_INSUFFICIENT" if {
	_tool_risk_class in _high_risk_tool_classes
	_verification_tier < 1
}

_has_value(val) if {
	not is_null(val)
	val != ""
}

_violations contains "AOS_VIOLATION" if {
	_is_agent_tool
	not _has_value(object.get(input, "trace_id", null))
}

_violations contains "AOS_VIOLATION" if {
	_is_agent_tool
	not _has_value(object.get(input, "span_id", null))
}

_violations contains "AOS_VIOLATION" if {
	_is_agent_tool
	rationale := object.get(input, "intent_rationale", object.get(input, "agent_thought", null))
	not _has_value(rationale)
}

_violations contains "AOS_VIOLATION" if {
	_is_agent_tool
	rationale := object.get(input, "intent_rationale", object.get(input, "agent_thought", null))
	_has_value(rationale)
	count(rationale) < 15
}

_token_budget_by_tier := {
	0: 10000,
	1: 100000,
	2: 1000000,
}

_violations contains "TOKEN_BUDGET_OPA" if {
	tier := object.get(input, "verification_tier", 0)
	budget := _token_budget_by_tier[tier]
	token_count := object.get(input, "token_count", 0)
	token_count > 0
	daily_spend := object.get(input, "daily_token_spend", 0)
	daily_spend + token_count > budget
}

# Reported when several rules fire: an unreadable request first, then identity and authorization, then input hygiene, then
# observability, then budget. A code missing from this list cannot be reported, which leaves the
# decision undefined and so falls to the pack's no_match default (deny): it fails closed.
_priority := [
	"BCC_MALFORMED_COMMITMENT",
	"HIPAA_ACCESS_CONTROL_VIOLATION",
	"VERIFICATION_TIER_INSUFFICIENT",
	"TOOL_RISK_TIER_INSUFFICIENT",
	"HIPAA_TECHNICAL_SAFEGUARD_FAILURE",
	"POLICY_VIOLATION",
	"AOS_VIOLATION",
	"TOKEN_BUDGET_OPA",
]

_primary := _priority[min({i | some i, code in _priority; code in _violations})] if count(_violations) > 0

_controls := {
	"HIPAA_ACCESS_CONTROL_VIOLATION": ["HIPAA-164.312(a)(1)"],
	"VERIFICATION_TIER_INSUFFICIENT": ["HIPAA-164.312(a)(1)"],
	"TOOL_RISK_TIER_INSUFFICIENT": ["HIPAA-164.312(a)(1)"],
	"AOS_VIOLATION": ["HIPAA-164.312(b)"],
}

decision := {
	"decision": "deny",
	"reason_code": _primary,
	"controls": object.get(_controls, _primary, []),
} if {
	input.event_class == "agent.tool_call"
	_primary
}

decision := {"decision": "permit", "reason_code": "BCC_POLICY_PERMIT", "controls": []} if {
	input.event_class == "agent.tool_call"
	count(_violations) == 0
}
