# contracts

The on-chain heart of the Integrity Protocol: the 7 agent primitives, the factory
that deploys them, the shared registries, the `$ITK` token, the Integrity Health
(HIPAA) stack, and the ZK verifier. Solidity `0.8.28`, built and tested with
Foundry.

> Ground rule (repo-wide): **no silent mocks.** See
> [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md).

## The self-sovereign model

The central design choice: **an agent deploys and owns its own contracts.** There
is no privileged factory that registers agents into shared global state. Instead:

- The agent's **own wallet** directly deploys `SovereignAgent` and `StateAnchor`.
  The deploy transactions are signed by the agent's key — that signature *is* the
  proof of self-sovereign control.
- `AgentPrimitivesFactory` then clones the other 5 primitives as **EIP-1167
  minimal proxies** (cheap: ~50k gas each vs. a full deploy) and registers all 7
  addresses atomically in `XibalbaAgentRegistry`.

### The 7 primitives

| # | Contract | Deploy | Source |
|---|---|---|---|
| 1 | `SovereignAgent` | direct | `src/core/SovereignAgent.sol` |
| 2 | `StateAnchor` | direct | `src/oracle/StateAnchor.sol` |
| 3 | `ReputationRegistry` | clone | `src/oracle/ReputationRegistry.sol` |
| 4 | `Slasher` | clone | `src/oracle/Slasher.sol` |
| 5 | `VerifierRegistry` | clone | `src/oracle/VerifierRegistry.sol` |
| 6 | `ComplianceGate` | clone | `src/health/ComplianceGate.sol` |
| 7 | `AgentProfile` | clone | `src/framework/AgentProfile.sol` |

The 5 clone contracts are `Initializable` (OpenZeppelin upgradeable): their
implementation is deployed once with `_disableInitializers()`, and each agent's
clone is set up via `initialize(...)`, never a constructor. A subtle footgun this
guards against — inline field initializers (`x = 3 days`) compile into the
*constructor*, which clones never run; every such default is set explicitly in
`initialize` instead (see `Slasher.disputeWindow` / `ReputationRegistry.reportingPeriod`).

### Call-routing convention (load-bearing)

Every clone's `DEFAULT_ADMIN_ROLE` is granted to the agent's `SovereignAgent`
*contract* address — not the raw EOA. All post-registration state changes route
through `SovereignAgent.execute(cloneAddr, 0, calldata)`. The one exception is the
bootstrap `AgentPrimitivesFactory.registerPrimitives` call itself (SovereignAgent
can't route the call that registers it), which is EOA-signed and verified by
checking `SovereignAgent.hasRole(DEFAULT_ADMIN_ROLE, msg.sender)`.

`Slasher`'s admin/arbiter is protocol **governance**, never the agent — an agent
can't be trusted to arbitrate its own slashing dispute.

## Singletons (deployed once, shared)

`IntegrityToken` ($ITK), `UltraPlonkVerifier`, `XibalbaAgentRegistry`,
`DomainRegistry`, plus the Integrity Health stack (`CoveredEntityRegistry`,
`SmartBAAFactory`, `HIPAAGuardrailRegistry`) and the 5 clone *implementations*.

### Integrity Health (HIPAA vertical)

The flagship regulated-industry proof. `EHRGate` enforces all three of: patient
consent **and** an active on-chain Business Associate Agreement (`SmartBAA`)
**and** a minimum reputation — resolving the requesting agent's own
`ReputationRegistry` clone live via `XibalbaAgentRegistry`. `ComplianceGate` is
the per-agent, read-optimized surface that answers "is this agent HIPAA-compliant
right now" by delegating to the real `CoveredEntityRegistry`/`SmartBAAFactory` —
it never fakes a `true`.

## Build & test

```bash
forge build
forge test            # 209 tests verified 2026-08-17
```

Tests cover every contract, including full end-to-end coverage of the
registration sequence in `test/AgentPrimitivesFactory.t.sol` (real
`SovereignAgent` deploy → `StateAnchor` deploy → `execute`-routed role grant →
`registerPrimitives`, asserting independent clones and correct admin wiring).

`via_ir = true` is enabled: `registerPrimitives` clones+initializes 5 contracts in
one function and hits "stack too deep" under legacy codegen.

## Deploy

```bash
# Local anvil
anvil &
FUNDER_PRIVATE_KEY=0xac09…ff80 \
  forge script script/Deploy.s.sol --rpc-url anvil --broadcast

# Base Sepolia (needs a funded deployer wallet)
cp .env.example .env   # fill FUNDER_PRIVATE_KEY, BASE_SEPOLIA_RPC_URL
forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast
```

`Deploy.s.sol` deploys every singleton (including the local
`IntegrityIdentityReadV1` facade) + the 5 clone implementations +
`AgentPrimitivesFactory`, wires `REGISTRAR_ROLE`, bootstraps the
`general.integrity` and `healthcare.integrity` domains, and writes the deployment
record to `../deployments.<network>.json`.

### Deployments file shape

Per [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) §6 — nested,
not a flat map. Per-agent primitive addresses are deliberately **absent** (they
don't scale to a static file); they're resolved live from `XibalbaAgentRegistry`.

```json
{
  "chainId": 84532,
  "singletons": { "XibalbaAgentRegistry": "0x…", "AgentPrimitivesFactory": "0x…", … },
  "cloneTemplates": { "ReputationRegistry": "0x…", "Slasher": "0x…", … },
  "protocolAddresses": { "oracleSigner": "0x…", "governance": "0x…", "funderWallet": "0x…" },
  "domains": { "general.integrity": "0x…", "healthcare.integrity": "0x…" }
}
```

## Live on Base Sepolia (chainId 84532)

See the repo root [`README.md`](../README.md#live-deployment-base-sepolia-chainid-84532)
and `deployments.baseSepolia.json` for the full address set.

## Known gaps (honest)

- `UltraPlonkVerifier.sol` is the generated ~2465-line UltraHonk verifier in
  local source, with real-proof positive and negative Foundry tests. The
  existing Base Sepolia singleton was deployed from the older fail-closed
  placeholder and has not been replaced; do not infer deployed behavior from
  the current source tree.
- `CCIPReputationBridge.sol` was reworked 2026-07-11 for the per-agent EIP-1167
  clone model: it now resolves each agent's own `ReputationRegistry` clone via
  `XibalbaAgentRegistry` on every call, instead of holding one immutable
  pre-clone-model registry address. It is still **not** deployed by
  `script/Deploy.s.sol`, but that's now a genuine operational decision — a peer
  bridge needs a real second chain to be meaningful — not an architectural
  incompatibility. See its own NatSpec for the full rework rationale.

## Layout

```
src/
  core/        SovereignAgent, IAccount
  framework/   XibalbaAgentRegistry, AgentPrimitivesFactory, DomainRegistry, AgentProfile
  oracle/      ReputationRegistry, Slasher, StateAnchor, VerifierRegistry,
               IntegrityToken, UltraPlonkVerifier, CCIPReputationBridge
  health/      CoveredEntityRegistry, SmartBAAFactory, SmartBAA,
               HIPAAGuardrailRegistry, EHRGate, ComplianceGate
script/Deploy.s.sol
test/          focused suites for contracts and deployment invariants (209 tests on 2026-08-17)
```
