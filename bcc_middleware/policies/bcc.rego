package integrity.bcc

import rego.v1

# Xibalba Integrity Protocol -- BCC pre-execution policy gate.
#
# Evaluated by bcc_middleware for every POST /v1/bcc/intercept, per
# docs/INTERFACE_CONTRACT.md §7 (queried as `/v1/data/integrity/bcc`, the
# package root -- see bcc_middleware/app/opa_client.py for why we read the
# whole document instead of only the `/allow` leaf).
#
# *** SCHEMA CONSTRAINT THAT SHAPES THIS WHOLE FILE ***
# The old prototype's HIPAA policy scanned a free-text "actual_context"
# blob for PHI (SSNs, DOBs, emails...) via regex. The new BCC Commitment
# schema (§4.2) intentionally does NOT carry that raw payload across the
# wire pre-execution -- only `intended_state_hash` (a sha256 digest) does,
# by design, so plaintext PHI never has to leave the agent to be gated.
# That means this policy CANNOT regex-scan real PHI content anymore -- it
# only ever sees: agent_id, intent_type, intended_state_hash, nonce,
# timestamp. So the rules below are split into two kinds:
#   1. Structural rules over fields we actually have (access control by
#      intent_type + agent allowlist; replay/expiry is enforced in Python,
#      not here, since it needs wall-clock state).
#   2. Defense-in-depth regex rules over `intent_type` itself (still a
#      free-text field an attacker controls) -- these catch someone trying
#      to smuggle exfiltration/spoofing keywords or PHI-shaped strings into
#      the label field itself. They are NOT a replacement for real payload
#      DLP, which is out of scope for a hash-only commitment.

default allow := false

allow if {
	count(violation) == 0
}

# ---------------------------------------------------------------------------
# 1. Clinical action allowlist (HIPAA § 164.312(a)(1) access control)
# ---------------------------------------------------------------------------
# Intent types that touch clinical/PHI systems may only be performed by
# agents on the allowlist below.
#
# PRODUCTION NOTE: this allowlist is hardcoded for the demo/local-dev scope
# of this rewrite. In production it should be an OPA `data` document kept in
# sync with the on-chain DomainRegistry/ReputationRegistry contracts (via
# integrity-oracle), not maintained by hand in this file -- flagged in the
# package README.
clinical_intent_types := {
	"EMR_WRITE",
	"DISPENSE_MEDICATION",
	"BILLING_SUBMISSION",
	"SECURE_EMR_WRITE",
	"CLINICAL_DATA_ACCESS",
}

# Static demo/local-dev allowlist. Kept for the three fixed demo DIDs the
# policy tests reference, but UNIONed with a runtime-provided data document
# (`data.integrity.bcc.authorized_clinical_agents`) so a real agent with a
# real Ed25519-derived DID — e.g. integrity-demo's clinical agent, or in
# production the set integrity-oracle keeps in sync with the on-chain
# DomainRegistry/ReputationRegistry — can be authorized WITHOUT editing this
# file by hand. This is the exact "should be an OPA data document" fix the
# PRODUCTION NOTE above calls for; the static set below is now just the
# built-in fallback, not the only source.
_static_clinical_agents := {
	"did:integrity:agent_scribe_01",
	"did:integrity:agent_billing_v1",
	"did:integrity:guardian_admin",
}

# Runtime-provided extra agents live at a DISTINCT top-level data path
# (`data.clinical_allowlist.agents`), not under this policy's own
# `integrity.bcc` package. Two things matter here:
#   - It must be a distinct path: referencing `data.integrity.bcc.<same-name>`
#     from a rule of that same name is a self-reference OPA rejects.
#   - It must be a DIRECT path reference (`data.clinical_allowlist.agents`),
#     not `object.get(data, ...)`: the latter depends on the entire `data`
#     root — including this very rule — which is also a recursion.
# A `default` rule keeps a completely absent document (the common local case)
# as an empty list rather than an undefined-reference error.
default _extra_clinical_agents := []

