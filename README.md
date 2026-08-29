# Integrity Protocol — v1.0.0-draft

**The compliance gap.** Regulatory counterparties and agent principals need cryptographic proof that an autonomous AI agent's behavior matches its claims. No off-chain system can provide this: once the agent is gone, there's no neutral party to ask. Integrity Protocol solves this by anchoring behavior claims on-chain so a regulator can verify them later, independent of the agent's cooperation.

**The guarantee.** Agents deploy their own identity contracts, anchor telemetry roots, and submit commitments signed by their own key — so the chain proves they control what happened. A scored reputation (AIS) gates participation in sensitive domains. A pre-execution policy layer (`bcc_middleware`) refuses risky actions before they commit. Evidence is redacted to protect regulated content (PHI/PII) while preserving enough signal for trust computation.

Three repositories, one closed loop:
- **Integrity Protocol** (this repo): the trust & scoring primitives (`integrity-core`), operator dashboard (`integrity-dashboard`), and the oracle that computes reputation
- **Xibalba Shield**: endpoint security and enforcement; produces signed evidence for the oracle
- **Xibalba Cortex**: agent's local memory store; anchors session roots into the protocol

## Canonical documents

| File | Audience |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Implementers (normative protocol grammar, invariants, status tags) |
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | Decision-makers and auditors (narrative, guarantees, architecture) |
| [docs/CONTROLS_MATRIX.md](docs/CONTROLS_MATRIX.md) | Auditors (evidence map: HIPAA, NIST, OWASP, AIUC-1) |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Builders (build order and phase gates) |

**Archived material is not normative.** Files moved to `docs/archive/` reflect the prior design iteration and remain accessible for historical context, but are not the source of truth. See [docs/archive/README.md](docs/archive/README.md).

## Implementation status

**Current state (as of 2026-08-20).** This is a strong testnet prototype, not production-ready. For exact implementation status of each v1 requirement, see [docs/SPEC.md](docs/SPEC.md) §13 (Status tags). The testnet Base Sepolia deployment has all identity, reputation, and HIPAA/healthcare primitives live; the gateway middleware is tested locally; the dashboard is integrated against live chain and oracle reads/writes.

**Honest gaps.** All six protocol roles (arbitrator, disputer, funder, governance, oracle, resolver) are currently a single operator EOA — appropriate for a testnet, not for any deployment where trust has economic value. The Base Sepolia ZK verifier holds older placeholder bytecode and does not verify real proofs yet (fixed and tested locally; deployment pending). `SovereignAgent`/`StateAnchor` are per-agent and non-upgradeable, so the upgrade-path strategy must be decided before the first mainnet agent exists. See [PRODUCTION_GAPS.md](PRODUCTION_GAPS.md) for the complete list, and [docs/MAINNET_READINESS.md](docs/MAINNET_READINESS.md) for deployment blockers.

## Packages and deliverables

This single repository contains six independently-versioned packages, orchestrated by a root Makefile. See each package's own README for detailed documentation.

| Package | Role | Status |
|---|---|---|
| `contracts/` | On-chain primitives: identity, reputation, HIPAA/healthcare vertical, experimental Phase I kernel slice | 250 tests locally; Base Sepolia genesis deployed |
| `integrity-zkp/` | Real Noir/Barretenberg ZK circuit for intent binding and reputation boost | Real pipeline working locally; Base Sepolia verifier holds placeholder bytecode |
| `integrity-oracle/` | Telemetry ingestion, AIS computation, on-chain reads, markets/leaderboard/governance APIs | 80 lib + 9 e2e tests locally; single-operator oracle |
| `integrity-sdk/` | Agent library: identity, wallet, registration, telemetry, BCC, markets | 259 tests locally |
| `integrity-cli/` | Developer CLI: standalone identity/wallet/registration reimplementation (not a wrapper around SDK) | 57 tests locally |
| `bcc_middleware/` | Pre-execution policy gate, HIPAA BAA check, Merkle anchoring | 91 pytest + 28 OPA policy tests locally |
| `integrity-userapi/` | User accounts, API keys, JWT, login rate limiting | 51 tests locally |
| `integrity-dashboard/` | Operator dashboard and closed-loop demo scenario engine | 9 vitest + 20 Playwright e2e tests locally |

For exact per-component status, see [docs/SPEC.md](docs/SPEC.md) §13.

### Integrity Health (HIPAA/healthcare vertical)

The protocol's flagship proof is a healthcare-specific gateway that ensures agents handling PHI (Protected Health Information) are cryptographically compliant: anchored memory, reputation floors, pre-execution policy gates, and HIPAA Business Associate Agreements.

