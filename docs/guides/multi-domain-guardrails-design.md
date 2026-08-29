# Multi-domain guardrails: design

> Status: design document. Nothing in this file has been implemented against
> `HIPAAGuardrailRegistry.sol` or `bcc.rego` — both are unchanged. This
> proposes how to generalize the existing single-domain (HIPAA) OPA+registry
> pattern into a pluggable, multi-domain one, grounded in what the repo
> already has: `contracts/src/framework/DomainRegistry.sol` (agents already
> join a `domainId`), `bcc_middleware`'s OPA integration, and
> `contracts/src/health/HIPAAGuardrailRegistry.sol`'s on-chain audit-anchor
> pattern.
>
> Source files read to ground this: `contracts/src/health/HIPAAGuardrailRegistry.sol`,
> `bcc_middleware/policies/bcc.rego`, `bcc_middleware/policies/bcc_test.rego`,
> `bcc_middleware/app/{main,opa_client,config,schemas,chain}.py`,
> `contracts/src/framework/{DomainRegistry,AgentPrimitivesFactory,XibalbaAgentRegistry}.sol`,
> `contracts/src/health/SmartBAAFactory.sol`, `docs/wiki/concepts/compliance-gate.md`,
> `docs/INTERFACE_CONTRACT.md` §7, and `integrity-oracle/backend/src/handlers.rs`
> (confirms `GET /v1/agent/{id}` already returns a server-verified `domain_id`).

## Part 1 — How production frameworks do pluggable, multi-domain guardrails

Surveyed: NVIDIA NeMo Guardrails, Guardrails AI, Meta LlamaGuard, OpenAI
Moderation API, AWS Bedrock Guardrails, Microsoft Presidio. Despite very
different implementations, they converge on the same four properties:

| Property | NeMo Guardrails | Guardrails AI | LlamaGuard | OpenAI Moderation | Bedrock Guardrails | Presidio |
|---|---|---|---|---|---|---|
| **(a) Domain/category-scoped** | Colang "rails" grouped by flow (jailbreak, topical, fact-checking, each its own `.co` file) | Validators grouped per RAIL spec / Hub category (PII, toxicity, competitor mentions, ...) | Single classifier, but its *taxonomy* (violence, hate, self-harm, ...) is itself category-scoped | Fixed category set (hate, harassment, self-harm, sexual, violence) — **not pluggable**, a fixed list | Named "guardrail configs": denied topics, content filters, word filters, PII entities — each independently configured per guardrail resource | Pluggable "recognizers," each scoped to one PII entity type (SSN, credit card, name, ...) |
| **(b) Independently enable/disable** | Rails are toggled per-flow in `config.yml` | Validators added/removed per Guard instance | N/A (one model, not decomposed) | N/A (fixed, not configurable) | Each filter/topic/word-list toggled per guardrail version | Recognizers registered/deregistered per `AnalyzerEngine` instance |
| **(c) Lifecycle evaluation point** | Explicit rail *types*: input rails (before LLM sees it), dialog rails (mid-conversation), output rails (before user sees it), execution rails (before/after tool calls) | Input guards (pre-prompt) and output guards (post-completion), run via `Guard.__call__` wrapping the LLM call | Typically both input (prompt) and output (completion) classification passes | Pre-generation call against user input (usually) | `ApplyGuardrail` API called at either INPUT or OUTPUT stage, explicit `source` param | Called wherever the integrating app chooses — typically pre-storage or pre-LLM-context |
| **(d) Structured verdict, not boolean** | Rail returns an action (`bot refuse`, `stop`) + which rail fired | `ValidationOutcome` (pass/fail per validator) + optionally a fixed/reasked value | Category label + severity, not just allow/deny | Per-category boolean flags + confidence scores, not one aggregate boolean | `{action: NONE\|GUARDRAIL_INTERVENED, assessments: [...]}` — one assessment per triggered policy, each naming which filter/topic fired and why | List of `RecognizerResult` (entity type, span, confidence) — a redaction plan, not a boolean |

**The common architectural shape**, stripped of vendor-specific vocabulary:

