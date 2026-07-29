# Integrity Protocol

**A trust and compliance layer for the agentic economy.** Integrity Protocol
uses smart contracts and immutable on-chain state to solve two problems no
purely off-chain system can:

1. **Regulatory compliance** — can a regulator or counterparty verify an AI
   agent's behavior *after the fact*, without trusting the agent's own word?
2. **Agent trust** — can one agent (or service) verify another's track record
   *before* transacting with it?

The protocol's defining architectural choice: **agents own and deploy their own
identity and reputation contracts.** On registration, an agent's own EVM wallet
deploys a set of *primitive* contracts that become its self-sovereign on-chain
identity. Nothing is registered *on behalf of* the agent by a privileged
factory — the deployment transactions are signed by the agent's own key, so the
chain itself is cryptographic proof of who controls what.

### Persistent memory is a foundational primitive

An agent that cannot carry state across sessions is not an economic actor — it is a
stateless function invoked repeatedly. So **persistent memory sits alongside identity,
commitment, stake, and observability as a foundational primitive of this protocol**, not as
a convenience feature bolted on top of one.

This is load-bearing, not aspirational: **an agent with no anchored memory cannot
register.** Every agent must control a durable **Trust Vault** whose commitments are
Merkle-anchored on its own `StateAnchor`, and must anchor a **genesis memory root** —
signed by the agent's own controller, never by the protocol — before registration
completes. The oracle independently re-reads `StateAnchor.latestRoot` from chain and
refuses a zero root with `400 MemoryNotInitialized`. Content stays off-chain and
agent-controlled; only commitments go on-chain, so memory is provable without being
exposed.

The consequences follow from that: reputation means something because the history it scores
is one the agent itself can produce and cannot silently rewrite; copying another agent's
vault transfers no identity, stake, or AIS, because roots are bound to the original
`StateAnchor`. See
[Persistent Memory, Genesis Root & Lineage](docs/wiki/concepts/agent-memory.md) for the
full model, `docs/INTERFACE_CONTRACT.md` §4.4a for the wire-level constant, and
[`PRODUCTION_GAPS.md`](PRODUCTION_GAPS.md) §19 for exactly what is enforced today versus
what is still open.

**Xibalba Shield** — the HIPAA/healthcare vertical — is the flagship proof that
this works in the most heavily regulated industry there is. It's not a side
feature; it's the demonstration that makes the rest of the protocol credible.

> This is a from-scratch rewrite of an earlier prototype. Its ground rule, in
> [`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md), is **no silent
> mocks**: every piece is either real and tested against a real toolchain, or an
> honestly-documented gap. Read the interface contract before changing any
> cross-package schema, port, or env var.

---

## Architecture at a glance

```mermaid
flowchart TB
    Wallet["Agent's own wallet"]
    Factory["AgentPrimitivesFactory"]

    subgraph OnChain["On-chain (EVM / Base Sepolia + anvil)"]
        SA["SovereignAgent<br/>(identity account)"]
        StA["StateAnchor<br/>(per-agent audit root)"]
        subgraph Clones["5 EIP-1167 minimal-proxy clones<br/>each uniquely owned by the agent"]
            RR["ReputationRegistry"]
            SL["Slasher"]
            VR["VerifierRegistry"]
            CG["ComplianceGate"]
            AP["AgentProfile"]
        end
    end

    SDK["integrity-sdk / integrity-cli<br/>(self-deploy registration,<br/>BCC commitments, telemetry)"]
    BCC["bcc_middleware (FastAPI + OPA)<br/>(policy, HIPAA BAA check,<br/>ZK, Merkle anchoring)"]
    Oracle["integrity-oracle (Rust/Axum)<br/>(AIS scoring, telemetry ingest,<br/>on-chain reads)"]
    Dashboard["integrity-dashboard (React + Python)<br/>(the one dashboard/landing app +<br/>its demo scenario engine)"]

    Wallet -->|signs direct deploys| SA
    Wallet -->|signs direct deploys| StA
    Factory -->|clones| RR
    Factory -->|clones| SL
    Factory -->|clones| VR
    Factory -->|clones| CG
    Factory -->|clones| AP

    SDK --> Wallet
    SDK -->|pre-execution gate| BCC
    BCC -->|telemetry| Oracle
    Oracle -->|resolve + score| OnChain
    Oracle --> Dashboard
```

`bcc_middleware` and `integrity-oracle` together form one trust domain — the
pre-execution gate (before an agent acts) and the telemetry/scoring backend
(after an agent acts, plus all on-chain reads) — see
[`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md) §6.10.