_extra_clinical_agents := data.clinical_allowlist.agents

authorized_clinical_agents := _static_clinical_agents | {a | some a in _extra_clinical_agents}

violation contains msg if {
	input.intent_type in clinical_intent_types
	not input.agent_id in authorized_clinical_agents
	msg := sprintf(
		"HIPAA_ACCESS_CONTROL_VIOLATION: agent '%v' is not on the clinical allowlist for intent_type '%v'",
		[input.agent_id, input.intent_type],
	)
}

# ---------------------------------------------------------------------------
# 1b. Verification-tier gate (docs/wiki/concepts/identity-ceiling.md)
# ---------------------------------------------------------------------------
# `input.verification_tier` is resolved by bcc_middleware (app/chain.py's
# resolve_verification_tier) from the oracle's SERVER-VERIFIED value -- never
# client-asserted, see integrity-oracle/backend/src/handlers.rs's
# SERVER_VERIFIED_TIER. An unresolvable agent (unknown DID, oracle down)
# resolves to tier 0, so this rule fails closed for anyone it can't verify.
#
# CEILING NOTE: only Tier 1 exists as an achievable value today -- Tiers 2/3
# have no built verification path (see identity-ceiling.md), so `min_tier`
# values below are deliberately capped at 1. Requiring tier >= 1 is NOT a
# no-op: it denies any commitment from an agent the oracle can't resolve/
# verify, as defense-in-depth on top of (not a replacement for) the explicit
# allowlist above -- e.g. it still catches a misconfigured allowlist entry
# for a DID that was never actually registered. Raise these thresholds once
# Tier 2/3 verification is real; until then, higher values would either be a
# permanent no-op (nobody could ever reach them) or, worse, look like a real
# policy decision when it can't actually be enforced yet.
min_tier_by_intent_type := {
	"DISPENSE_MEDICATION": 1,
	"BILLING_SUBMISSION": 1,
	"SECURE_EMR_WRITE": 1,
	"EMR_WRITE": 1,
	"CLINICAL_DATA_ACCESS": 1,
}

# `input.verification_tier` is always sent by bcc_middleware (see main.py), but this
# policy must not silently fail OPEN for a commitment that omits it -- referencing an
# absent `input` field directly makes the comparison below undefined rather than
# false, which would make the whole violation rule silently not fire (no violation
# recorded) instead of denying. `default` + override gives a real fail-closed 0.
default _verification_tier := 0

_verification_tier := input.verification_tier

violation contains msg if {
	required := min_tier_by_intent_type[input.intent_type]
	_verification_tier < required
	msg := sprintf(
		"VERIFICATION_TIER_INSUFFICIENT: agent '%v' has tier %v, intent_type '%v' requires tier >= %v",
		[input.agent_id, _verification_tier, input.intent_type, required],
	)
}

# ---------------------------------------------------------------------------
# 2. requires_baa signal
# ---------------------------------------------------------------------------
# Tells bcc_middleware whether this commitment falls into the
# healthcare/BAA-covered vertical, so it knows to also run the on-chain BAA
# check (app/baa.py) -- a chain call we don't want to make for every
# request, only ones that are actually healthcare-flavored.
requires_baa if {
	input.intent_type in clinical_intent_types
}

default requires_baa := false

# ---------------------------------------------------------------------------
# 3. Defense-in-depth regex checks on intent_type (see header note)
# ---------------------------------------------------------------------------
suspicious_patterns := {
	"exfiltrat": "possible data exfiltration reference",
	"backdoor": "possible unauthorized backdoor/contract-manipulation reference",
	"spoof": "possible telemetry/hardware fingerprint spoofing reference",
	"bypass": "possible safety-control bypass reference",
}

violation contains msg if {
	some pattern, explanation in suspicious_patterns
	contains(lower(input.intent_type), pattern)
	msg := sprintf("POLICY_VIOLATION: intent_type '%v' matches '%v' (%v)", [input.intent_type, pattern, explanation])
}