```
policy set (domain-scoped, independently toggleable)
        │
        ▼
evaluated at a named lifecycle hook (pre-request / pre-tool-call / post-response)
        │
        ▼
structured verdict: {allow|block|redact, reason(s), which-policy-fired}
```

This repo's existing `bcc.rego` + `bcc_middleware` + `HIPAAGuardrailRegistry`
already implements exactly this shape for **one** domain (HIPAA):

- **(a) domain-scoped** — hardcoded to `integrity.bcc`, HIPAA-only. No pluggability today.
- **(b) toggleable** — not per-policy; the whole bundle is load-or-don't.
- **(c) lifecycle point** — already correct and general: step 5 of `run_intercept` (`app/main.py`), pre-execution, evaluated once per `POST /v1/bcc/intercept`. This does not need to change.
- **(d) structured verdict** — already correct and general: `OPADecision{allow, violations, requires_baa}` (`app/opa_client.py`) is already an "allow/deny + reasons + a domain-specific obligation flag," not a bare boolean. This also does not need to change shape, only be extended (see Part 2).

So the generalization needed is narrowly about (a) and (b): make the policy
*bundle* domain-pluggable, and make bundle *selection* driven by which
domain(s) the requesting agent is actually in — not about redesigning the
request lifecycle or the verdict shape, both of which are already
industry-standard-shaped.

One divergence from every vendor surveyed, worth calling out because it's a
strength, not a gap to close: none of NeMo/Guardrails-AI/Bedrock/Presidio
anchor *which policy version* governed a given decision anywhere
tamper-evident — their audit trail is application logs. `HIPAAGuardrailRegistry`
already does something none of them do (an on-chain, third-party-verifiable
"policy version X was active when decision Y was made" record). The design
below preserves and generalizes that, it doesn't discard it.

## Part 2 — Design

### 2.0 The load-bearing constraint: domain selection must be server-resolved

`bcc.rego`'s own `verification_tier` gate is emphatic that
`input.verification_tier` must come from `resolve_verification_tier`
(oracle-resolved, "never client-asserted") rather than a field the
commitment itself carries — because a self-asserted tier is worthless as a
guardrail. The exact same failure mode applies to domain selection: if a
healthcare agent's commitment could simply say `"domain": "general"`, it
would evade every HIPAA rule by asserting the weakest bundle applies. A
*signed* domain field doesn't fix this either — the agent still picks which
bundle it wants held accountable to.

