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

**CORRECTION 2026-08-28 (see Changelog):** the date in the note directly above is wrong by
one year — it should read **2027-12-02**, not 2026-12-02 (the note's own "16-month deferral"
math from 2026-08-02 lands in December 2027, not December 2026; this looks like a transcription
slip in the 2026-08-26 run, not a substantive correction). Multiple independent sources
(the Council of the EU's own final-approval press release, plus Gibson Dunn, White & Case, and
Sidley client alerts) confirm: standalone Annex III high-risk obligations are deferred to
**2 December 2027** (16-month deferral), and AI embedded in regulated products under Annex I
separately to **2 August 2028** (12-month deferral, not previously noted in this doc at all).
See Changelog for full sourcing. Do not cite "2026-12-02" anywhere downstream.

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

### 2026-08-28 — Ecosystem watch: correction to 2026-08-26's EU AI Act date; no other material change

Automated research sweep (scheduled tracking run, ~2 days after the prior run). Landscape
table in §3 unchanged — swept all nine named players plus a general sweep for a new entrant
combining identity + staked reputation + compliance gating; nothing found meets this doc's
materiality bar (see "not material" list below). One correction to a prior entry:

1. **Correction to the 2026-08-26 changelog entry's EU AI Act date.** That entry stated the
   Digital Omnibus pushed the Annex III high-risk conformity deadline to "2026-12-02." This is
   a one-year transcription error — independent confirmation from the Council of the EU's own
   final-approval press release plus three law-firm client alerts all give **2 December 2027**
   (a 16-month deferral from the original 2026-08-02 date — consistent with the prior entry's
   own "16-month" language, just the wrong year attached). Separately, and not previously
   captured in this doc at all: AI embedded in regulated products under **Annex I** gets its
   own, later deferral to **2 August 2028** (12 months from the original 2027-08-02 date).
   Inline correction added to §2 above (marked `CORRECTION 2026-08-28`, original erroneous
   note left visible per this doc's own convention).
   Sources: [Consilium, Council gives final green light to simplify and streamline rules (2026-06-29)](https://www.consilium.europa.eu/en/press/press-releases/2026/06/29/artificial-intelligence-council-gives-final-green-light-to-simplify-and-streamline-rules/),
   [Gibson Dunn, EU AI Act Omnibus Agreement — Postponed High-Risk Deadlines](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/),
   [White & Case, EU agrees Digital Omnibus deal to simplify AI rules](https://www.whitecase.com/insight-alert/eu-agrees-digital-omnibus-deal-simplify-ai-rules),
   [Sidley, EU Lawmakers Reach Provisional Agreement to Delay Key EU AI Act Obligations](https://datamatters.sidley.com/2026/06/22/eu-lawmakers-reach-provisional-agreement-to-delay-key-eu-ai-act-obligations/),
   [Axios, The EU AI Act gets real (2026-08-28)](https://www.axios.com/2026/08/28/eu-ai-act-gets-real) (the piece that
   surfaced the discrepancy in the first place, by citing "December 2027" against this doc's
   then-current "2026-12-02").

2. **§4 fact-check (a), ERC-8004 Validation Registry: no change since 2026-08-26.** Re-checked;
   Identity/Reputation registries remain live on 40+ EVM networks including Ethereum mainnet,
   Validation Registry remains explicitly under active spec revision per the same primary repo,
   no new mainnet address published. Status unchanged from the 2026-08-26 entry.

Not material / considered and not added: Injective Institutional Services' SEC transfer-agent
registration (effective 2026-08-19) — securities-transfer-agent status, unrelated to the
identity/reputation/compliance combination tracked here; Anthropic's enterprise-managed MCP
connector authorization GA (2026-08-24) — org-level IdP-gated tool-connector provisioning, not
agent identity/reputation resolution, so an evolution of the already-tracked MCP row rather
than a new fact; BNBAgent SDK / ERC-8183 (BNB Chain, escrow + UMA optimistic-oracle dispute
resolution for agent task settlement) — dates to 2026-03-18, predates this doc, and combines
identity with escrow/arbitration rather than staked/slashable reputation or compliance gating;
Vouched's "Know Your Agent" / Agent Reputation Directory — dates to 2025, reputation is
community-reported rather than staked/slashable, no compliance-gating component; Offroad ($7M
seed, 2026-06-04) and SecureAuth Agentic Authority Platform (2026-05) — enterprise agent-IAM
governance plays, no staking/slashing or compliance-vertical gating. None meet this doc's
specific competitor bar.

### 2026-09-01 — Ecosystem watch: possible direct-combination entrant found (Observer Protocol), KYA stake/slash question partly resolved, everything else unchanged

Automated research sweep (scheduled tracking run, ~4 days after the prior run; branch
`audit/harness-loop-2026-07-30` had been merged into `main` and deleted since the last run, so
this run recreated it from `main` before continuing — the tracked file itself has also moved
from `docs/plans/` to `docs/archive/2026-08/plans/` since 2026-08-17, note for future runs).
Re-swept all nine named §3 players plus both §4 fact-checks; both are unchanged since
2026-08-28 (ERC-8004 Identity/Reputation live on 40+ EVM networks, Validation Registry still
under active spec revision, no new mainnet address; EU AI Act Annex III deadline still
2027-12-02 per the 2026-08-28 correction, nothing newer surfaced). One likely-material finding
and one partial resolution, both **lower-confidence than usual** because this session's network
egress proxy blocked direct fetches of every primary source involved
(`observerprotocol.org`, `agentecon.ai`, `kya.link` all returned `EGRESS_BLOCKED`) — everything
below is secondary-source-only and needs a primary-source check from an unrestricted session
before being treated as settled, more so than this doc's usual standard.

1. **Possible new named entrant: "Observer Protocol"** (`observerprotocol.org`), not previously
   in §3. Multiple independent secondary sources (its own GitHub org, an arXiv agent-trust-models
   survey, and a third-party "Agent Payments Stack" directory) describe it consistently as:
   agent identity tied to legal-entity verification via W3C-compliant "Verifiable Agent
   Credentials," an "Agent Interaction Protocol" governing delegation and bilateral attestation,
   and — the part that matters here — observers must stake collateral with slashing on false
   attestation, explicitly marketed as "the compliance layer" for enterprises delegating economic
   authority to agents, with KYB linkage and compliance audit trails. If accurate, this is
   identity + staked/slashable reputation + compliance gating in one stack — the exact
   combination this doc's brief asks to watch for as a direct competitor, not adjacent like most
   of the §3 KYA-adjacent entries. Not added to §3 this run: could not independently confirm
   deployment status (live mainnet vs. spec/whitepaper-stage), funding, or team from a primary
   source (site fetch blocked), and no funding/founding-date signal turned up in a separate
   search either. Flagging here rather than adding a table row so a future run (or a session
   without this network restriction) can verify `observerprotocol.org` directly before this
   is treated as a confirmed competitor.
   Sources: [Observer Protocol · GitHub](https://github.com/observer-protocol),
   [Observer Protocol · Trust Infrastructure for the Agentic Economy](https://observerprotocol.org/),
   [Observer Protocol · Architecture](https://observerprotocol.org/architecture),
   [Observer Protocol - The Agent Payments Stack](https://agentpaymentsstack.com/observer-protocol),
   [Inter-Agent Trust Models: A Comparative Study of Brief, Claim, Proof, Stake, Reputation and
   Constraint in Agentic Web Protocol Design (arXiv)](https://arxiv.org/html/2511.03434).

2. **§3's existing KYA row's open question ("may or may not have stake/slashing") — partial,
   unverified signal that the answer is yes.** Search results for the already-tracked "Know
   Your Agent (KYA), built on AWP protocol, live on Base" row surfaced a "KYA Protocol"
   whitepaper at `agentecon.ai` and a `kya.link` site describing (consistently across several
   secondary sources) an ERC-8004-compliant, Base-deployed identity protocol where "AWP stake"
   is a verified per-agent attribute and staked assets are slashed on guardrail violations —
   i.e., staking tied to compliance enforcement, not just Sybil resistance. **Caveat, stronger
   than usual:** it is not fully clear from secondary sources alone whether `agentecon.ai`'s
   "KYA Protocol" and the `kya.link` "Know Your Agent" are the same project (the "KYA" initialism
   is now used by at least half a dozen unrelated efforts — Trulioo/Worldpay's framework,
   Vouched's directory, AstraSync AI, `knowyouragent.network`, `kyapay.org` — see prior
   changelog entries for some of these already ruled out separately). One search also attributed
   a "$30M from Polychain Capital, Coinbase Ventures, Polygon Labs, July-August 2025" raise to
   "KYA Protocol," which predates this doc's original 2026-08-17 dateline by a year and was not
   independently confirmed — not repeating that figure as fact, flagging it only so a future
   verification pass knows to check it. Net: worth a primary-source visit to `kya.link` and
   `agentecon.ai/whitepaper` (both blocked from this session) before updating the §3 table's KYA
   relevance note from "may or may not have stake/slashing" to confirmed.
   Sources: [KYA — Know Your Agent](https://kya.link/),
   [KYA Protocol - Know Your Agent (whitepaper)](https://agentecon.ai/whitepaper),
   [Every Company Building AI Agent Identity in 2026](https://knowyouragent.network/every-company-building-ai-agent-identity-in-2026),
   [Know Your Agent (KYA): Establishing the Standard for AI Agent Identity and Trust (AstraSync AI, Medium)](https://medium.com/@astrasyncai/know-your-agent-kya-establishing-the-standard-for-ai-agent-identity-and-trust-d0fb779fc657).

Not material / considered and not added: Cloudflare+GoDaddy's AI Crawl Control default-blocking
change (effective 2026-09-15, Agent Name Service + Web Bot Auth support) — coverage of this
dates to July 2026, predates this doc's 2026-08-26 tracking start, not new this sweep, and it's
already the tracked §3 row's "distribution chokepoint" characterization rather than a
compliance/reputation competitor; the newly-formed "Agentic Payments Alliance" (Rain, 26
members including Visa/Mastercard/Circle/Solana/Fiserv, announced 2026-08-18, Fiserv joining
reported 2026-08-31) — payment-rail standards consolidation, adjacent to the already-tracked
Visa TAP/Mastercard Agent Pay row per its existing "track for interop only" framing, not an
identity/reputation/compliance play; Oasis Security's $120M Series B (non-human identity/agentic
access governance) plus ModelCop and Securden's AI-agent security/governance platform launches —
enterprise agent-IAM plays, same category as Offroad/SecureAuth already ruled out in the
2026-08-28 entry, no staking/slashing or compliance-vertical gating disclosed. None meet this
doc's specific competitor bar with the confidence needed to add them.

### 2026-09-02 — Ecosystem watch: Observer Protocol upgraded to primary-source-confirmed (still pre-mainnet); everything else unchanged since 2026-09-01

Automated research sweep (scheduled tracking run, ~1 day after the prior run). Re-swept all
nine named §3 players, both §4 fact-checks, and did a general sweep for a new entrant combining
identity + staked reputation + compliance gating; only one item advanced past what the
2026-09-01 entry already recorded.

1. **Observer Protocol (flagged 2026-09-01, previously secondary-source-only) — primary source
   now reachable, confirms it's a real, actively-developed project, still explicitly pre-mainnet.**
   Unlike the prior run, this session's network egress was *not* blocked for
   `github.com/observer-protocol` (it was still blocked for `observerprotocol.org`,
   `agentecon.ai`, and `kya.link` — same as 2026-09-01). Fetching the GitHub org directly shows
   active repos updated as recently as 2026-08-31 (`op-policy-engine`, "delegation-scoped
   enforcement for agentic wallets," referencing an "AIP v0.8" spec) and 2026-08-26
   (`op-verify-service`, a hosted credential-verification service; `observerprotocol-website`).
   Several other repos (`ap2-op-authorize`, `x402-op-authorize`, `aqua`) are archived as
   reference implementations rather than live production code. No mainnet contract address
   appears anywhere in the org's visible content, and the org's own documentation is explicit
   that adapters carry tiered "support" rather than uniform production readiness. Net: this is
   not vaporware — it's a real, currently-maintained project matching the identity +
   staked/slashable-attestation + compliance-layer combination this doc watches for — but it is
   confirmed, now from a primary source rather than secondary coverage, to still be at
   spec/reference-implementation stage, not a deployed competitor. Still not added to §3 for
   that reason; re-check `observerprotocol.org`/GitHub again next sweep for a mainnet
   announcement, since active weekly commits suggest this could ship soon.
   Sources: [Observer Protocol · GitHub org](https://github.com/observer-protocol),
   [op-policy-engine](https://github.com/observer-protocol/op-policy-engine),
   [op-verify-service](https://github.com/observer-protocol/op-verify-service).

2. **§4 fact-checks: no change.** ERC-8004 Validation Registry — re-confirmed directly against
   the primary `erc-8004/erc-8004-contracts` README (reachable this session): still "under
   active update and discussion with the TEE community," still no mainnet address, identical
   language to the 2026-08-26/08-28 findings. EU AI Act — general sweep found nothing past the
   already-recorded 2027-12-02 (Annex III) / 2028-08-02 (Annex I) dates; no new enforcement
   action or amendment surfaced.

3. **KYA (`agentecon.ai`/`kya.link`) open stake/slash question — unchanged, still open.**
   Both primary sites remained blocked from this session (same as 2026-09-01). Secondary
   sources continue to describe a stake/slash mechanism consistent with the 2026-09-01 entry,
   but add nothing new beyond it, and the multiple-unrelated-projects-share-the-"KYA"-name
   caveat from that entry still applies. Not repeating as a separate finding since it doesn't
   advance past what's already recorded.

Not material / considered and not added: ChaosChain/Genesis Studio, FIDO Alliance's Agentic
Authentication TWG, and Trulioo+Worldpay's Digital Agent Passport all have routine coverage this
week (SDK/adapter updates, working-group-formation recaps, an AP2 partnership recap) but nothing
past what's already tracked in §3 — no new staking/slashing or compliance-gating mechanism, no
status change. General sweep for a new named entrant combining identity + staked reputation +
compliance gating surfaced nothing beyond Observer Protocol (already tracked above, not new
this run). No changes to the §3 table this run.

### 2026-09-13 — Ecosystem watch: Visa/Mastercard/Ant International joint "Know Your Agent" payment framework; everything else unchanged since 2026-09-02

Automated research sweep (scheduled tracking run, ~11 days after the prior run — wider than the
usual cadence, so this sweep covers the full gap rather than just the last 7 days). Re-swept all
nine named §3 players, both §4 fact-checks, and did a general sweep for a new entrant combining
identity + staked reputation + compliance gating. One material finding; everything else confirmed
unchanged.

1. **Visa, Mastercard, and Ant International announced a joint "Know Your Agent" (KYA)
   interoperability framework, 2026-09-10, São Paulo.** This is new since the 2026-09-02 entry
   and directly touches this doc's already-tracked §3 "Visa TAP / Mastercard Agent Pay" row: the
   two card networks (previously described in this doc as separate, competing frameworks — see
   the Forbes "fighting over how AI agents pay" framing cited in earlier research) are now
   converging on a shared standard, joined by Ant International, so that an agent's KYA
   verification from one provider is recognized by the others rather than needing duplicate
   verification per network. Reported consistently across independent outlets (PYMNTS, Forkast,
   PANews, crypto.news, Hokanews). **Explicitly no technical specification, governance body, or
   rollout timeline disclosed yet** — this is a joint intent-to-standardize announcement, not a
   shipped mechanism, and nothing in the coverage describes staking, slashing, or a
   compliance-vertical gate, so it stays in this doc's existing "adjacent, payments-identity,
   track for interop only" bucket rather than becoming a direct identity+staked-reputation+
   compliance-gating competitor. Flagging two things for future runs: (a) this is the specific
   development to watch if it later grows a staking/slashing or compliance-gating layer, since
   three major payment networks converging on one agent-trust standard would be a much higher-
   leverage integration/interop target than any single one alone; (b) this consortium's own use
   of the "Know Your Agent" / "KYA" name is a **new, separate naming collision** on top of the
   half-dozen unrelated "KYA"-branded efforts already flagged in the 2026-09-01 entry (this doc's
   existing §3 KYA row tracks a different, Base-deployed, AWP-protocol project at
   `kya.link`/`agentecon.ai` — unrelated to this Visa/Mastercard/Ant announcement) — do not
   conflate the two in future sweeps.
   Sources: [PYMNTS, Visa and Mastercard Team With Ant on Know Your Agent Framework](https://www.pymnts.com/cybersecurity/2026/visa-mastercard-team-with-ant-know-your-agent-framework),
   [Forkast, Ant International, Visa, and Mastercard Agree on Agent Identity Standard. Now Comes the Hard Part.](https://forkast.news/ant-international-visa-and-mastercard-agree-on-agent-identity-standard-now-comes-the-hard-part/),
   [crypto.news, Ant International joins Visa, Mastercard to build AI agent payment standards](https://crypto.news/ant-international-joins-visa-mastercard-to-build-ai-agent-payment-standards/),
   [PANews, Ant International Partners with Visa and Mastercard to Establish AI Agent Payment Standards](https://panews.io/articles/01a08951-c577-77c7-b43b-2795756e0c48).

2. **§4 fact-checks: no change since 2026-09-02.** ERC-8004 Validation Registry — general
   secondary-source sweep found nothing past the already-recorded status (Identity/Reputation
   live on 40+ EVM networks since 2026-01-29; Validation Registry still described as under active
   spec revision, no mainnet address). EU AI Act — reconfirmed the 2026-08-28 correction's dates
   (Annex III high-risk conformity 2027-12-02, Annex I 2028-08-02) against fresh sources; nothing
   newer surfaced.

3. **Observer Protocol (tracked since 2026-09-01, still not added to §3) — unchanged, still
   pre-mainnet.** This session's egress proxy again blocked `observerprotocol.org`,
   `agentecon.ai`, and `kya.link` directly (same restriction as the prior two runs), but
   `github.com/observer-protocol` was reachable. Its visible repo activity is **identical** to
   what the 2026-09-02 entry already recorded (`op-policy-engine` last updated 2026-08-31,
   `op-verify-service` and `observerprotocol-website` last updated 2026-08-26) — no commits since
   the last sweep, no mainnet contract address, no new funding/deployment signal. A separate
   general web search surfaced an unrelated Bitcoin-Lightning-settlement narrative for
   "Observer Protocol" (a "genesis transaction," 2026-02-22) describing "Verified Agent
   Credentials (VAC)" — this predates and is a different framing from the AIP-spec/staked-
   attestation project already tracked here; not enough independent confirmation this run to
   determine if it's the same project rebranding its terminology or a distinct namesake, so not
   treated as new information pending a primary-source check once the proxy block clears.

4. **KYA (`agentecon.ai`/`kya.link`) open stake/slash question — still unverified, still
   blocked.** No change from the 2026-09-01/09-02 status.

Not material / considered and not added: FIDO Alliance's Agentic Authentication TWG (still
tracking toward H2 2026–early 2027 per its own April timeline, no draft spec yet); Cloudflare's
2026-09-15 default AI-agent-crawler-blocking change (already flagged as non-new in the 2026-09-01
entry — this run confirms the date is real and imminent but it's the same already-tracked policy,
not a new fact); Anthropic's enterprise-managed MCP auth GA (already covered in the 2026-08-28
entry, no further change); Semantica (still pre-1.0, PyPI 0.5.0 as of a 2026-09-02 third-party
review, no staking/reputation mechanism); Trulioo+Worldpay Digital Agent Passport (still no public
API for the agent-specific KYA layer beyond the 2025-08-14 partnership announcement); VeChain's
"Agentic Foundations" 2026 roadmap (agent identity + a behavioral "credibility score" + its
existing StarGate validator-staking platform) — considered as a possible new identity+staked-
reputation entrant, but the roadmap dates to April 2026 (predates this doc's tracking window
entirely), the staking is StarGate's general network-consensus staking rather than an
agent-specific bond that gets slashed on misbehavior, and no compliance-vertical gating is
described — does not meet this doc's competitor bar. No changes to the §3 table this run.

### 2026-09-15 — Ecosystem watch: correction — Observer Protocol does not actually have a stake/slash mechanism (primary-source-confirmed); everything else unchanged since 2026-09-13

Automated research sweep (scheduled tracking run, ~2 days after the prior run). Re-swept all nine
named §3 players, both §4 fact-checks, and did a general sweep for a new entrant combining
identity + staked reputation + compliance gating. One material correction to a repeatedly-tracked
item; everything else confirmed unchanged or not material.

1. **Correction: Observer Protocol does not have a staking/slashing mechanism — the
   "observers must stake collateral with slashing on false attestation" characterization
   carried in the 2026-09-01, 2026-09-02, and 2026-09-13 entries above was based on secondary
   sources and does not hold up against the protocol's own primary sources.** This run's network
   egress again blocked `observerprotocol.org`, `agentecon.ai`, and `kya.link` directly (same
   restriction as every prior run), but `github.com/observer-protocol` and its component repos
   were reachable. Direct review of the `aip` spec repo (the Agentic Identity Protocol
   specification itself, v0.6 through v0.9) found **no mention of staking, bonds, collateral, or
   slashing anywhere** — the spec's actual scope is DIDs/credential lifecycle, verification flows
   and an attestation taxonomy, trading-delegation policy mandates, and World ID
   proof-of-personhood linkage, not an economic stake/slash mechanism. A separate search
   independently corroborates this: Observer Protocol is MIT-licensed "with no token and no plans
   for one." The `op-policy-engine` repo (delegation-scoped policy enforcement for agentic
   wallets) is a compliance/authorization layer — evaluating a proposed agent action against a
   signed delegation credential and returning a signed allow/deny decision — not a staking
   ledger. Net: Observer Protocol is identity (W3C DIDs, Verifiable Agent Credentials) +
   delegation/compliance policy enforcement, but **not** staked/slashable reputation, so it does
   **not** actually match this doc's specific identity+staked-reputation+compliance-gating
   competitor combination after all. Downgrading from "possible direct competitor, pending
   primary-source confirmation" (2026-09-01) / "primary-source-confirmed real project, still
   pre-mainnet" (2026-09-02, 2026-09-13) to: primary-source-confirmed, does not meet the
   competitor bar on the staked-reputation axis. Not added to §3 (consistent with prior runs,
   though now for a different reason — mechanism mismatch rather than deployment-stage caveat).
   Leaving the original 2026-09-01/09-02/09-13 entries above unedited per this doc's own
   append-only convention; this entry is the correction of record.
   Sources: [Observer Protocol · GitHub org](https://github.com/observer-protocol),
   [observer-protocol/aip](https://github.com/observer-protocol/aip),
   [observer-protocol/op-policy-engine](https://github.com/observer-protocol/op-policy-engine).

2. **§4 fact-checks: no change since 2026-09-13.** ERC-8004 Validation Registry — independently
   reconfirmed via a primary-source signal not seen in prior sweeps: a September 5, 2026 GitHub
   pull request (`CSOAI-ORG/councilof-ai#1332`, unrelated third-party repo naming canonical
   ERC-8004 mainnet addresses) explicitly states the "Validation registry is UNSHIPPED upstream"
   — consistent with the status already tracked here since 2026-08-26 (Identity/Reputation live
   on 40+ EVM networks since 2026-01-29, Validation Registry still not deployed). EU AI Act — no
   new developments surfaced; Annex III high-risk conformity 2027-12-02 and Annex I 2028-08-02
   dates reconfirmed against fresh secondary sources, nothing newer.

3. **KYA (`agentecon.ai`/`kya.link`) open stake/slash question — still unverified, still
   blocked.** Same as 2026-09-01/09-02/09-13: primary sites unreachable this session; secondary
   sources continue describing an AWP-protocol stake/slash mechanism consistent with prior runs,
   nothing new enough to change status.

Not material / considered and not added: two solo/hobbyist projects technically combining
identity + stake/slash surfaced in a general sweep — `selfradiance/agentgate` ("Stake-gated
action microservice for AI systems," Ed25519 identity + bond-and-slash + progressive trust
tiers — genuinely matches the technical combination on paper, but primary-source and press
review (the creator's own Medium posts) confirm it's an individual's learning project built
solo with Claude Code, explicitly described as "not a business," 5 GitHub stars, no company or
funding; its public `agentgate.run` deployment was decommissioned in March 2026 and it now runs
locally only) and `agentstake.dev` ("The Trust Layer for AI Agents," STAKE-token staking +
slashing + staked-juror dispute resolution on Base — but framed across dev.to posts as an
"I built the missing trust layer" solo/hackathon project, its dispute-resolution model is
escrow/arbitration-style rather than compliance-vertical gating, matching the pattern already
ruled out for BNBAgent SDK/ERC-8183 in the 2026-08-28 entry) — neither is a funded or
institutionally-backed entrant, so neither meets this doc's "genuinely new named competitor"
bar; flagging only in case either gains real backing later. FIDO Alliance TWG (still no draft
spec); Cloudflare/GoDaddy default AI-crawler-blocking (effective today, 2026-09-15, but already
flagged as non-new since 2026-09-01); Anthropic MCP enterprise auth (no change since
2026-08-28); Semantica and Trulioo+Worldpay (no updates since last tracked). No changes to the
§3 table this run.

### 2026-09-22 — Ecosystem watch: first confirmed EU AI Act enforcement action (GPAI RFIs); no new competitor; everything else unchanged since 2026-09-15

Automated research sweep (scheduled tracking run, ~7 days after the prior run; branch
`audit/harness-loop-2026-07-30` still exists from the last run, no recreation needed this time —
note for future runs: the 2026-09-01 entry recorded it being deleted-and-recreated once already).
Re-swept all nine named §3 players, both §4 fact-checks, and did a general sweep for a new
entrant combining identity + staked reputation + compliance gating. One material finding on the
EU AI Act enforcement fact-check; everything else confirmed unchanged or not material.

1. **First confirmed concrete EU AI Act enforcement action: formal Requests for Information sent
   to 30+ GPAI model providers.** European Commission Executive Vice-President Henna Virkkunen
   confirmed on 2026-08-29 that the AI Office had formally sent requests for information (under
   Article 91's investigative powers) to "a number of providers of general-purpose AI models
   based in different regions of the world," with the requests themselves going out around
   2026-09-01. Reporting (independently corroborated by the AGENCE EUROPE wire service and
   multiple law/policy outlets) says the RFIs run on two tracks — one on model security,
   independent external evaluation, and post-market monitoring for the most advanced models; the
   other on copyright and transparency obligations for training data and outputs — and that
   OpenAI, Anthropic, and Google are reportedly among the recipients (the Commission has not
   published an official recipient list). This is evidence-gathering, not a finding of
   infringement, but it is the first actual use of the Act's Article 91 investigative power
   reported anywhere, i.e. the first move from "law on the books" to "enforcement in motion" —
   material to this doc's §2 EU AI Act tracking even though it targets the transparency/GPAI tier
   already in force since 2026-08-02, not the deferred Annex III high-risk tier (2027-12-02,
   unchanged — see item 2 below). Distinct and lower-confidence secondary reporting (cubbbix.com,
   opsintel.io, thegputrade.com — none corroborated by a primary EU source or major outlet found
   this sweep) additionally claims a parallel "first wave" of Article 50 sector inspections
   (automated resume screening, credit-scoring, healthcare triage) starting in September 2026;
   not treated as confirmed here given the source quality, flagging only so a future run with
   primary-source access can check for an official AI Office announcement.
   Sources: [Agence Europe, European Commission sends first requests for information to more
   than 30 AI providers](https://agenceurope.eu/en/bulletin/article/13929/31/european-commission-sends-first-requests-for-information-to-more-than-30-ai-providers),
   [Superpower Daily, EU Seeks AI Act Answers From 30-Plus Companies, With Fines for Misleading
   Replies](https://superpowerdaily.com/posts/eu-seeks-ai-act-answers-from-30-plus-companies-with-fines-for-misleading-replies),
   [Tokenstead, EU AI Act Enforcement Begins: The AI Office Starts Asking](https://tokenstead.ai/guides/eu-ai-act-first-enforcement-security-rfis).

2. **§4 fact-checks: no change.** ERC-8004 Validation Registry — re-confirmed unchanged (Identity/
   Reputation registries live on 40+ EVM networks since 2026-01-29; Validation Registry still
   explicitly "unshipped upstream" per the same primary repo/PR evidence already cited in the
   2026-09-15 entry, no mainnet address). EU AI Act deadlines — Annex III high-risk 2027-12-02 and
   Annex I 2028-08-02 reconfirmed against fresh sources, no change to the dates themselves (only
   the new enforcement-activity fact in item 1 above).

3. **General sweep for a new identity + staked-reputation + compliance-gating entrant: nothing
   added.** Checked several newly-surfaced identity/compliance players specifically for a
   staking/slashing mechanism, since that's the discriminator that has ruled out most candidates
   in prior sweeps — none qualify: **KYA Lab** (`kyalab.com`, "KAAC" accreditation credential for
   AI agents in healthcare/insurance/finance/government, continuous re-examination on material
   change, HIPAA/PCI-DSS/SOX audit trails) is accreditation/credentialing only, no staking or
   slashing found anywhere in its public materials — same shape as the already-tracked
   Semantica/Trulioo rows, not added, though flagged here given its explicit healthcare framing
   overlaps Integrity Health's vertical; **AgentFacts** (`agentfacts.org`, an academic "Know Your
   Agent" metadata standard, Apache 2.0, cites enterprise pilots in finance/gaming/Web3) is a
   capability-declaration/verification standard, no staking mechanism disclosed; **AGNTCY
   Identity** and the newly-surfaced **"MCP-I"** identity extension work referenced in MCP-adjacent
   coverage are both agent/MCP identity-and-permissioning layers (delegation credentials,
   workload identity federation, token exchange — consistent with Anthropic's own 2026-08-22 MCP
   roadmap, already covered by this doc's existing MCP row), not staked-reputation systems.
   **New naming-collision note for future runs:** a *third*, unrelated "KYA Protocol" surfaced
   this sweep — `github.com/fotescodev/kya-protocol`, an EAS (Ethereum Attestation Service)-based
   on-chain identity standard, alpha-stage and live only on Base Sepolia testnet, explicitly with
   no staking/slashing mechanism — distinct from both the already-tracked `kya.link`/`agentecon.ai`
   AWP-based KYA Protocol and the Visa/Mastercard/Ant "Know Your Agent" payments framework; do not
   conflate the three in future sweeps.

4. **§3's existing KYA row (`kya.link`/`agentecon.ai`) stake/slash question — still open, still
   blocked from primary-source confirmation, but secondary-source detail firmed up somewhat.**
   This session's egress proxy again blocked `agentecon.ai` and `kya.link` directly (same
   restriction every prior run since 2026-09-01), but web search (rather than direct fetch)
   surfaced more specific, mutually-consistent secondary-source technical detail than prior runs
   had: agentecon.ai's KYA Protocol is described as an ERC-8004-compliant system on Base with
   "10 core smart contracts" implementing Identity/Reputation/Validation registries mirroring the
   ERC-8004 structure, where validators "earn rewards for accurate scoring and face slashing
   penalties for malicious behavior." This is consistent with, and more detailed than, the
   2026-09-01 entry's original secondary-source characterization, but it is still secondary-source
   only (no primary-site fetch succeeded) and still does not resolve whether this constitutes
   compliance-vertical gating specifically (searches returned only generic "KYA compliance market"
   framing, not an agentecon.ai-specific gating mechanism) — not upgrading this doc's confidence
   level beyond "open, unverified" for that reason. Worth a primary-source visit to
   `agentecon.ai/whitepaper` and `kya.link` from an unrestricted session before treating the
   stake/slash mechanism, or any compliance-gating claim, as confirmed.

Not material / considered and not added: Injective Agents and ChaosChain/Genesis Studio (no
September 2026 updates found beyond routine ecosystem-event coverage — Injective/Microsoft
Token2049 commerce event, no ERC-8004/identity-specific news; ChaosChain's Genesis Studio repo
shows no commits since 2026-02-07); the Visa/Mastercard/Ant International "Know Your Agent"
payments framework (already tracked in the 2026-09-13 entry — this sweep found additional detail,
that it was convened under the Monetary Authority of Singapore's BuildFin.ai platform and builds
on an existing "SAFR framework," but no technical spec, staking, or compliance-gating mechanism
disclosed yet, so status is unchanged); FIDO Alliance's Agentic Authentication TWG (still tracking
toward its original H2 2026–early 2027 timeline, no draft spec yet); Cloudflare/GoDaddy (no
update since the already-tracked 2026-09-15 default-blocking change); Semantica (still MIT-licensed
open source, no funding or staking found, v0.6.0 as of 2026-07-21); Trulioo+Worldpay Digital Agent
Passport (no update since the original 2025-08-14 partnership); Observer Protocol (not re-checked
in depth this run beyond a routine site-content-reorganization commit dated 2026-09-16 — no
reversal of the 2026-09-15 correction that it lacks a staking/slashing mechanism). No changes to
the §3 table this run.
