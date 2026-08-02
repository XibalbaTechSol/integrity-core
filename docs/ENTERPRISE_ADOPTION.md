# Enterprise Adoption Roadmap — the Compliance ↔ LLM Layer

Integrity Protocol sits between an enterprise's **compliance obligations** and its **LLM/agent
actions**: agents commit to an intent, the gate authorizes or denies it against policy before
execution, and every decision is cryptographically attested and audit-logged. The hard
engine — policy gate, BCC-signed attestation, AIS reputation, ZK proofs, on-chain anchoring,
the Shield HIPAA vertical — already exists. The adoption gap is almost entirely **packaging**:
how the layer integrates, how policy is authored, how evidence is exported, and how it deploys
in a regulated environment.

This document is the granular map from *strategic lever* → *concrete implementation surface in
this repo* → *status* → *next step*, so architectural decisions can be made against real files
rather than abstractions. Ordered by adoption leverage. Keep it current as tranches land.

Legend: ✅ shipped · 🔨 in progress · ⬜ not started

---

## Lever 1 — Transparent interception (change where the layer sits in the call path)

**Problem.** Today `bcc_middleware` is a pre-execution API the agent must *explicitly* call
(`POST /v1/bcc/intercept`, driven by `integrity-sdk` / `integrity-cli`). No enterprise rebuilds
its agents around a "please remember to call our gate" contract. Adoption requires **drop-in
interception** with near-zero agent code change.

**Target form factors.**
- **(a) LLM-I/O proxy shim** — an OpenAI/Anthropic-compatible endpoint that proxies to the real
  provider and runs the commitment gate on tool-call / completion boundaries. One base-URL env
  var to adopt.
- **(b) Tool-call egress sidecar** — intercepts *actions* (the outbound HTTP/tool calls an agent
  makes) rather than LLM tokens. Language-agnostic, deployed as a sidecar container.

**Implementation surface.** New package `bcc-proxy/` (or a new entrypoint in `bcc_middleware`)
that reuses `run_intercept()` unchanged — `app/main.py::run_intercept` is already factored out
of the HTTP handler precisely so a non-HTTP entrypoint can reuse it (see its docstring). The
proxy translates an intercepted call into a `BCCCommitment` and calls `run_intercept`.

**Status.** ⬜ Not started. **Next step:** spike the egress sidecar (b) first — it's
provider-agnostic and demoable against the existing `demo/` scenario engine.

---

## Lever 2 — Shadow (monitor-only) mode — the risk-free on-ramp ✅

**Problem.** A pre-execution gate that blocks is a scary first deployment. Enterprises adopt
security/compliance tooling in *monitor* mode first (Cloudflare, Snyk, OPA-gatekeeper all did),
watch what it would have caught, then enforce.

**What shipped.** `BCC_SHADOW_MODE=true` (config `Settings.shadow_mode`). When on, the gate runs
the **full** authorization gauntlet and records every would-be decision, but never blocks and
never trips the circuit breaker:
- A commitment enforcement would deny returns `authorized=True, enforced=False,
  shadow_would_deny=True` with the would-be reason preserved in `reason`.
- The would-be denial is still written to the durable audit trail as
  `decision="shadow_deny"` (distinct from a real enforced `deny`), via `app/audit.py`.
- `GET /health` reports `mode: "enforce" | "shadow"`.

**Files.** `bcc_middleware/app/config.py` (flag), `app/schemas.py` (`enforced`,
`shadow_would_deny`, health `mode`), `app/main.py` (`_deny` / `_record_violation` shadow-aware),
`tests/test_shadow_mode.py` (5 tests), `.env.example`. **Dashboard surface:**
`integrity-dashboard/src/components/diagnostics/AuditLogsPanel.tsx` renders `shadow_deny` as an amber
"Would-be block" row and counts them separately in the summary.

**Status.** ✅ Shipped, tested (96/96 suite green). **Next step:** per-request shadow override
(header) so a single agent can be canaried into enforcement while the fleet stays in shadow;
and a dashboard toggle/time-series of would-be blocks (Lever 6 evidence surface).

---

## Lever 3 — Policy authoring in the buyer's language (compliance packs)