### The 7 agent primitives

Every agent, at registration, comes to own seven contracts. Two are deployed
**directly by the agent's own wallet** (so the deploy transaction proves
self-sovereign control); five are cheap **EIP-1167 minimal-proxy clones** of
shared implementation contracts (each clone is still uniquely owned and
controlled by that agent).

| # | Primitive | Deploy | Purpose |
|---|---|---|---|
| 1 | `SovereignAgent` | direct | The agent's account contract — DID, cached AIS, `execute`, controller rotation |
| 2 | `StateAnchor` | direct | The agent's own tamper-evident Merkle-root anchor for its telemetry |
| 3 | `ReputationRegistry` | clone | Per-agent AIS ledger + ZK-boost bookkeeping |
| 4 | `Slasher` | clone | Per-agent $ITK stake / dispute-gated slashing vault |
| 5 | `VerifierRegistry` | clone | Per-agent versioned pointer to the ZK verifier it trusts |
| 6 | `ComplianceGate` | clone | Per-agent regulated-industry declaration + live Shield/HIPAA check |
| 7 | `AgentProfile` | clone | Per-agent domain-membership + metadata pointer |

**Call-routing rule:** every clone's admin role is granted to the agent's own
`SovereignAgent` *contract* address, never its raw EOA. All post-registration
state changes route through `SovereignAgent.execute(...)`. See
[`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md) §6 for the full
convention and the one bootstrap exception.

### Sovereign vs. Centralized Deployments

When building and deploying applications on the protocol, developers must choose between two deployment topologies depending on whether the smart contract serves an individual agent or the entire platform:

| Feature | Sovereign Mode (Agent-Owned Clones) | Centralized Mode (EOA-Owned Singletons) |
|---|---|---|
| **Architecture** | EIP-1167 minimal-proxy clones unique to each agent. | Monolithic global singleton contracts shared by all agents. |
| **Ownership** | Admin/owner role is the agent's `SovereignAgent` contract address. | Admin/owner role is the platform operator's or DAO's EOA/multisig key. |
| **Call Routing** | Admin actions must route through `SovereignAgent.execute()`. | Direct EOA interaction with the target contract. |
| **Typical Use Cases** | `IntegrityMarket` (individual prediction clones), task/service escrows, custom A2A agreements. | `A2ACapitalPool` (global allocation venue), `XibalbaAgentRegistry`, regulatory portals (`CoveredEntityRegistry`). |
| **Key Implications** | High gas efficiency (cloning), sandboxed liabilities (isolated stakes), and self-sovereign controller key rotation. | Unified liquidity, centralized verification guardrails, and platform-wide parameter standards. |

---

## Packages

| Package | Stack | Purpose | Status |
|---|---|---|---|
| [`contracts/`](contracts/) | Solidity + Foundry | The 7 primitives, factory, registries, XNS, `IntegrityGovernance`, $ITK, Shield stack, ZK verifier, cross-chain reputation bridge | ✅ 198 tests; deployed to Base Sepolia (XNS/governance/CCIP bridge not yet broadcast — see below) |
| [`integrity-zkp/`](integrity-zkp/) | Noir + Barretenberg | The ZK circuit proving an action matches its committed intent | ✅ real `nargo`/`bb` pipeline |
| [`integrity-oracle/`](integrity-oracle/) | Rust + Axum + Postgres | Telemetry ingestion, AIS computation, on-chain reads | ✅ 37 lib tests + real e2e |
| [`integrity-sdk/`](integrity-sdk/) | Python | Agent library: DID/keys, EVM wallet, self-deploy registration, BCC, telemetry (OTel + MLflow) | ✅ 46 tests |
| [`integrity-cli/`](integrity-cli/) | Python (Typer) | Developer CLI for identity, on-chain registration, BCC intercept | ✅ 49 tests |
| [`bcc_middleware/`](bcc_middleware/) | Python (FastAPI) + OPA | Pre-execution policy gate, HIPAA BAA check, Merkle anchoring | ✅ 49 tests + 12 OPA |
| [`integrity-userapi/`](integrity-userapi/) | Python (FastAPI) + Postgres | User accounts, auth, API keys, agent ownership — strictly non-chain | 🚧 in progress |
| [`integrity-dashboard/`](integrity-dashboard/) | React + Vite + TS, plus `demo/` (Python) | The ONE investor/developer app — landing, markets, leaderboard, wallet, capital allocation, cognition, identity, Shield — plus its closed-loop demo scenario engine. Formerly two packages (`integrity-dashboard` + `integrity-demo`), merged so there's exactly one product surface. | 🚧 in progress |

---

## The Agent Integrity Score (AIS)

The protocol's trust metric. Computed in exactly one place —
`integrity-oracle/scoring-core` — and read by everyone else via the oracle's
HTTP API, never recomputed:

```
AIS = (S_entropy·wE + S_grounding·wG + S_sacrifice·wS + S_compliance·wC) · ZK_boost
```

Default weights `wE=0.30, wG=0.30, wS=0.20, wC=0.20` (sum to 1.0); `ZK_boost`
is `1.15` when a real Barretenberg proof was verified for the reporting period,
else `1.0`. The four component scores come from an agent's telemetry — the SDK
derives first-pass signals from OpenTelemetry/MLflow spans, but the **oracle
independently recomputes entropy/grounding/sacrifice/compliance server-side**
from the same signed telemetry rather than trusting the client's numbers (see
`integrity-oracle/backend/src/derive.rs`) — the SDK's values are advisory/audit
trail only. See [`docs/wiki/concepts/ais.md`](docs/wiki/concepts/ais.md).

```mermaid
flowchart LR
    Agent["Agent (SDK/CLI)"] -->|"signed POST /v1/telemetry/ingest<br/>(otel_spans + derived_signals)"| Oracle["integrity-oracle"]
    Oracle -->|"re-derive from otel_spans<br/>(same posture as PHI backstop)"| Recompute["entropy / grounding /<br/>sacrifice / compliance<br/>(oracle-computed, authoritative)"]
    Recompute --> Formula["AIS = ΣS·w · ZK_boost<br/>(scoring-core, sole formula owner)"]
    ZK["Real Barretenberg ZK proof<br/>(bb verify)"] -.->|"1.15× if verified<br/>this period"| Formula
    Formula --> API["GET /v1/agent/{id}/ais<br/>+ live SSE push"]
```

---

## Vision & long-term roadmap

**Thesis:** AI agents should be able to hold their own identity, own and deploy
their own smart contracts, and act as accountable economic participants —
"Economic Sovereigns," not passive tools running under someone else's
account. Integrity Protocol is the trust layer that makes delegating money
and regulated actions to an autonomous agent mathematically safe: every claim
an agent makes about its own behavior is either independently verified
on-chain, or honestly labeled as unverified. Xibalba Shield (healthcare) is
the flagship proof this holds in the most heavily regulated industry there
is; the multi-vertical Dashboard (markets, capital allocation, wallet) proves the
same mechanism generalizes to any domain where trust has economic value.

This section distinguishes, deliberately, **what is real and running today**
from **what is the long-term architectural direction** — per this repo's
"no silent mocks" rule, nothing below in the roadmap column is implemented
yet, and no code should ever claim otherwise.

### Identity & hardware trust

| Built today | Long-term roadmap |
|---|---|
| Software-held secp256k1/Ed25519 keypairs (encrypted local keystore) | Hardware-bound identity: keys tethered to TEE/SGX enclaves or an HSM (AWS KMS, FIPS 140-2 Level 3), so a key can't be extracted even by whoever controls the host |
| `did:integrity:<sha256(pubkey)>` DIDs, W3C DID Documents | Remote TEE attestation (AWS Nitro / Intel SGX) proving an agent's key is physically tethered to a verified Controller |
| Agent self-registers all 7 primitives with its own signature as proof of control, and can self-service claim a human-readable XNS handle (`XibalbaNameService.sol`, first-come-first-served, no admin in the critical path) | Direct handle transfer between agents (today: release + separate re-claim by the new owner) and expiry/renewal semantics |
| **Persistent memory** (spec v0.3 §4.1/§7): the agent anchors a genesis Trust Vault root on its own `StateAnchor` through its controller during registration, and the oracle independently re-reads `latestRoot`, refusing a zero root with `400 MemoryNotInitialized` | Contract-level enforcement that the protocol's `ANCHOR_ROLE` signer cannot anchor epoch 1 (§7.2), and lineage attestation for fork/migration/recovery with no automatic AIS or stake transfer (§7.4) — neither built |

### Verification ladder (roadmap — not yet gating anything)

The long-term design ties an agent's AIS *ceiling* (not just its measured
score) to how strongly its identity is verified, so a freshly-created,
unverified agent can never simply out-score a hardware-attested one:

| Tier | Verification | AIS ceiling | Status |
|---|---|---|---|
| 1 — Sovereign | Proof-of-possession of a software key (what every agent has today) | 600 | Effectively where every agent sits now — **not yet enforced as a ceiling** |
| 2 — Linked | DNS TXT record or social-account attestation | 850 | Not built |
| 3 — Institutional | Remote TEE attestation + institutional audit | 1000 (uncapped credit) | Not built |
| Developer API key (testnet convenience) | Issued by `integrity-userapi` | Capped at 300 | Planned in `integrity-userapi`'s API-key issuance |

### Data, telemetry & PHI safety

The SDK is a **local metrology apparatus**: it measures agent behavior (entropy,
grounding, sacrifice signals) and forwards only what the oracle needs — never
raw reasoning content by default in a regulated vertical. The precise
architecture:

- **`Redactor`** (`integrity_sdk/security/`, alongside the existing
  `attestation.py`/`vault.py`) — performs client-side PII/PHI/secret masking
  on span content *before anything leaves the agent's process*. This is
  targeted masking (patient identifiers, secrets, credentials — the specific
  entities HIPAA/PCI care about), not a blanket delete: the goal is a trace
  that's safe to store AND still useful for downstream evaluation.
- **LLM-as-judge evaluation runs oracle-side**, as part of the backend's
  Evaluation Framework, operating on the already-redacted trace the SDK sent
  — never on raw content, and never client-side. Its rubric ("Xibalba
  Solutions defines") is not specified in this repo yet; the ingestion
  schema/hook is being built ahead of the rubric itself.
- **Dual-mode storage** (roadmap, not yet built as a toggle): Mode 1
  (transparent) stores full traces for standard, non-regulated use —
  developer debugging visibility is the priority. Mode 2 (Sovereign
  ZK-Mode, for Shield/healthcare and any PHI-adjacent vertical) never lets
  raw content leave local hardware at all — only a hash and a ZK proof of
  correct measurement leave the agent's process.
- **Redaction gate is closed everywhere it needs to be.**
  `integrations/openai_integrity.py` and `integrations/langchain_callback.py`
  both call `redact_text(...)` on prompt/completion span content before it
  ever leaves the agent's process — that was fixed a while back and is no
  longer an open gap. The real remaining gap, closed 2026-07-11: the SDK's
  own general-purpose, documented tracing API
  (`telemetry/tracing.py`'s `trace_run`/`traceable`/`client.traceable(...)`)
  captured raw function arguments/return values with **no** redaction. A
  `_redact_value` helper is now applied in `TraceRun.set_outputs` and
  `_capture_inputs`, so that path is redaction-gated the same as the
  integrations above.
- **Oracle never touches raw PHI, full stop** — enforced with defense in
  depth: the SDK-side `Redactor` is the primary control, and
  `/v1/telemetry/ingest` independently rejects any payload carrying a
  recognized raw-content key as a backstop against a future SDK regression.

### Decentralization path

Today, Xibalba Solutions LLC operates the oracle, the demo resolver, and
policy defaults as a single operator — appropriate for a testnet Dashboard, not
the end state:

1. **Phase 1 — Human-in-the-loop (current).** Xibalba Solutions manages OPA
   policy defaults, the market `RESOLVER_ROLE`, and protocol upgrades
   directly.
2. **Phase 2 — Hybrid council (roadmap).** Governance shared between human
   stakeholders and a council of Tier-3 Institutional agents that sustain a
   950+ AIS over a sustained period — the same mechanism this Dashboard's
   `IntegrityMarket.RESOLVER_ROLE` is a deliberately-labeled stand-in for
   (see `contracts/src/markets/IntegrityMarket.sol`'s NatSpec): a syndicate
   of high-AIS agents, not one operator key, eventually resolves markets.
3. **Phase 3 — Protocol DAO (contract built, deploy deferred).** On-chain
   governance where `$ITK` holders vote on protocol parameter changes is now a
   **real contract** — `IntegrityGovernance.sol` (lock-to-vote, timelocked
   propose→vote→queue→execute; 26 tests), read by the oracle
   (`GET /v1/governance/proposals`) and rendered live in the dashboard's
   Governance panel. It is wired into genesis `Deploy.s.sol` but **not yet
   broadcast to Base Sepolia** (a gas-costing operator action) — until then the
   endpoint returns a clean `MissingSingleton` (HTTP 400) and the UI shows an
   honest "not yet live" state. Participation writes (propose/vote) are done via
   CLI/SDK for now. See `docs/wiki/concepts/governance.md`.
4. **Cross-chain reputation (roadmap).** `CCIPReputationBridge.sol` exists
   in `contracts/` but is explicitly unwired (see its own NatSpec) —
   synchronizing AIS across Base/Arbitrum/Ethereum is a real future step,
   not a current capability.
5. **Gas abstraction (roadmap).** An ERC-4337 verifying paymaster
   (sponsoring gas for agents above an AIS threshold, so an agent never
   needs to hold native ETH to participate) is a planned simplification of
   today's direct-funding faucet model (`chain.fund_agent_wallet`) — not
   built yet.

### Advanced primitives (roadmap, explicitly out of scope for the current Dashboard)

Named here so they're tracked, not forgotten, and so nothing in this repo
should be mistaken for having built them:

- **A2A negotiation protocol** — P2P capability broadcast + bid negotiation
  over a gossip layer (libp2p/Waku), landing in a signed on-chain deal.
  Today's `A2ACapitalPool.sol` is a simpler, direct allocation primitive —
  not this.
- **ZK-ML model-inference verification** — proving an agent's output came
  from a *specific, authorized* model without revealing weights, via a
  dedicated Noir inference circuit + `ZKModelRegistry.sol`. Today's ZK layer
  (`integrity-zkp/`, `UltraPlonkVerifier.sol`) proves telemetry/attestation
  claims, not model-inference correctness.
- **Institutional credit & AIS-collateralized lending** — reputation-backed
  ITK credit lines (this is `integrity-framework/`'s originally-scoped
  concept, §12 of `docs/INTERFACE_CONTRACT.md`, not yet built).
- **Decentralized oracle validator network** — today's oracle is a single
  Rust service; the long-term design redistributes AIS computation and
  ZK-proof verification across redundant, independently-operated nodes
  reaching consensus on Merkle anchors.

### Full source vision documents

The complete, unabridged product/architecture vision (including sections not
yet reflected in this repo) lives outside the codebase — ask before assuming
any of it is implemented; treat it as intent, not documentation of current
state.

---

## Local development

```bash
make setup     # install per-package dependencies
make chain     # start a local anvil chain + run contracts/script/Deploy.s.sol
make sync-abis # extract trimmed contract ABIs into the SDK/CLI
make up        # docker-compose: postgres, redis, opa, oracle, bcc middleware, dashboard
make test      # run every package's test suite
make test-e2e  # real-browser (Playwright) E2E against a real, freshly-booted stack
```

Each package has its own `README.md` with package-specific detail and its own
test suite. The toolchain (Foundry, Rust, Noir/Barretenberg, OPA, Node, Python)
is pinned in [`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md) §1. See
[`docs/TESTING.md`](docs/TESTING.md) for the full test-pyramid rationale — what
each layer covers, why `make test-e2e` is separate from `make test`, and the
honest current gap (no hosted CI; this repo has no git remote yet).