On registration, a healthcare agent must declare compliance and anchor its controllers to a `CoveredEntity` (hospital, clinic, insurer). The dashboard surfaces live BAA status, patient-data audit trails, and escalation workflows for policy violations. This is not a side feature — it's the demonstration that makes the rest of the protocol credible for regulated domains.

## Core concepts

**Persistent Memory (Primitive #1):** An agent anchors its telemetry commitments on-chain via its own `StateAnchor` contract. The genesis memory root is signed by the agent's controller, and the oracle re-reads it before registration — an agent with no memory cannot register.

**Agent-Owned Contracts (Primitive #2):** Every agent deploys two contracts directly (`SovereignAgent`, `StateAnchor`) and clones five more (`ReputationRegistry`, `Slasher`, `VerifierRegistry`, `ComplianceGate`, `AgentProfile`). All state changes route through the agent's own `SovereignAgent.execute()`, so the chain proves the agent controls what it claims.

**Authority (Primitive #3):** In Integrity Health (healthcare), agents must bind their controllers to a `CoveredEntity` and agree to a HIPAA Business Associate Agreement. Pre-execution policy gates refuse risky actions before they commit.

**Reputation (Primitive #4):** The Agent Integrity Score (AIS) is a weighted geometric mean of four component signals: entropy (reasoning diversity), grounding (cite backing), sacrifice (resource commitment), and compliance (rule adherence). Zero in any component means zero overall — aspirational averaging has no place here.

For the full conceptual derivation, see [docs/SPEC.md](docs/SPEC.md) §4.

---

## Quick start

```bash
make setup     # install every package's dependencies
make chain     # start local anvil + deploy genesis
make test      # run all package suites
make up        # docker-compose: postgres, redis, opa, oracle, dashboard
make test-e2e  # playwright e2e against live stack
```

Toolchain pinned in [docs/INTERFACE_CONTRACT.md](docs/INTERFACE_CONTRACT.md) §1. For per-package development, see each package's own README.

### Registering an agent

```python
from integrity_sdk import registration

reg = registration.register_agent(
    "my-agent",
    domain_name="integrity",
    compliance_vertical=None,  # or "healthcare" for Integrity Health
)
```

Requires `FUNDER_PRIVATE_KEY` (testnet faucet) and `INTEGRITY_WALLET_PASSWORD`. See [integrity-sdk/README.md](integrity-sdk/README.md).

---

## Live deployment

**Base Sepolia, chainId 84532.** Full deployments record in `deployments.baseSepolia.json`. Key singletons at:
- `XibalbaAgentRegistry`: `0x72e21e44AdD6d6e7CAa02eaedF078630afC40819`
- `AgentPrimitivesFactory`: `0x215f39C8a2Cea2F8c6976fA10bbf48479825aD6e`
- `IntegrityToken` ($ITK): `0x0E87D408732BeC3d3997d9eCE2E20A6679C35655`
- `CoveredEntityRegistry` (Integrity Health): `0x3E42C072BA8Ca6EE6E86c8DB011eB4063b8aac07`

**Before mainnet:** read [docs/MAINNET_READINESS.md](docs/MAINNET_READINESS.md) for the consequence-ordered blocker list. The headline items: all six protocol roles are currently one EOA; the Base Sepolia ZK verifier holds placeholder bytecode; `SovereignAgent`/`StateAnchor` are per-agent and non-upgradeable.

---

## Reference documentation

- **[docs/SPEC.md](docs/SPEC.md)** — normative protocol specification (canonical source)
- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — narrative and architecture
- **[docs/CONTROLS_MATRIX.md](docs/CONTROLS_MATRIX.md)** — audit controls map (HIPAA, NIST, OWASP, AIUC-1)
- **[docs/INTERFACE_CONTRACT.md](docs/INTERFACE_CONTRACT.md)** — cross-package schemas, ports, env vars, registration sequence
- **[docs/MAINNET_READINESS.md](docs/MAINNET_READINESS.md)** — deployment blockers
- **[PRODUCTION_GAPS.md](PRODUCTION_GAPS.md)** — unbuilt requirements and disclosed limitations
- **[docs/TESTING.md](docs/TESTING.md)** — test pyramid and E2E scope
- **[docs/archive/](docs/archive/)** — historical specifications and design iterations (not normative)
- **[spec/ais-api/](spec/ais-api/)** — read-side wire specification (v1, frozen)

## License

MIT.
