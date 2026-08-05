package integrity.bcc_test

import data.integrity.bcc
import rego.v1

# Run with: opa test . -v   (from bcc_middleware/)

_base_commitment := {
	"agent_id": "did:integrity:some_generic_agent",
	"intent_type": "payment",
	"intended_state_hash": "0x1111111111111111111111111111111111111111111111111111111111111",
	"nonce": 1,
	"timestamp": 1730000000000,
	# Tier 1 is what every real, oracle-registered agent has (see bcc.rego's
	# min_tier_by_intent_type doc comment) -- the realistic default for a
	# generic test fixture representing "a normal registered agent."
	"verification_tier": 1,
	"trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
	"span_id": "00f067aa0ba902b7",
	"intent_rationale": "Verifiable public intent rationale validating agent compliance and intent.",
	# Token budget defaults: 0 spend means no budget violation in existing tests.
	"token_count": 0,
	"daily_token_spend": 0,
}

test_ordinary_payment_is_allowed if {
	bcc.allow with input as _base_commitment
}

test_ordinary_payment_does_not_require_baa if {
	not bcc.requires_baa with input as _base_commitment
}

test_clinical_action_by_unauthorized_agent_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "EMR_WRITE", "agent_id": "did:integrity:random_unlisted_agent"})
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "HIPAA_ACCESS_CONTROL_VIOLATION")
}

test_clinical_action_requires_baa if {
	commitment := object.union(_base_commitment, {"intent_type": "EMR_WRITE", "agent_id": "did:integrity:random_unlisted_agent"})
	bcc.requires_baa with input as commitment
}

test_clinical_action_by_allowlisted_agent_is_allowed if {
	commitment := object.union(_base_commitment, {"intent_type": "EMR_WRITE", "agent_id": "did:integrity:agent_scribe_01"})
	bcc.allow with input as commitment
}

test_clinical_action_by_allowlisted_agent_still_requires_baa if {
	# allow=true doesn't mean the BAA gate is skipped -- bcc_middleware runs
	# both checks; requires_baa should be true regardless of allowlist status.
	commitment := object.union(_base_commitment, {"intent_type": "DISPENSE_MEDICATION", "agent_id": "did:integrity:agent_scribe_01"})
	bcc.allow with input as commitment
	bcc.requires_baa with input as commitment
}

test_exfiltration_keyword_in_intent_type_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "exfiltrate_customer_records"})
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "POLICY_VIOLATION")
}

test_bypass_keyword_in_intent_type_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "bypass_safety_guardrail"})
	not bcc.allow with input as commitment
}

test_backdoor_keyword_in_intent_type_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "install_backdoor_access"})
	not bcc.allow with input as commitment
}

test_spoofed_keyword_in_intent_type_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "spoofed_telemetry_report"})
	not bcc.allow with input as commitment
}

test_ssn_shaped_intent_type_is_denied if {
	commitment := object.union(_base_commitment, {"intent_type": "123-45-6789"})
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "HIPAA_TECHNICAL_SAFEGUARD_FAILURE")
}

test_non_clinical_agent_can_still_do_ordinary_data_access if {
	commitment := object.union(_base_commitment, {"intent_type": "data_access", "agent_id": "did:integrity:some_random_agent"})
	bcc.allow with input as commitment
	not bcc.requires_baa with input as commitment
}

# ---------------------------------------------------------------------------
# Verification-tier gate
# ---------------------------------------------------------------------------

test_allowlisted_agent_with_tier_0_is_denied_for_clinical_intent if {
	# Same allowlisted agent/intent_type as test_clinical_action_by_allowlisted_agent_is_allowed
	# above, but tier 0 (e.g. bcc_middleware couldn't resolve this agent from the
	# oracle) -- allowlist membership alone must not be sufficient once the tier
	# gate is in play.
	commitment := object.union(_base_commitment, {
		"intent_type": "EMR_WRITE",
		"agent_id": "did:integrity:agent_scribe_01",
		"verification_tier": 0,
	})
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "VERIFICATION_TIER_INSUFFICIENT")
}