**Problem.** OPA/Rego (`bcc_middleware/policies/*.rego`) is powerful but the buyer is a compliance
officer, not a Rego programmer. Selling a *framework mapping* ("47 of the EU AI Act's high-risk
controls, out of the box") beats selling a policy engine.

**Implementation surface.** A `policies/packs/` layout: versioned, framework-tagged Rego bundles
(`hipaa/`, `soc2/`, `eu_ai_act/`, `finra/`, `pci/`) loaded as OPA data documents alongside the
base policy — the clinical allowlist already proves the data-document pattern
(`policies/bcc.rego`'s `data.clinical_allowlist.agents`). Each control maps to a stable ID so
evidence export (Lever 6) can cite it. Longer term: a natural-language → Rego compiler and a
compliance-officer UI in the Dashboard.

**Status.** ⬜ Not started. **Next step:** extract the existing healthcare intent gating into a
first `packs/hipaa/` bundle with control IDs, as the template for the rest.

---

## Lever 4 — Auditability / cryptographic evidence, framed as compliance artifacts

**Problem.** The BCC signatures + Merkle anchoring + ZK are a real moat — but an auditor wants a
*signed evidence report mapped to controls*, not a chain explorer. This is the highest-value
enterprise feature and it's mostly a packaging job on primitives that already exist.

**Implementation surface.** The durable audit trail already exists end-to-end:
`bcc_middleware/app/audit.py` → oracle `POST /v1/audit/ingest` → `GET /v1/audit-log` →
`AuditLogsPanel`. Add an **evidence export**: a signed, control-mapped report
(agent × intent × decision × policy-control × Merkle-anchor tx) exportable as PDF/JSON for a
date range. De-emphasize "Base L2 / blockchain" in the enterprise framing (reads as risk to a
CISO); emphasize "tamper-evident, cryptographically verifiable audit log."

**Status.** 🔨 Scoped — full design in `docs/design/evidence-export.md` (chain-of-custody,
phased plan, files to touch, test plan, open questions). Underlying trail is real and queryable
today; `audit_log.metadata` already exists as the anchor-linkage slot (no migration needed).
**Next step:** sign off the two open questions (anchor back-fill vs. export-time join; HIPAA-only
vs. multi-framework v1), then build Phase A (persist decision→leaf→anchor linkage).

---

## Lever 5 — Deployment sovereignty (non-negotiable for regulated buyers)

**Problem.** Healthcare/finance will not send prompts or PHI to a vendor cloud or a public chain.
Requires VPC/on-prem deploy, BYO-key, data residency, and a **private/permissioned** anchor
option. The current single-operator Base Sepolia testnet (all roles = one key, see root
`CLAUDE.md` "Live deployment") is a non-starter for a regulated sale as-is.

**Implementation surface.** Config is already fully env-var driven (`app/config.py`,
`RPC_URL`/`DEPLOYMENTS_FILE` switch chains). Needed: (a) an off-chain / permissioned-ledger
anchoring backend behind `app/anchor.py`'s interface; (b) key-separation (the `reputation_signer`
/ `anchor_signer` split is already stubbed in config for when production key-separation happens);
(c) a hardened Helm/compose deploy. Vendor's own posture — **SOC 2 Type II + signable BAA** — is
table-stakes trust and belongs on this roadmap even though it's not code.

**Status.** ⬜ Not started. **Next step:** abstract `app/anchor.py` behind an anchor-backend
interface so "public chain" is one implementation, not the only one.

---

## Lever 6 — Lead vertical, generalize later (Shield/HIPAA is the wedge)

**Problem.** Enterprises adopt horizontal infra reluctantly but buy *vertical compliance
solutions* eagerly. Don't sell "trust layer for the agentic economy" to a hospital — sell
"HIPAA guardrails + audit evidence for your AI agents," win it undeniably, then generalize the
same primitives to finance/legal.

**Implementation surface.** The Shield vertical already exists on both sides:
`contracts/src/shield/*` (ComplianceGate, CoveredEntityRegistry, EHRGate, SmartBAA(Factory),
HIPAAGuardrailRegistry), the on-chain BAA gate in `bcc_middleware` (`app/baa.py` +
`policies/bcc.rego` healthcare intent types), and `ShieldPage` in the Dashboard. The wedge work is
GTM + the evidence export (Lever 4) and HIPAA pack (Lever 3) aimed at one named buyer persona.

**Status.** 🔨 Primitives exist; productization not started. **Next step:** a HIPAA-specific
evidence report + a compliance-officer view in `ShieldPage` that reads the real audit trail.

---

## Lever 7 — Xibalba Shield as its own product (device & network security)

**Problem.** "Xibalba Shield" currently names only the HIPAA/healthcare vertical inside this
repo (`contracts/src/shield/*`). Device/network security research (2026-08-01, drawn from a
Perplexity project session — full technical spec at
[`spec/xibalba-shield-v1.md`](../spec/xibalba-shield-v1.md)) identified a real, undefended
wedge: kernel-level agent discovery and enforcement on the endpoint, combined with
Integrity-backed actuarial evidence, is a combination none of the current AI-agent-security
vendors own — identity-governance players (Astrix, CyberArk) don't touch the endpoint;
enterprise EDR/XDR (CrowdStrike, SentinelOne, Microsoft) don't produce cryptographically
attributable decisions.

**Decision.** Xibalba Shield splits into two things going forward, recorded normatively in
[`spec/integrity-protocol-v0.4.md`](../spec/integrity-protocol-v0.4.md) §14.1:
1. The existing HIPAA vertical, unchanged, still in this repo.
2. A **new product in a new repository**, `XibalbaTechSol/xibalba-shield` — an endpoint agent
   (kernel/OS sensor, local policy engine, LLM/agent guardrail hooks) that consumes
   `integrity-sdk` exactly as any third-party agent runtime would, with zero dependency in the
   other direction.

**Implementation surface.** None of it lives in this repo by design (§14.1's whole point is
architectural separation), so there is nothing to point at here. What *does* live here and is
directly reusable: the egress-sidecar shape from Lever 1b is the same interception pattern
Shield's endpoint agent needs; `run_intercept()`'s HTTP-handler-independent factoring
(Lever 1) is the precedent for how Shield calls into the gate without duplicating its logic;
the evidence-export path (Lever 4) is what Shield's compliance reporting reuses rather than
building its own (Shield spec §11).

**Status.** ⬜ Not started — no repository exists yet. **Next step:** create
`XibalbaTechSol/xibalba-shield`, scaffold the layout in Shield spec §2, and build the Linux
agent core + eBPF sensor first (Shield spec §14's build order), independent of everything else
on this roadmap.

---

## Lever 8 — Agentic payment-protocol interop

**Problem.** External agentic-commerce protocols (AP2, ACP, x402, MPP, Coral) standardize *how*
an agent pays; none of them decide *whether it's allowed to*, under whose authority, or produce
regulator-grade evidence that it did. That gap is structurally the same gap Integrity Protocol
already closes for every other action type via Delegation (§4.3/§12) and BCC (§11) — full
mapping and a financial `intent_type` taxonomy now live in
[`spec/integrity-protocol-v0.4.md`](../spec/integrity-protocol-v0.4.md) §21.

**Implementation surface.** The financial `intent_type` taxonomy (protocol spec §21.2,
`docs/INTERFACE_CONTRACT.md` §15.1) requires **zero schema change** to start using — `BCC
Commitment.intent_type` already accepts any string. What's genuinely new work: adapters that
translate an AP2 Payment Mandate / ACP checkout session / x402 capability / Coral escrow
condition into a BCC commitment before the underlying rail executes (protocol spec §21.3's
interop table names each mapping). A first adapter (x402, the simplest — a single signed
capability token per payment) is the natural pilot; it validates the pattern before building
the other four.

**Status.** ⬜ Not started. **Next step:** land the `intent_type` taxonomy as a policy-pack
convention (reuses Lever 3's `packs/` layout) before writing any adapter code, so the vocabulary
is stable before five external protocols start depending on it.

---

## Sequencing

1. ✅ **Shadow mode** (Lever 2) — done; the on-ramp everything else rides on.
2. 🔨 **Evidence export** (Lever 4) + **HIPAA pack** (Lever 3) — turn the real audit trail into
   an auditor-ready, control-mapped artifact for the Shield vertical wedge (Lever 6).
3. ⬜ **Egress sidecar** (Lever 1b) — remove integration friction so shadow mode can sit in front
   of real traffic with no agent changes; also the direct precedent for Lever 7's endpoint agent.
4. ⬜ **Sovereignty** (Lever 5) — anchor-backend abstraction + key separation for a regulated
   deployment.
5. ⬜ **Xibalba Shield product** (Lever 7) — new repository, independent build track; start once
   Lever 1b's interception pattern is proven, since Shield's endpoint agent needs the same shape.
6. ⬜ **Payment-protocol interop** (Lever 8) — taxonomy first, one adapter (x402) to validate,
   then the remaining four; lowest urgency of the numbered levers, highest optionality (costs
   nothing to defer since the taxonomy alone requires no schema change).

Each tranche is one focused PR with real tests, updated here and in `docs/wiki/` per
`.agents/AGENTS.md`. No silent mocks — shipped rows are real and tested, everything else is an
honestly marked ⬜/🔨 gap.