# Belt-and-suspenders: if an SSN-shaped string somehow ends up in the
# intent_type label itself (it should never carry real payload data, but
# labels are attacker-controlled free text), block it outright rather than
# silently accept it.
violation contains msg if {
	regex.match(`\d{3}-\d{2}-\d{4}`, input.intent_type)
	msg := "HIPAA_TECHNICAL_SAFEGUARD_FAILURE: intent_type contains an SSN-shaped string"
}

# ---------------------------------------------------------------------------
# 3b. Agent-runtime tool intents (`claude_tool:<Tool>[:<risk_class>]`)
# ---------------------------------------------------------------------------
# Measured motivation, not a hypothetical: across 792 logged decisions from the
# Claude Code hook set, this policy authorized 715 and denied 0. Every rule above
# keys on `intent_type`, and the hook emitted the CONSTANT label
# `claude_tool:<ToolName>` -- which matches no rule, so `violation` was always
# empty and `allow` always true. The engine was healthy the whole time
# (`claude_tool_bypass` and `EMR_WRITE` deny correctly); it was simply never
# reachable. A gate that cannot express an opinion is not a gate.
#
# The hook (~/.claude/xibalba/pretool_gate.py::classify_intent) now appends a
# coarse risk class derived from the payload, while the payload itself still
# crosses the wire only as `intended_state_hash`. That keeps §4.2's hash-only
# property -- plaintext never leaves the agent -- while giving these rules a
# bounded, enumerable value to match on.
#
# SCOPE, stated plainly: the classifier is a one-way lossy SIGNAL and is
# trivially evadable by an adversarial agent (base64, indirection, aliasing).
# These rules therefore encode "the agent committed to doing something
# destructive" and gate on that assertion -- they are not, and must not be
# described as, a sandbox. Real containment is the runtime's job.
# One namespace per agent runtime, all reaching the SAME rules. The runtime is
# encoded in the label rather than given its own ruleset, because the failure this
# whole section exists to fix was two runtimes under one DID having two different
# behavioral guarantees. Duplicated rules are how that drift happens; a shared
# rule with a runtime-tagged label keeps them honest AND lets an auditor see which
# runtime committed to what.
agent_tool_prefixes := {"claude_tool", "hermes_tool"}

_is_agent_tool if {
	some prefix in agent_tool_prefixes
	startswith(input.intent_type, sprintf("%v:", [prefix]))
}

# Surfaced for audit logging: which runtime made this commitment.
tool_runtime := runtime if {
	_is_agent_tool
	runtime := split(input.intent_type, ":")[0]
}