test_allowlisted_agent_with_tier_1_is_allowed_for_clinical_intent if {
	commitment := object.union(_base_commitment, {
		"intent_type": "EMR_WRITE",
		"agent_id": "did:integrity:agent_scribe_01",
		"verification_tier": 1,
	})
	bcc.allow with input as commitment
}

test_missing_verification_tier_fails_closed_for_clinical_intent if {
	# object.union with a base that already has verification_tier can't easily
	# construct an object missing the key, so build directly to omit it entirely
	# -- proves the `default _verification_tier := 0` fallback (not a hard OPA
	# error) is what makes an absent field deny, per bcc.rego's doc comment on
	# why referencing input.verification_tier directly would silently fail open.
	commitment := {
		"agent_id": "did:integrity:agent_scribe_01",
		"intent_type": "EMR_WRITE",
		"intended_state_hash": "0x1111111111111111111111111111111111111111111111111111111111111",
		"nonce": 1,
		"timestamp": 1730000000000,
	}
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "VERIFICATION_TIER_INSUFFICIENT")
}

test_non_clinical_intent_is_unaffected_by_tier_0 if {
	# min_tier_by_intent_type only covers the clinical set -- an intent_type not
	# in that map must not be gated by tier at all (no entry => no violation).
	commitment := object.union(_base_commitment, {"verification_tier": 0})
	bcc.allow with input as commitment
}

# ---------------------------------------------------------------------------
# Agent-runtime tool intents (bcc.rego §3b)
# ---------------------------------------------------------------------------
# Regression guard for the measured failure these rules exist to fix: the Claude
# Code hook set emitted a CONSTANT `claude_tool:<Tool>` label, which matched no
# rule, so the gate authorized 715 commitments and denied 0. The first test below
# pins that unclassified labels still pass (we did not make the shell unusable);
# the rest pin that a classified one can actually be denied.

test_unclassified_claude_tool_intent_is_allowed if {
	commitment := object.union(_base_commitment, {"intent_type": "claude_tool:Bash"})
	bcc.allow with input as commitment
	# No risk class parsed out of a two-segment label.
	not bcc.tool_risk_class with input as commitment
}

test_destructive_tool_class_is_parsed if {
	commitment := object.union(_base_commitment, {"intent_type": "claude_tool:Bash:destructive"})
	bcc.tool_risk_class == "destructive" with input as commitment
}

test_destructive_tool_intent_allowed_for_verified_agent if {
	# Tier 1 = the oracle resolved and verified this DID. A registered agent is
	# permitted to commit to destructive work; the value is the COMMITMENT, which
	# PostToolUse can later be reconciled against.
	commitment := object.union(_base_commitment, {"intent_type": "claude_tool:Bash:destructive"})
	bcc.allow with input as commitment
}

test_destructive_tool_intent_denied_for_unverifiable_agent if {
	commitment := object.union(_base_commitment, {
		"intent_type": "claude_tool:Bash:destructive",
		"verification_tier": 0,
	})
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "TOOL_RISK_TIER_INSUFFICIENT")
}

test_credential_and_chain_write_classes_are_high_risk if {
	cred := object.union(_base_commitment, {
		"intent_type": "claude_tool:Bash:credential",
		"verification_tier": 0,
	})
	chain := object.union(_base_commitment, {
		"intent_type": "claude_tool:Bash:chain_write",
		"verification_tier": 0,
	})
	not bcc.allow with input as cred
	not bcc.allow with input as chain
}

test_low_risk_tool_class_is_not_tier_gated if {
	# `network` is classified for audit visibility but is not in
	# high_risk_tool_classes -- it must not be denied even at tier 0, or routine
	# curl/git-push calls would brick the shell for any unresolvable agent.
	commitment := object.union(_base_commitment, {
		"intent_type": "claude_tool:Bash:network",
		"verification_tier": 0,
	})
	bcc.allow with input as commitment
}