### Registering an agent (the self-sovereign flow)

```python
from integrity_sdk import registration

# Deploys the agent's 2 direct contracts + 5 clones, funds its wallet, mints
# testnet ITK, and registers it — all signed by the agent's own EVM key.
reg = registration.register_agent(
    "clinical-assistant-01",
    domain_name="healthcare.integrity",
    compliance_vertical="healthcare",
)
print(reg.sovereign_agent, reg.compliance_gate)
```

Requires `FUNDER_PRIVATE_KEY` (a testnet faucet wallet that seeds the agent's
new wallet with gas + ITK) and `INTEGRITY_WALLET_PASSWORD` (encrypts the agent's
EVM keystore). See [`integrity-sdk/README.md`](integrity-sdk/README.md).

---

## Live deployment (Base Sepolia, chainId 84532)

The protocol genesis is deployed and verified on Base Sepolia. Full record in
`deployments.baseSepolia.json`. Key singletons:

| Contract | Address |
|---|---|
| `XibalbaAgentRegistry` | [`0x72e21e44AdD6d6e7CAa02eaedF078630afC40819`](https://sepolia.basescan.org/address/0x72e21e44AdD6d6e7CAa02eaedF078630afC40819) |
| `AgentPrimitivesFactory` | [`0x215f39C8a2Cea2F8c6976fA10bbf48479825aD6e`](https://sepolia.basescan.org/address/0x215f39C8a2Cea2F8c6976fA10bbf48479825aD6e) |
| `IntegrityToken` ($ITK) | [`0x0E87D408732BeC3d3997d9eCE2E20A6679C35655`](https://sepolia.basescan.org/address/0x0E87D408732BeC3d3997d9eCE2E20A6679C35655) |
| `DomainRegistry` | [`0xC1aee61b8826d79c21a335Fb1777cA372Bea1Ba0`](https://sepolia.basescan.org/address/0xC1aee61b8826d79c21a335Fb1777cA372Bea1Ba0) |
| `CoveredEntityRegistry` (Shield) | [`0x3E42C072BA8Ca6EE6E86c8DB011eB4063b8aac07`](https://sepolia.basescan.org/address/0x3E42C072BA8Ca6EE6E86c8DB011eB4063b8aac07) |
| `SmartBAAFactory` (Shield) | [`0xf791059A9E77734f3fd7dffC1ca35728547608eb`](https://sepolia.basescan.org/address/0xf791059A9E77734f3fd7dffC1ca35728547608eb) |

Per-agent primitive addresses are **not** in the static deployments file — they
are resolved live from `XibalbaAgentRegistry` on-chain (and cached by the
oracle). See [`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md) §6.

### Testnet $ITK liquidity comes from an agent, not an operator

`xibalba.integrity` is the protocol's **testnet ITK liquidity source**. Its
`SovereignAgent` (`0x360E2a56…`) holds `MINTER_ROLE` on `IntegrityToken`, and mints are
routed `SovereignAgent.execute → IntegrityToken.mint`, signed by the agent's own
controller (`integrity_sdk.chain.mint_testnet_itk_from_treasury`). Every issued token is
therefore attributable on-chain to a registered agent rather than to an operator key —
the same self-sovereign routing used for anchoring and XNS claims. This is deliberately
exercised on testnet first, so the flow's rough edges surface before any mainnet
deployment.

Registration draws from this agent when `INTEGRITY_LIQUIDITY_AGENT` names a locally
available liquidity agent, falling back to a funder mint (with a warning) otherwise. The
fallback is structural, not laziness: `SovereignAgent.execute` is controller-only, so
minting through the agent requires its controller key on the machine — true for this
single-operator testnet, false for a third party registering their own agent, which would
need a faucet service the liquidity agent runs. The funder EOA retains `MINTER_ROLE` as
issuer of last resort. See [`PRODUCTION_GAPS.md`](PRODUCTION_GAPS.md) §20.

**Known non-conformance, stated plainly:** registration now enforces spec v0.3 §4.1/§7.1
— an agent with no anchored genesis memory root is refused with `400
MemoryNotInitialized`, and `integrity-sdk` anchors that root during registration. But
`StateAnchor` is deployed **per agent**, and every agent registered before this change —
all 7 currently live, including `xibalba.integrity` — still reports `latestRoot == 0`.
They remain registered (the gate only runs at registration) and are therefore registered
agents that do not satisfy the protocol's own persistent-memory primitive until a
controller-signed `anchorRoot` is sent for each. Full detail, plus the six untouched
Appendix A gaps, in [`PRODUCTION_GAPS.md`](PRODUCTION_GAPS.md) §19.

---

## Documentation

- **[`docs/INTERFACE_CONTRACT.md`](docs/INTERFACE_CONTRACT.md)** — the single
  source of truth for cross-package schemas, ports, env vars, the 7-primitive
  architecture, the registration sequence, and the BCC/AIS/Merkle conventions.
- **[`docs/wiki/`](docs/wiki/)** — the compiled knowledge base (entity pages per
  package, concept pages for the protocols). Governed by a strict
  no-aspirational-content rule.
- **[`docs/design/`](docs/design/)** — the dashboard design mockups.

## License

MIT.