# Risk classes that require an agent to be verifiable before it may commit to
# them. Tier >= 1 means the oracle could resolve and verify the DID at all (see
# the CEILING NOTE above); an agent it cannot resolve falls to 0 and is denied.
#
# "financial" added 2026-08-19 for xibalba-quant (autonomous trading agent,
# PRODUCTION_GAPS.md-adjacent work, see docs/plans/): before this, an
# `intent_type` of e.g. `hermes_tool:coinbase_trade:financial` matched NO
# rule in this file at all -- `violation` stayed empty by construction, and
# the commitment was authorized because nothing looked at it, not because
# anything approved it. That is the exact "792 logged decisions... denied 0"
# failure this section's own history above already names once. Kept at
# tier >= 1, same as every other class here, for the same reason the CEILING
# NOTE above states: tier 2/3 verification isn't real yet, so requiring it
# would be an unreachable no-op dressed up as a real policy decision, not an
# actual stricter gate. Raise this specifically once a real, earnable higher
# tier exists and there's a reason financial actions should sit above the
# others.
#
# What this rule does NOT and cannot check, stated plainly (per this file's
# own header note): the commitment schema never carries the actual trade
# payload across the wire pre-execution, only `intended_state_hash` -- so
# there is no venue/asset/size/side field here to validate. Trade-level
# input validation (a well-formed venue, a sane size) is the trade-executor's
# own job before it ever builds a commitment; this rule only gates identity
# verifiability and (via `_is_agent_tool` below) requires a real declared
# trace_id/span_id/intent_rationale for every financial action, same as
# every other agent-tool commitment.
high_risk_tool_classes := {
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

violation contains msg if {
	_tool_risk_class in high_risk_tool_classes
	_verification_tier < 1
	msg := sprintf(
		"TOOL_RISK_TIER_INSUFFICIENT: agent '%v' has tier %v; intent_type '%v' is class '%v' and requires tier >= 1",
		[input.agent_id, _verification_tier, input.intent_type, _tool_risk_class],
	)
}

# Surfaced for audit logging so an operator can see which commitments carried a
# risk class at all, distinguishing "passed policy" from "matched no rule".
tool_risk_class := _tool_risk_class

# ---------------------------------------------------------------------------
# 4. NOT implemented here, on purpose: READ_ONLY-vs-destructive intent drift
# ---------------------------------------------------------------------------
# The old prototype flagged a READ_ONLY commitment that later tried a
# "delete" action by scanning the actual execution context for the string
# "delete". We have no equivalent signal here: `/v1/bcc/intercept` only ever
# sees the pre-execution commitment (intent_type is a single fixed label,
# not a stream of runtime actions), so there is nothing to compare it
# against at this layer. Detecting that kind of drift needs a *second*
# call after execution (or a runtime action log) that isn't part of the
# §4.2 schema today -- flagged in the README as a gap for integration to
# resolve, rather than faked here with a rule that can never fire.

# ---------------------------------------------------------------------------
# 5. AOS Observability & Chain-of-Thought (CoT) Gating
# ---------------------------------------------------------------------------
_has_value(val) if {
	not is_null(val)
	val != ""
}

violation contains msg if {
	_is_agent_tool
	not _has_value(object.get(input, "trace_id", null))
	msg := "AOS_VIOLATION: missing OpenTelemetry trace_id in execution context"
}

violation contains msg if {
	_is_agent_tool
	not _has_value(object.get(input, "span_id", null))
	msg := "AOS_VIOLATION: missing OpenTelemetry span_id in execution context"
}

violation contains msg if {
	_is_agent_tool
	rationale := object.get(input, "intent_rationale", object.get(input, "agent_thought", null))
	not _has_value(rationale)
	msg := "AOS_VIOLATION: agent tool execution requires a non-empty intent_rationale (legacy agent_thought)"
}

violation contains msg if {
	_is_agent_tool
	rationale := object.get(input, "intent_rationale", object.get(input, "agent_thought", null))
	_has_value(rationale)
	count(rationale) < 15
	msg := sprintf("AOS_VIOLATION: intent_rationale is too brief (%v chars); requires >= 15 chars of declared intent", [count(rationale)])
}

# ---------------------------------------------------------------------------
# 6. Token Budget Policy (declarative audit check)
# ---------------------------------------------------------------------------
# Per-tier daily token budget (tokens/day). -1 = unlimited.
# The Python-layer TokenBudgetEnforcer is the authoritative enforcer and
# tracks cumulative spend. This OPA rule is a secondary declarative check
# that fires when both token_count AND daily_token_spend are present in
# the input -- useful for audit logging the budget state at decision time.
# ---------------------------------------------------------------------------
_token_budget_by_tier := {
    0: 10000,
    1: 100000,
    2: 1000000
}

violation contains msg if {
    tier := object.get(input, "verification_tier", 0)
    budget := _token_budget_by_tier[tier]
    token_count := object.get(input, "token_count", 0)
    token_count > 0
    daily_spend := object.get(input, "daily_token_spend", 0)
    daily_spend + token_count > budget
    msg := sprintf(
        "TOKEN_BUDGET_OPA: tier %v daily budget (%v tokens) would be exceeded (spend=%v + this=%v = %v > %v)",
        [tier, budget, daily_spend, token_count, daily_spend + token_count, budget]
    )
}

# ---------------------------------------------------------------------------
# Metadata rule: surfaced by bcc_middleware for audit logging (see
# app/opa_client.py's OPADecision.violations).
# ---------------------------------------------------------------------------
