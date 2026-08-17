# Ecosystem landscape tracking + adoption strategy (2026-08-17)

**Status:** initial tracking doc, not yet acted on. Written from web/X research done
2026-08-17, not independently verified against each project's own contracts/docs the way
`PRODUCTION_GAPS.md` §27 or the ERC-8004 audit in `spec/integrity-protocol-v3.2.md` §1.2
were. Treat every claim below as "reported by search results," not confirmed.

## 1. Why this exists

Two sessions of research (competitor landscape, then live August 2026 checks) surfaced a
fast-moving field around AI agent identity/reputation/compliance. The goal here is to turn
that into (a) something worth re-checking on a cadence rather than re-discovering from
scratch each time, and (b) a short list of integration targets ranked by adoption leverage,
not a feature race against every entrant.

## 2. Regulatory driver (dates matter — check first)

**EU AI Act high-risk provisions became enforceable 2026-08-02** — risk management, data
governance, logging, transparency, human oversight, cybersecurity resilience, post-market
monitoring. Reported scope explicitly includes agent-invoked API calls (MCP servers named)
and extends the compliance boundary through a whole chain of agents, not just the
user-facing one. This is a live deadline inside the current build window, not a future one
— worth citing directly in Integrity Health material if not already, and worth re-reading
the Act's actual text (not just secondary coverage) before making specific compliance claims.

McKinsey's 2026 AI Trust survey (reported, not independently read): 77% of orgs have written
AI agent policies, 26% can enforce them. This is the sharpest available framing for the
kernel's actual thesis — governance-as-document vs. governance-as-enforced-constraint — and
is a better lead line than a feature comparison against Semantica/Trulioo-style audit trails.

## 3. Landscape, by category (re-verify before quoting externally)

| Project | Category | One line | Relevance |
|---|---|---|---|
| ERC-8004 (standard) | Identity/DID | 3 on-chain registries: identity, reputation, validation | Already the standard §3.1 "bridges, not adopts" — re-verify Validation Registry mainnet status (see §4 below), this may have changed since the whitepaper's audit |
| ChaosChain (Nethermind+Hetu+Hyperbolic) | Infra for ERC-8004 | L1/L2 built for 8004 registry availability under agent load; "Genesis Studio" first end-to-end commercial 8004 prototype (identity+work+USDC payment+IP) | Infra layer, not a direct competitor — potential integration/interop target if we ever expose the ERC-8004 adapter live |
| Injective Agents | Identity/DID, live | Every agent gets on-chain identity via ERC-8004 directly, "portable reputation" | Funded L1 already doing what our adapter route targets — worth a direct comparison once our adapter exists |
| Know Your Agent (KYA) | Identity/DID, live product | "Identity layer for the agent economy," built on AWP protocol, live on Base | Went from directory site (Jan 2026 snapshot) to live product by Aug 2026 — re-check its actual mechanism, may or may not have stake/slashing |
| Cloudflare + GoDaddy | Web-infra identity/permissioning | Websites decide which AI agents can access their data at the web layer | Not a compliance/reputation competitor — a potential *gate* agents pass through regardless of identity layer carried; worth tracking as a distribution chokepoint |
| FIDO Alliance | Standards body | Formed Agentic Authentication Technical Working Group (announced 2026-04-28) | Could become the "boring, everyone-adopts-it" enterprise baseline the way WebAuthn did for human auth — high leverage if it gains traction, currently early |
| Visa TAP / Mastercard Agent Pay | Payments-identity | Agent authentication at payment rails | Adjacent, not a compliance layer — track for interop only if Integrity agents need payment-rail legitimacy |
| Semantica | Compliance/audit (see [[semantica_competitor]]) | PROV-O provenance/reasoning, zero identity/reputation/stake | Same buyer as Integrity Health, different mechanism — parity-not-feature-race per existing memory |
| Trulioo + Worldpay Digital Agent Passport | Compliance/audit | KYC-style credential bundle: provenance + behavior telemetry, 5 verification layers | Closest branding match to "compliance layer," from identity-verification incumbents — likely the nearest buyer-overlap to Semantica from a different angle |
| MCP (Anthropic) | Protocol, not a company | Becoming default tool-authorization surface for agent-to-enterprise-system access | Not a competitor at all — a surface our kernel's constraint story may eventually need to speak to, since a lot of real tool-calls will flow through it regardless of chain-level identity |

## 4. Open fact-check (do before the next spec revision touches identity)

`spec/integrity-protocol-v3.2.md` §1.2 states ERC-8004's Validation Registry has "no
confirmed mainnet deployment on any studied chain" — this was the load-bearing evidence for
the "bridge, not adopt" identity decision (§3.1's `PROPOSED NORMATIVE CHANGE`). 2026-08-17
research reports reference deployments went live on Ethereum mainnet in late January 2026
with a "growing set" of registered identities by Q2. **Re-verify directly against the
registry contracts** (not secondary coverage) before either (a) restating the "no mainnet
deployment" claim in a future revision, or (b) treating this as grounds to revisit the
bridge-not-adopt decision — the decision's other stated triggers (§3.1's own list: a
counterparty requiring native registration, or cross-chain portability becoming a live
requirement) haven't independently changed just because the registry itself deployed.

## 5. Integration targets, ranked by adoption leverage (not by feature parity)

Ranked by "how much easier does this make it for someone to *start trusting* an Integrity
agent without doing new work," not by technical interest:

1. **Ship and document the versioned Integrity identity read profile (§3.1 route b).**
   **Completed locally 2026-08-17:** `IntegrityIdentityReadV1` resolves existing DID-backed
   agents without migration and is wired into future genesis deployments. Primary-source and
   adversarial review rejected the earlier generic-tooling premise: this is not an ERC-8004 or
   ERC-721 adapter, so Injective/ChaosChain-adjacent tooling needs a custom integration unless
   and until native convergence is implemented. Existing Base Sepolia remains unchanged.
2. **Watch FIDO's Agentic Authentication WG for a draft spec, don't build against it yet.**
   Too early to integrate; worth a calendar re-check (see §6) rather than work now.
3. **Confirm MCP compatibility of agent identity resolution** — if Xibalba agents are
   already MCP-server-shaped (per this repo's own `mcp_server.py`), check whether an
   external MCP client can resolve an agent's DID/AIS through the existing tool surface
   without new code, or what the gap is. Low-cost to check, not yet done.
4. **Do not chase Cloudflare/GoDaddy integration yet** — it's a distribution chokepoint
   worth tracking, not an API surface with an obvious integration point today. Revisit if
   their agent-permissioning spec becomes concrete and public.
5. **Do not build toward Visa TAP/Mastercard Agent Pay** unless a real payment-rail use case
   emerges for an Integrity agent — currently speculative.

## 6. Re-check cadence

No automated tracking exists (was not set up in this session — would need a scheduled
research job, not attempted here). Manual trigger points instead:
- Before any spec revision that touches §3.1 (identity) — re-run the fact-check in §4 first.
- Before any GTM/pitch material update — re-verify the EU AI Act enforcement framing and the
  McKinsey stat against primary sources, not this doc's secondhand summary.
- Roughly quarterly, or whenever a named project in §3 is mentioned again in unrelated
  research — that's a signal it's gaining traction and worth a fresh look.