This repo already has the fix, and it's already wired: `AgentPrimitivesFactory
.registerPrimitives` requires a `domainId` and calls
`DomainRegistry.recordJoin`/`XibalbaAgentRegistry.registerPrimitives`, and
`integrity-oracle`'s `GET /v1/agent/{id}` already returns that `domain_id` —
re-verified against `XibalbaAgentRegistry.resolveDID` on-chain, per this
repo's "the chain is the source of truth" rule (`CLAUDE.md`, oracle section).
So domain resolution for guardrail purposes should be **oracle-resolved,
exactly like `resolve_verification_tier`**, not a field on `BCCCommitment`.

Design decision: bcc_middleware evaluates the **union** of:
1. A mandatory, always-on `general` baseline bundle (every agent, every domain), and
2. The domain-specific bundle for the agent's oracle-resolved `domain_id`.

A request is denied if *either* bundle denies. A commitment MAY optionally
carry a client-side `domain_hint` for logging/telemetry, but a hint can only
ever narrow which *additional* bundles get consulted for defense-in-depth —
it must never be used to skip the oracle-resolved domain's bundle. (Today,
`XibalbaAgentRegistry` stores exactly one `domainId` per agent, set at
registration — so in practice this is "general baseline + the agent's one
home-domain bundle," not an open-ended list. `DomainRegistry.isMember` is
already keyed generically enough that if the protocol later lets an agent
join multiple domains, this design extends to "general + every domain the
agent is a member of" with no further change.)

### 2.1 `bcc_middleware/policies/*.rego`: from one hardcoded bundle to domain-scoped bundles

Today `opa run --server policies/` loads the whole `policies/` directory as
one OPA server holding a single package, `integrity.bcc`. The generalization:

- **Keep `bcc.rego` and its package name (`integrity.bcc`) exactly as-is.**
  `docs/INTERFACE_CONTRACT.md` §7 pins `POST {OPA_URL}/v1/data/integrity/bcc/allow`
  as the cross-package contract endpoint (`integrity-sdk` calls this path
  directly, per `bcc_middleware/README.md`'s "Integration reconciliation" §1).
  Renaming the package would be a breaking cross-package change requiring a
  coordinated migration across `integrity-sdk`/`integrity-cli`, which is out
  of scope for a design doc. Instead, `integrity.bcc` becomes the **healthcare
  domain bundle** by convention/documentation (a comment at the top of the
  file noting this), not by a file or package rename. This is the one place
  this design deliberately does NOT "clean up" naming, in favor of not
  breaking a frozen interface.
- **New sibling bundles, each its own file + package**, following `bcc.rego`'s
  exact shape (`default allow := false`, `allow if count(violation) == 0`,
  `violation contains msg if {...}`, a `requires_*` signal rule where the
  domain needs one):
  - `policies/general.rego` — package `integrity.general`. Always-on
    baseline (see 2.4 for content).
  - `policies/finance.rego` — package `integrity.finance`. New finance
    vertical (see 2.4).
  - Future: `policies/<domain>.rego`, package `integrity.<domain>`, one file
    per domain, all loaded by the same `opa run --server policies/` (OPA
    loads every `.rego` file in the directory into one in-memory tree keyed
    by package — no per-file registration step needed).
- **Domain → package-path mapping** lives in `bcc_middleware`, not in Rego —
  Rego bundles stay domain-local and don't need to know about each other or
  about a routing table.

### 2.2 `GuardrailRegistry.sol`: single domain-parameterized registry, not a factory

The task prompt suggests checking whether a factory pattern (like
`AgentPrimitivesFactory`/`SmartBAAFactory`) fits here. It doesn't, and the
reason is instructive: `SmartBAAFactory` deploys a *new contract per pair*
because each BAA is its own escrow with independent collateral and a status
state machine — genuinely separate contract instances with separate balances.
`AgentPrimitivesFactory` clones because each agent must **self-own** its
primitives (that's the whole self-sovereignty argument in `CLAUDE.md`).
Neither reason applies here: a guardrail anchor is just data (a policy hash +
version + an audit log), and every domain's anchor is governed by the same
protocol-level admin/oracle roles, not owned per-agent or per-pair. Note also
that `ComplianceGateFactory` does **not** exist as a real contract in
`contracts/src/health/` today (only `script/FixComplianceGateFactory.s.sol`,
a deploy/ops script) — it isn't precedent to build on here.

The right shape mirrors `DomainRegistry.sol` itself: one registry, keyed by
`domainId` (`keccak256(bytes(domainName))`, reusing `DomainRegistry`'s own
hashing convention so a `domainId` means the same thing everywhere in the
protocol):

```solidity
// contracts/src/health/GuardrailRegistry.sol  (DESIGN ONLY — not implemented)
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title GuardrailRegistry
/// @notice Generalizes HIPAAGuardrailRegistry to be domain-parameterized: one
/// active-policy anchor + one audit log per domainId (the same bytes32
/// identifier DomainRegistry already mints via keccak256(bytes(domainName))),
/// instead of one hardcoded global HIPAA anchor. HIPAAGuardrailRegistry is
/// left in place, unmodified, as the "healthcare" domain's anchor for
/// backward compatibility with anything already pointed at it (e.g.
/// EHRGate's existing wiring, per compliance-gate.md) -- this is an
/// ADDITIONAL, general-purpose registry for every other domain, not a
/// replacement migration.
contract GuardrailRegistry is AccessControl {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    struct PolicyAnchor {
        bytes32 policyHash;
        string version;
        uint256 activeSince;
    }

    /// @dev domainId => currently active policy bundle for that domain.
    /// A domainId with policyHash == 0 has no active guardrail bundle
    /// (bcc_middleware should treat "no anchor" as "domain not yet
    /// on-chain-governed", NOT as "no guardrail" -- see §2.3 fail-closed note).
    mapping(bytes32 => PolicyAnchor) public activePolicy;

    struct AuditEntry {
        bytes32 domainId;
        address agent;
        // Generalizes HIPAAGuardrailRegistry's patientRecordHash: a
        // domain-neutral hash of whatever resource/subject the decision was
        // about (a patient record for healthcare, a transaction for
        // finance, a tool-call payload for general -- the caller decides
        // what "the subject" means per domain, this contract just anchors
        // its hash).
        bytes32 subjectHash;
        bytes32 policyHash;
        bool allowed;
        uint256 timestamp;
    }

    AuditEntry[] public auditLog;
    /// @dev domainId => indices into auditLog, for cheap per-domain audit queries.
    mapping(bytes32 => uint256[]) public auditLogByDomain;

    event PolicyActivated(bytes32 indexed domainId, bytes32 indexed policyHash, string version, uint256 timestamp);
    event AccessAudited(
        uint256 indexed entryIndex,
        bytes32 indexed domainId,
        address indexed agent,
        bytes32 subjectHash,
        bytes32 policyHash,
        bool allowed
    );

    error StalePolicyHash();
    error NoActivePolicy();

    constructor(address admin, address oracle) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        if (oracle != address(0)) _grantRole(ORACLE_ROLE, oracle);
    }

    function setActivePolicy(bytes32 domainId, bytes32 policyHash, string calldata version)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        activePolicy[domainId] = PolicyAnchor({policyHash: policyHash, version: version, activeSince: block.timestamp});
        emit PolicyActivated(domainId, policyHash, version, block.timestamp);
    }

    function anchorAccessAudit(bytes32 domainId, address agent, bytes32 subjectHash, bytes32 policyHashUsed, bool allowed)
        external
        onlyRole(ORACLE_ROLE)
        returns (uint256 entryIndex)
    {
        PolicyAnchor memory anchor = activePolicy[domainId];
        if (anchor.policyHash == bytes32(0)) revert NoActivePolicy();
        if (policyHashUsed != anchor.policyHash) revert StalePolicyHash();

        entryIndex = auditLog.length;
        auditLog.push(AuditEntry(domainId, agent, subjectHash, policyHashUsed, allowed, block.timestamp));
        auditLogByDomain[domainId].push(entryIndex);

        emit AccessAudited(entryIndex, domainId, agent, subjectHash, policyHashUsed, allowed);
    }

    function auditLogLength() external view returns (uint256) { return auditLog.length; }
    function auditLogLengthForDomain(bytes32 domainId) external view returns (uint256) {
        return auditLogByDomain[domainId].length;
    }
}
```

Deploy once (singleton, like `DomainRegistry`), register in
`deployments.local.json`'s `singletons` section (§6.6 shape), admin activates
a `PolicyAnchor` per domain as bundles are authored (`general`, `finance`,
...; `healthcare` stays on the existing `HIPAAGuardrailRegistry` unless/until
a deliberate migration ships). `bcc_middleware` computes
`policyHash = keccak256(concatenated .rego sources for that domain's bundle)`
the same way it presumably already does (or should) for
`HIPAAGuardrailRegistry.setActivePolicy` — this design doesn't change that
mechanic, just parameterizes it by `domainId`.

### 2.3 Minimal `bcc_middleware` change

Two files change; the request-lifecycle position (step 5 in `main.py`) does
not move.

**`app/chain.py`** — add a `resolve_agent_domain` function, same shape as
`resolve_verification_tier` (oracle-resolved, fails to a safe default rather
than raising, since a transient oracle hiccup must deny gracefully via the
`general` baseline still applying, not take down every commitment):

```python
def resolve_agent_domain(agent_id: str, *, oracle_url: str) -> str | None:
    """
    Server-verified domain_id for agent_id, from GET /v1/agent/{id} (the
    oracle already returns this -- see handlers.rs's AgentRecord.domain_id,
    re-verified against XibalbaAgentRegistry.resolveDID on-chain). Never
    client-asserted, same reasoning as resolve_verification_tier. Returns
    None (not a made-up domain) on any resolution failure -- the caller
    still evaluates the mandatory `general` bundle even when a vertical
    bundle can't be resolved; it must NOT skip domain-specific gating by
    inventing a default domain.
    """
    ...  # httpx GET, return data.get("domain_id"), except -> None
```

**`app/opa_client.py`** — parameterize `evaluate()` by package path (it
already takes `settings`, which already carries `opa_package_path`; add an
explicit `package_path: str` parameter instead of always reading
`settings.opa_package_path`), and add a small helper that evaluates a *list*
of domain package paths and combines verdicts:

```python
DOMAIN_PACKAGE_PATHS = {
    "general": "/v1/data/integrity/general",
    "healthcare": "/v1/data/integrity/bcc",   # unchanged path, see §2.1
    "finance": "/v1/data/integrity/finance",
}

async def evaluate_domains(settings: Settings, opa_input: dict, domain_ids: list[str]) -> OPADecision:
    """
    Evaluates the mandatory 'general' bundle plus each resolved domain's
    bundle, and combines them: allow only if every bundle allows: violations
    from every bundle that denied are concatenated (so a caller sees ALL
    reasons, not just the first). requires_baa is OR'd across bundles --
    generalizes cleanly since only the healthcare bundle sets it today and
    every other bundle's requires_baa defaults False (see schemas note in §2.4).
    An unreachable/malformed OPA response for ANY bundle in the list still
    raises OPAUnavailableError -- fail-closed is preserved per-bundle, not
    weakened by evaluating more than one.
    """
    ...
```

**`app/main.py`** step 5 becomes:

```python
domain_id = resolve_agent_domain(commitment.agent_id, oracle_url=settings.oracle_url)
domains_to_evaluate = ["general"] + ([domain_id] if domain_id else [])
decision = await opa_evaluate_domains(settings, opa_input, domains_to_evaluate)
```

Everything downstream of `decision` (circuit breaker recording, the BAA gate
keyed on `decision.requires_baa`, the deny-response shape) is unchanged —
`OPADecision` doesn't need new fields, only `evaluate_domains`'s combining
logic is new. This is the entire code-path change; nothing about signature
verification, nonce/replay, freshness, BAA, or Merkle batching moves.

**Backward compatibility note:** until `GuardrailRegistry.sol` is deployed
and `general.rego`/`finance.rego` exist, `domains_to_evaluate` degenerates to
`["general"]` (if a `general.rego` bundle is shipped) plus the healthcare
bundle for healthcare-domain agents — behaviorally identical to today for any
agent whose resolved domain is `healthcare`, since `integrity.bcc` is
untouched.

### 2.4 Two worked example bundles

Both follow `bcc.rego`'s exact shape: `default allow := false`,
`allow if count(violation) == 0`, `violation contains msg if {...}`, a
`requires_*` obligation rule where relevant, and a comment block explaining
the schema constraint they're working under (same discipline `bcc.rego`'s
header uses).

**`policies/general.rego` — the mandatory baseline every agent hits.**
Real, evaluable guardrails using only fields every `BCCCommitment` already
carries (`agent_id`, `intent_type`, `nonce`, `timestamp` — no domain-specific
fields needed, which is exactly why this is the "floor everyone hits"
bundle):

- Prompt-injection / control-token pattern rejection on `intent_type` (a
  free-text, attacker-controlled field, same threat model as `bcc.rego`'s
  §3 defense-in-depth regexes) — reject strings that look like an attempt to
  smuggle a system-prompt override (`"ignore previous instructions"`,
  `"disregard all prior"`, `system`/`assistant`-role token spoofing like
  `<|im_start|>`).
  This mirrors industry practice directly: NeMo's jailbreak-detection input
  rail and Bedrock's "denied topics"/word-filter guardrail both exist to
  catch exactly this class of string, structurally.
- A structural nonce-shape sanity check (`nonce` must be a plausible
  monotonic value, not e.g. `0` used as a sentinel bypass) as a second,
  independent layer on top of `nonce_store.py`'s runtime replay check —
  same "defense-in-depth over a field we actually have" principle `bcc.rego`
  already documents for its own regex checks.

**`policies/finance.rego` — a new regulated vertical, same shape as HIPAA's.**
Given the BCC schema's hash-only design (no raw payload crosses the wire pre-
execution, same constraint `bcc.rego`'s header explains for PHI), a finance
bundle is structurally identical to the HIPAA one: it cannot inspect a real
transaction amount from `intended_state_hash` alone, so — exactly like
`bcc.rego` — it splits into (1) structural rules over fields actually present
(`intent_type` allowlisting for finance-flavored intents, e.g.
`TOKEN_TRANSFER`, `CONTRACT_CALL_PAYMENT`) and (2) defense-in-depth regex over
`intent_type` for sanctioned-address or exfiltration-shaped strings an
attacker might smuggle into the label itself:

```rego
package integrity.finance

import rego.v1

default allow := false
allow if { count(violation) == 0 }

finance_intent_types := {"TOKEN_TRANSFER", "CONTRACT_CALL_PAYMENT", "MARKET_ORDER"}

# Placeholder for a real sanctioned-address list -- in production this would
# be an OPA data document synced from an OFAC/Chainalysis feed, same
# "should be a data document, not hand-maintained" note bcc.rego's §1 makes
# for its clinical allowlist.
default _sanctioned_addresses := []
_sanctioned_addresses := data.sanctions.addresses

violation contains msg if {
    some addr in _sanctioned_addresses
    contains(lower(input.intent_type), lower(addr))
    msg := sprintf("FINANCE_SANCTIONS_VIOLATION: intent_type references sanctioned address '%v'", [addr])
}

requires_finance_review if {
    input.intent_type in finance_intent_types
}
default requires_finance_review := false
```

`requires_finance_review` is the finance-domain analog of `bcc.rego`'s
`requires_baa` — a signal `bcc_middleware` could use to gate a future
transaction-amount check the same way `requires_baa` gates the on-chain BAA
call today (out of scope to build here; flagged as the natural next hook).

## Summary of what would actually change vs. stay fixed

| Piece | Stays as-is | Changes |
|---|---|---|
| `HIPAAGuardrailRegistry.sol` | Unmodified, remains the healthcare domain's anchor | — |
| `bcc.rego` / package `integrity.bcc` | Unmodified — stays the healthcare bundle, keeps its frozen §7 path | Documented (comment) as "the healthcare domain bundle" |
| Request lifecycle (`main.py` steps 0–7) | Position/order of the OPA check (step 5) unchanged | Step 5 now evaluates a domain-resolved list of bundles instead of one hardcoded path |
| `OPADecision` shape | `{allow, violations, requires_baa}` unchanged | None — `requires_baa` still just means "healthcare bundle's obligation," generalizable per-bundle without a schema change |
| New: `GuardrailRegistry.sol` | — | New singleton, `domainId`-keyed, mirrors `DomainRegistry`'s hashing + `HIPAAGuardrailRegistry`'s anchor/audit pattern |
| New: `policies/general.rego`, `policies/finance.rego` | — | New domain bundles, same shape as `bcc.rego` |
| Domain resolution | `resolve_verification_tier`'s oracle-resolved, fail-safe pattern | New sibling `resolve_agent_domain`, same pattern, using the oracle's already-returned `domain_id` |

## Suggested wiki entry (not added by this task — left for the wiki-log owner)

A new `docs/wiki/concepts/multi-domain-guardrails.md` (or an extension to
`compliance-gate.md`) cross-linking: `DomainRegistry` (existing),
`HIPAAGuardrailRegistry` (existing, now "the healthcare instance of the
pattern"), this design's `GuardrailRegistry` (proposed), and `bcc.md`. Should
note the load-bearing decision in §2.0 (domain must be server-resolved via
the oracle, never client-asserted) since that's the one property most likely
to be gotten wrong by a future implementer under time pressure.