test_missing_tier_fails_closed_for_high_risk_tool_class if {
	# Same fail-closed property the clinical rules have: an absent
	# verification_tier must deny, not silently skip the comparison.
	commitment := {
		"agent_id": "did:integrity:some_generic_agent",
		"intent_type": "claude_tool:Bash:destructive",
		"intended_state_hash": "0x1111111111111111111111111111111111111111111111111111111111111",
		"nonce": 1,
		"timestamp": 1730000000000,
	}
	not bcc.allow with input as commitment
}

test_hermes_tool_namespace_reaches_the_same_rules if {
	# The Hermes runtime executed entirely ungated while Claude Code was gated,
	# under the same DID. Both namespaces must hit one ruleset -- if this ever
	# regresses to a claude-only prefix, Hermes silently goes unpoliced again.
	commitment := object.union(_base_commitment, {
		"intent_type": "hermes_tool:terminal:destructive",
		"verification_tier": 0,
	})
	not bcc.allow with input as commitment
	bcc.tool_risk_class == "destructive" with input as commitment
	bcc.tool_runtime == "hermes_tool" with input as commitment
}

test_tool_runtime_is_surfaced_for_both_namespaces if {
	claude := object.union(_base_commitment, {"intent_type": "claude_tool:Bash:network"})
	hermes := object.union(_base_commitment, {"intent_type": "hermes_tool:terminal:network"})
	bcc.tool_runtime == "claude_tool" with input as claude
	bcc.tool_runtime == "hermes_tool" with input as hermes
	# Both allowed: `network` is classified for visibility, not gated.
	bcc.allow with input as claude
	bcc.allow with input as hermes
}

test_aos_missing_trace_id_is_denied if {
	commitment := {
		"agent_id": "did:integrity:agent_scribe_01",
		"intent_type": "claude_tool:Bash",
		"intended_state_hash": "0x1111111111111111111111111111111111111111111111111111111111111",
		"nonce": 1,
		"timestamp": 1730000000000,
		"verification_tier": 1,
		"span_id": "00f067aa0ba902b7",
		"intent_rationale": "Reasoning monologue validation.",
	}
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "AOS_VIOLATION")
}

test_aos_missing_thought_is_denied if {
	commitment := {
		"agent_id": "did:integrity:agent_scribe_01",
		"intent_type": "claude_tool:Bash",
		"intended_state_hash": "0x1111111111111111111111111111111111111111111111111111111111111",
		"nonce": 1,
		"timestamp": 1730000000000,
		"verification_tier": 1,
		"trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
		"span_id": "00f067aa0ba902b7",
	}
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "AOS_VIOLATION")
}

# ---------------------------------------------------------------------------
# Token Budget tests
# ---------------------------------------------------------------------------

test_token_budget_under_limit_is_allowed if {
	commitment := object.union(_base_commitment, {
		"token_count": 5000,
		"daily_token_spend": 3000,
		"verification_tier": 0,
	})
	# 3000 + 5000 = 8000 < 10000 (tier 0 budget) → allowed
	bcc.allow with input as commitment
}

test_token_budget_at_limit_is_denied if {
	commitment := object.union(_base_commitment, {
		"token_count": 5000,
		"daily_token_spend": 6000,
		"verification_tier": 0,
	})
	# 6000 + 5000 = 11000 > 10000 (tier 0 budget) → denied
	not bcc.allow with input as commitment
	some msg in bcc.violation with input as commitment
	contains(msg, "TOKEN_BUDGET_OPA")
}

test_token_budget_tier1_allows_large_spend if {
	commitment := object.union(_base_commitment, {
		"token_count": 50000,
		"daily_token_spend": 40000,
		"verification_tier": 1,
	})
	# 40000 + 50000 = 90000 < 100000 (tier 1 budget) → allowed
	bcc.allow with input as commitment
}

test_token_budget_zero_count_is_not_checked if {
	commitment := object.union(_base_commitment, {
		"token_count": 0,
		"daily_token_spend": 9999,
		"verification_tier": 0,
	})
	# token_count=0 means no usage event → budget rule does not fire
	bcc.allow with input as commitment
}

