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

**MATERIAL UPDATE 2026-08-26 (see Changelog):** the "became enforceable 2026-08-02" framing
above needs a caveat, not a rewrite. What actually took effect 2026-08-02 was the
transparency-obligation tier (GPAI disclosure, deepfake/AI-content labeling, chatbot
"you're talking to AI" notices) plus the Commission/AI Office's enforcement posture generally.
The *high-risk* Annex III regime specifically (risk management, data governance, logging,
human oversight — the tier this doc's Integrity Health framing leans on) had its conformity
deadline pushed from 2026-08-02 to 2026-12-02 by the "Digital Omnibus" amendment (Regulation
(EU) 2026/1744, entered into force 2026-07-27). Substance unchanged, only the date the
high-risk obligations start biting. Re-verify against the Act's actual text/Official Journal
entry before citing an immediate high-risk deadline in GTM material — see Changelog for
sources.

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

**RESOLVED 2026-08-26 (partially — see Changelog for sources):** checked the primary source
(`erc-8004/erc-8004-contracts` repo, the 8004 team's own deployment registry) directly rather
than secondary press. Its own README distinguishes IdentityRegistry and ReputationRegistry —
both deployed at fixed addresses (`0x8004A169...`, `0x8004BAa1...`) and replicated across 40+
EVM networks including Ethereum mainnet — from the **Validation Registry**, which the same
README flags with its own caution: "still under active update and discussion with the TEE
community... will be revised and expanded in a follow-up spec update later this year," with
only "basic request/response operations" currently supported and no stable mainnet address
listed alongside the other two. So the v3.2 §1.2 claim was accurate as of 2026-08-17 and
remains *substantially* accurate for the Validation Registry specifically — identity and
reputation are live and widely replicated, but validation is not yet a finalized, deployed
singleton the way the whitepaper's critique implies for the standard as a whole. This is
narrower than what most secondary coverage ("all three registries live") reports — worth
citing the primary repo, not the press summary, in any future spec revision. Does not by
itself change the bridge-not-adopt decision's other triggers, per (b) above.

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
3. **Confirm MCP compatibility of agent identity resolution — CHECKED 2026-08-17, real gap
   found.** `integrity_sdk/mcp_server.py`'s `integrity_resolve_did` (the only DID-resolution
   MCP tool) calls `GET /v1/agent/{id}` (`handlers::get_agent`), whose `AgentResponse`
   struct (`handlers.rs:228`) carries `id`, `verification_tier`, `last_nonce`,
   `has_ed25519_key`/`has_eth_address`, `primitives`, `oracle_registered` — no `ais` field.
   AIS is served exclusively by the separate `GET /v1/agent/{id}/ais`
   (`handlers::get_ais`), which has **zero corresponding MCP tool**. So today: an external
   MCP client CAN resolve identity (DID, registration state, verification tier) through the
   existing surface with no new code, but CANNOT resolve reputation/AIS the same way — the
   exact half of the "resolve an Integrity agent" story that matters for the adoption thesis
   (identity without reputation is what §1.2 critiques ERC-8004 for). Fix, if wanted: add a
   read-only `integrity_get_ais` tool mirroring `integrity_resolve_did`'s exact pattern
   (`GET /v1/agent/{id}/ais`, defaults to the server's own DID) — small, same shape as the
   existing read-only tools, not attempted here since it wasn't asked for, just the gap
   confirmed.
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

## Changelog

### 2026-08-26 — Ecosystem watch: ERC-8004 Validation Registry status + EU AI Act high-risk deadline delay

Automated research sweep (scheduled tracking run). Two material findings, both resolving or
materially updating existing open items; landscape table in §3 unchanged (no new named
competitor combining identity + staked reputation + compliance gating surfaced this sweep —
checked Microsoft's `agent-governance-toolkit` [OSS, launched 2026-04-02] specifically since
it combines DID-based identity with compliance/policy gating, but it uses non-economic "trust
scoring," not staked/slashable reputation, so it doesn't match the specific combination this
repo occupies and wasn't added to §3).

1. **§4 fact-check (a) partially resolved.** Checked the primary source directly
   (`erc-8004/erc-8004-contracts` GitHub repo, the ERC-8004 team's own deployment listing)
   rather than secondary press. IdentityRegistry and ReputationRegistry are deployed at fixed
   addresses and replicated across 40+ EVM networks including Ethereum mainnet (since
   2026-01-29). The Validation Registry is explicitly *not* in that same deployed-address
   list — the repo's own README states that section of the spec "is still under active
   update and discussion with the TEE community" and will be "revised and expanded in a
   follow-up spec update later this year," with only basic request/response operations
   implemented so far. Net: most secondary coverage ("all three ERC-8004 registries live on
   mainnet") overstates the Validation Registry's status specifically; see the inline
   `RESOLVED 2026-08-26` note in §4 for full detail.
   Sources: [erc-8004/erc-8004-contracts](https://github.com/erc-8004/erc-8004-contracts),
   [ERC-8004: Trustless Agents (EIP)](https://eips.ethereum.org/EIPS/eip-8004),
   [Forbes, AI Agents Gain Trust Via Ethereum: ERC-8004 On Mainnet (2026-02-05)](https://www.forbes.com/sites/digital-assets/2026/02/05/ai-agents-gain-trust-via-ethereum-erc-8004-on-mainnet/).

2. **EU AI Act: high-risk (Annex III) deadline delayed to 2027-12-02, not immediate.**
   The "Digital Omnibus on AI" amendment (Regulation (EU) 2026/1744) completed its EU
   legislative process (Parliament backing 2026-06-16, Council approval 2026-06-29, signed
   2026-07-08, published in the Official Journal 2026-07-24, entered into force 2026-07-27)
   and pushes the high-risk Annex III systems conformity deadline from 2026-08-02 to
   2026-12-02 — a 16-month delay, rationale being that harmonised standards weren't ready,
   not that the substantive requirements changed. What *did* take effect on schedule on
   2026-08-02 was the transparency-obligation tier (GPAI disclosure, AI-content/deepfake
   labeling, chatbot disclosure) and the AI Office's general enforcement posture (up to 3% of
   global revenue in fines). Material because this doc's §2 cited the immediate 2026-08-02
   date as blanket "high-risk provisions became enforceable" without this carve-out — see the
   inline `MATERIAL UPDATE 2026-08-26` note added to §2. Worth re-checking primary EU sources
   (not this changelog) before any GTM claim about an imminent high-risk deadline.
   Sources: [Consilium press release, Council and Parliament agree to simplify and streamline rules (2026-05-07)](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/),
   [Cloud Security Alliance, EU AI Act High-Risk Deadline Pushed to December 2027](https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-omnibus-vii-deadline-delay-20260/),
   [Help Net Security, EU begins enforcing AI Act (2026-08-04)](https://www.helpnetsecurity.com/2026/08/04/eu-ai-act-enforcement-ai-models/),
   [European Commission, Commission starts enforcing AI Act rules and new transparency requirements on 2 August](https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august).

Not material / considered and not added: Microsoft `agent-governance-toolkit` (see above, no
staking mechanism); Sumsub/MetaComp KYA framework developments (April 2026, predates this
doc's dateline, no stake/slashing mechanism reported); Trulioo+Worldpay Digital Agent Passport
(no update since original tracking, partnership dates to 2025-08-14); routine funding-round
coverage of general agent-security startups (Zenity, Norm AI, HappyRobot) — adjacent
enterprise-IAM/compliance space but none combine on-chain identity + staked/slashable
reputation + compliance gating, so none meet this doc's specific competitor bar.
