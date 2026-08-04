# Smart contract development guide

How to write, test, and deploy a Solidity contract in this repo's `contracts/`
package — grounded in the actual patterns already used here, not generic
Foundry-tutorial content. If you haven't already, read
[`contracts/README.md`](../../contracts/README.md) first for the package's
overall architecture (the self-sovereign model, the 7 agent primitives,
call-routing convention); this guide is the "how do I add a contract"
companion to that.

For deeper background on specific concepts referenced below, see the wiki
rather than duplicating it here:
- [`docs/wiki/entities/contracts.md`](../wiki/entities/contracts.md) — full
  contract inventory, invariants, current deployed state.
- [`docs/wiki/concepts/agent-primitives.md`](../wiki/concepts/agent-primitives.md)
  — the 7-primitive self-sovereign model and the `SovereignAgent.execute`
  call-routing convention referenced in §6 below.
- [`docs/INTERFACE_CONTRACT.md`](../INTERFACE_CONTRACT.md) — the cross-package
  toolchain/env-var reference (§1–3) and the `deployments.<network>.json`
  schema (§6).

## 1. Repo/toolchain setup

Everything contract-related lives under `contracts/`. Solidity `0.8.28`,
built and tested with [Foundry](https://github.com/foundry-rs/foundry)
(`forge`/`anvil`/`cast`, pinned to `1.7.1` per
`docs/INTERFACE_CONTRACT.md`).

```bash
cd contracts
npm install          # pulls node_modules/@openzeppelin, @chainlink/contracts-ccip, etc. — see remappings.txt
forge build
forge test            # 165 tests as of this writing
```

`via_ir = true` is set in `contracts/foundry.toml` — required because
`AgentPrimitivesFactory.registerPrimitives` clones+initializes 5 contracts in
one function and hits "stack too deep" under the legacy codegen. You won't
normally need to touch this, but if you add a function that also clones/inits
several contracts in one call and see a stack-too-deep error, this is why
`via_ir` is already on rather than something to newly enable.

### Directory layout

```
contracts/
  src/
    core/        SovereignAgent, IAccount
    framework/   XibalbaAgentRegistry, AgentPrimitivesFactory, DomainRegistry,
                 AgentProfile, XibalbaNameService
    oracle/      ReputationRegistry, Slasher, StateAnchor, VerifierRegistry,
                 IntegrityToken, UltraPlonkVerifier, CCIPReputationBridge
    health/      CoveredEntityRegistry, SmartBAAFactory, SmartBAA,
                 HIPAAGuardrailRegistry, EHRGate, ComplianceGate
    markets/     IntegrityMarket, MarketFactory, A2ACapitalPool
  test/          one *.t.sol per contract (mirrors src/ subdirectory names,
                 e.g. test/health/, test/markets/)
  script/        Deploy.s.sol, DeployMarkets.s.sol, FixComplianceGateFactory.s.sol
  foundry.toml
  remappings.txt
```

A new contract goes in the `src/` subdirectory that matches its role (a new
registry/framework-level contract goes in `src/framework/`, a new
oracle-adjacent contract in `src/oracle/`, etc.), and its test goes in the
matching `test/` subdirectory with the exact same base name +
`.t.sol`.

## 2. Worked example: a new contract from scratch

We'll write `AgentEndorsementRegistry` — a small, self-contained example
distinct from anything in `src/`: it lets one registered agent publicly
endorse another (a simple reputation-adjacent signal, deliberately *not*
wired into `ReputationRegistry`/AIS scoring — just a standalone registry to
demonstrate the pattern). It follows the same conventions as
`XibalbaNameService` (`contracts/src/framework/XibalbaNameService.sol`),
which is the most recently added, simplest self-contained contract in this
codebase and the best template to copy from.

Confirmed conventions (grepped against the existing `src/` tree before
writing this):

- **OpenZeppelin `AccessControl`**, not `Ownable` — every contract that needs
  any privileged role (even just one) inherits `AccessControl` and grants
  `DEFAULT_ADMIN_ROLE` to an `admin` constructor param. Role constants are
  `bytes32 public constant X_ROLE = keccak256("X_ROLE");`.
- **Custom errors, not `require(..., "string")`**, for the overwhelming
  majority of revert paths — `grep -rc "error " contracts/src/**/*.sol` shows
  essentially every contract defines its own `error` set and uses
  `if (cond) revert SomeError();`. (`SovereignAgent.sol` has two
  string-`require`s left over on its zero-address checks — that's a minor,
  pre-existing inconsistency, not the pattern to copy; use custom errors.)
- **NatSpec**: `@title`/`@notice` on the contract, `@notice` on every external
  function explaining the *why*/trust model (not just restating the
  signature), `@dev` for implementation footguns or non-obvious ordering
  constraints. Comments routinely reference sibling contracts and the
  specific invariant they preserve (see `XibalbaNameService.sol`'s NatSpec on
  why it's deliberately *not* a port of the legacy admin-gated version).
- **`bytes32` keys over `string` keys** in mappings — hash the human-readable
  string once (`keccak256(bytes(x))`) and key everything off that, keeping a
  reverse `bytes32 => string` mapping only where you need to hand a
  human-readable value back to a caller.
- Self-service, first-come-first-served patterns (`register`-style functions)
  check the caller's standing live against `XibalbaAgentRegistry`
  (`isRegisteredAgent(msg.sender)`) rather than trusting an admin-supplied
  flag — see §6 below on why `msg.sender` being the agent's `SovereignAgent`
  contract address matters.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {XibalbaAgentRegistry} from "./XibalbaAgentRegistry.sol";

/// @title AgentEndorsementRegistry
/// @notice Lets one registered agent publicly endorse another (`msg.sender` must itself be
/// a registered agent's `SovereignAgent` address, verified live against
/// `XibalbaAgentRegistry` — same trust model `XibalbaNameService.register` uses). Standalone
/// signal, not wired into `ReputationRegistry`/AIS scoring.
/// @dev Self-service, no privileged party in the critical path — mirrors
/// `XibalbaNameService`'s self-sovereign registration pattern rather than an admin-gated one.
contract AgentEndorsementRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    /// @dev Immutable: the canonical registry this deployment checks endorser eligibility
    /// against, same rationale as `XibalbaNameService.agentRegistry`.
    XibalbaAgentRegistry public immutable agentRegistry;

    /// @notice endorser => endorsed => whether an active endorsement exists.
    mapping(address => mapping(address => bool)) public hasEndorsed;
    /// @notice endorsed => running count of active endorsements.
    mapping(address => uint256) public endorsementCount;

    event Endorsed(address indexed endorser, address indexed endorsed);
    event EndorsementRevoked(address indexed endorser, address indexed endorsed);

    error NotRegisteredAgent();
    error CannotEndorseSelf();
    error AlreadyEndorsed();
    error NoSuchEndorsement();

    constructor(address admin, address agentRegistry_) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        agentRegistry = XibalbaAgentRegistry(agentRegistry_);
    }

    /// @notice Self-service endorsement. Both `msg.sender` and `endorsed` must be
    /// registered agents' `SovereignAgent` addresses, verified live — matching how
    /// `XibalbaNameService.register` and `ComplianceGate` treat the calling
    /// `SovereignAgent` contract as the acting agent's identity.
    function endorse(address endorsed) external {
        if (!agentRegistry.isRegisteredAgent(msg.sender)) revert NotRegisteredAgent();
        if (!agentRegistry.isRegisteredAgent(endorsed)) revert NotRegisteredAgent();
        if (endorsed == msg.sender) revert CannotEndorseSelf();
        if (hasEndorsed[msg.sender][endorsed]) revert AlreadyEndorsed();

        hasEndorsed[msg.sender][endorsed] = true;
        endorsementCount[endorsed] += 1;
        emit Endorsed(msg.sender, endorsed);
    }

    /// @notice Voluntary self-revocation of an endorsement the caller itself made.
    function revokeEndorsement(address endorsed) external {
        if (!hasEndorsed[msg.sender][endorsed]) revert NoSuchEndorsement();
        hasEndorsed[msg.sender][endorsed] = false;
        endorsementCount[endorsed] -= 1;
        emit EndorsementRevoked(msg.sender, endorsed);
    }
}
```

This would live at `contracts/src/framework/AgentEndorsementRegistry.sol`
(framework-level registry, same directory as `XibalbaNameService.sol` and
`XibalbaAgentRegistry.sol`).

## 3. Writing its Foundry test

Test file: `contracts/test/AgentEndorsementRegistry.t.sol`. The conventions
below are confirmed by grepping `contracts/test/` — `XibalbaNameService.t.sol`
is the closest existing template since it has the exact same
"register a real agent via `XibalbaAgentRegistry`, then act as it"
setup shape.

- `address foo = makeAddr("foo");` for every test actor — not raw literals.
- `vm.prank(x)` before a single call as `x`; `vm.startPrank(x)` /
  `vm.stopPrank()` when an actor makes several calls in a row.
- `vm.expectRevert(Contract.ErrorName.selector)` immediately before the call
  expected to revert — confirmed all over `contracts/test/` (e.g.
  `contracts/test/SovereignAgent.t.sol:48`,
  `contracts/test/XibalbaAgentRegistry.t.sol:102`,
  `contracts/test/CCIPReputationBridge.t.sol:96`). Use the bare
  `vm.expectRevert()` (no selector) only for an `AccessControl` role-check
  revert you don't want to hardcode OZ's own custom-error encoding for (see
  `XibalbaNameService.t.sol`'s `test_nonRegistrarCannotForceRevoke`).
- To get a real `isRegisteredAgent(...) == true` address, don't fake it —
  actually call `XibalbaAgentRegistry.registerPrimitives(...)` in `setUp()`
  with a full `PrimitiveSet` struct (other primitive fields can be
  `makeAddr(...)` placeholders; only the `sovereignAgent` field is checked by
  most agent-facing contracts).

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentEndorsementRegistry} from "../src/framework/AgentEndorsementRegistry.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";

contract AgentEndorsementRegistryTest is Test {
    AgentEndorsementRegistry endorsements;
    XibalbaAgentRegistry registry;

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");
    address agentA = makeAddr("agentA");
    address agentB = makeAddr("agentB");
    address stranger = makeAddr("stranger");

    bytes32 domainId = keccak256("general.integrity");

    function setUp() public {
        registry = new XibalbaAgentRegistry(admin);
        vm.prank(admin);
        registry.grantRole(registry.REGISTRAR_ROLE(), registrar);

        endorsements = new AgentEndorsementRegistry(admin, address(registry));

        _registerAgent(agentA, "did:integrity:agent-a");
        _registerAgent(agentB, "did:integrity:agent-b");
    }

    function _registerAgent(address sovereignAgent, string memory did) internal {
        XibalbaAgentRegistry.PrimitiveSet memory primitives = XibalbaAgentRegistry.PrimitiveSet({
            sovereignAgent: sovereignAgent,
            stateAnchor: makeAddr(string.concat(did, "-stateAnchor")),
            reputationRegistry: makeAddr(string.concat(did, "-reputationRegistry")),
            slasher: makeAddr(string.concat(did, "-slasher")),
            verifierRegistry: makeAddr(string.concat(did, "-verifierRegistry")),
            complianceGate: makeAddr(string.concat(did, "-complianceGate")),
            agentProfile: makeAddr(string.concat(did, "-agentProfile"))
        });
        bytes32 didHash = registry.didHash(did);
        vm.prank(registrar);
        registry.registerPrimitives(didHash, primitives, controller, domainId);
    }

    function test_registeredAgentCanEndorseAnother() public {
        vm.prank(agentA);
        endorsements.endorse(agentB);

        assertTrue(endorsements.hasEndorsed(agentA, agentB));
        assertEq(endorsements.endorsementCount(agentB), 1);
    }

    function test_unregisteredCallerCannotEndorse() public {
        vm.prank(stranger);
        vm.expectRevert(AgentEndorsementRegistry.NotRegisteredAgent.selector);
        endorsements.endorse(agentB);
    }

    function test_cannotEndorseSelf() public {
        vm.prank(agentA);
        vm.expectRevert(AgentEndorsementRegistry.CannotEndorseSelf.selector);
        endorsements.endorse(agentA);
    }

    function test_cannotDoubleEndorse() public {
        vm.prank(agentA);
        endorsements.endorse(agentB);

        vm.prank(agentA);
        vm.expectRevert(AgentEndorsementRegistry.AlreadyEndorsed.selector);
        endorsements.endorse(agentB);
    }

    function test_endorserCanRevokeTheirOwnEndorsement() public {
        vm.startPrank(agentA);
        endorsements.endorse(agentB);
        endorsements.revokeEndorsement(agentB);
        vm.stopPrank();

        assertFalse(endorsements.hasEndorsed(agentA, agentB));
        assertEq(endorsements.endorsementCount(agentB), 0);
    }
}
```

Run just this file while iterating:

```bash
forge test --match-path test/AgentEndorsementRegistry.t.sol -vv
```

Then run the full suite before committing:

```bash
forge test
```

## 4. Wiring it into the deploy flow

### Genesis vs. incremental deploy

There are two deploy scripts, and which one you touch depends on the
contract's relationship to already-registered agents:

- **`contracts/script/Deploy.s.sol`** — the genesis script. Deploys every
  protocol singleton, the 5 clone implementations, and
  `AgentPrimitivesFactory`, then bootstraps the two open domains. Only run
  against a *fresh* chain — re-running it against a live network would
  deploy a brand-new `XibalbaAgentRegistry` with zero agents in it, orphaning
  every real registration.
- **`contracts/script/DeployMarkets.s.sol`** — the template for *incremental*
  deploys onto an already-live protocol. It reads the existing
  `../deployments.<network>.json`, deploys only the new contract(s) against
  the existing `IntegrityToken`/`XibalbaAgentRegistry` addresses, and
  re-serializes the *entire* file (every pre-existing field, read back via
  `vm.parseJsonAddress`/`vm.parseJsonBytes32`) with the new addresses merged
  in — never overwriting unrelated fields.

For a brand-new singleton like `AgentEndorsementRegistry` that doesn't yet
exist on Base Sepolia, follow the `DeployMarkets.s.sol` pattern: a new
`DeployAgentEndorsementRegistry.s.sol` (or add it inside `Deploy.s.sol` if
you're touching genesis before it's ever been broadcast anywhere).

Wiring into `Deploy.s.sol` looks like this (mirrors how `xns` was added — see
`contracts/script/Deploy.s.sol` lines 118, 197, 222):

1. Import it: `import {AgentEndorsementRegistry} from "../src/framework/AgentEndorsementRegistry.sol";`
2. Add a contract-level state var: `AgentEndorsementRegistry endorsements;`
3. Deploy it in `_deploySingletons()`:
   `endorsements = new AgentEndorsementRegistry(deployer, address(registry));`
4. Log it in `_logSummary()`.
5. Serialize it into the `singletons` JSON object in `_writeDeploymentsFile()`:
   `vm.serializeAddress(singletons, "AgentEndorsementRegistry", address(endorsements));`

For an incremental deploy (the `DeployMarkets.s.sol` shape), you'd instead
read the existing file, deploy just the new contract, and re-serialize
*every* existing field plus the one new address — see
`DeployMarkets.s.sol`'s `_mergeDeploymentsFile()` for the exact pattern (note
the bracket path form `'.domains["general.integrity"]'` for keys containing a
literal `.`, since forge-std's JSON parser otherwise treats the dot as a
nesting separator).

### `deployments.<network>.json`

Per `docs/INTERFACE_CONTRACT.md` §6, the file is nested
(`singletons` / `cloneTemplates` / `protocolAddresses` / `domains`), not a
flat map, and deliberately excludes per-agent primitive addresses (those are
resolved live from `XibalbaAgentRegistry` instead — they don't scale to a
static file). `contracts/foundry.toml`'s `fs_permissions` explicitly
allow-lists read-write access to `../deployments.local.json` and
`../deployments.baseSepolia.json` — a script targeting a different file path
will fail on `vm.writeJson`/`vm.readFile` until that allow-list is extended.

### `make sync-abis`

After any change to a contract's interface (new function, new error, brand
new contract another package needs to call), run:

```bash
make sync-abis
```

This runs `forge build` then `scripts/sync_abis.py`, which extracts
`{abi, bytecode}` out of `contracts/out/<File>.sol/<Contract>.json` for the
specific contract list in that script's `CONTRACTS` tuple, and writes trimmed
JSON into **both** `integrity-sdk/integrity_sdk/abis/` and
`integrity-cli/integrity_cli/abis/` (the CLI deliberately carries its own
copy rather than importing `integrity_sdk.abis` — see that script's own
docstring). If you add a contract that a Python package needs to deploy or
call directly (as opposed to one only ever touched by other Solidity
contracts), you must also add a `("YourContract", "YourContract")` tuple to
`scripts/sync_abis.py`'s `CONTRACTS` list — see the `XibalbaNameService`
entry there for the exact comment style to follow (what it's for, which
package/command consumes it, when it was added).

## 5. Local deploy + verification

### Local anvil

```bash
make chain
```

This is `cd contracts && anvil &` (backgrounded), a 2-second wait, then
`forge script script/Deploy.s.sol --rpc-url http://localhost:8545 --broadcast`
— see the `chain:` target in the repo-root `Makefile`. It needs
`FUNDER_PRIVATE_KEY` set in the environment (anvil's well-known default
account #0 key works fine locally). Output lands in
`deployments.local.json` at the repo root (`contracts/foundry.toml`'s
`fs_permissions` only allow `../deployments.local.json` and
`../deployments.baseSepolia.json`, confirming those are the only two valid
targets).

Equivalently, from inside `contracts/`:

```bash
anvil &
FUNDER_PRIVATE_KEY=<anvil-account-0-private-key> \
  forge script script/Deploy.s.sol --rpc-url anvil --broadcast
```

(`anvil` here resolves via the `[rpc_endpoints]` alias in `foundry.toml`,
which reads `${RPC_URL}` — set `RPC_URL=http://127.0.0.1:8545` if you use the
alias form instead of the literal URL form `make chain` uses.)

### Base Sepolia

From `contracts/`:

```bash
cp .env.example .env   # fill in FUNDER_PRIVATE_KEY, BASE_SEPOLIA_RPC_URL
forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast --verify
```

Required env vars (see `contracts/.env.example` for the full annotated
list):

- `BASE_SEPOLIA_RPC_URL` — defaults to `https://sepolia.base.org` in the
  example file; get a dedicated Alchemy/Infura endpoint for anything
  high-frequency, the public endpoint rate-limits aggressively.
- `FUNDER_PRIVATE_KEY` — **must be 0x-prefixed hex** (`vm.envUint` rejects a
  bare hex string without the prefix). This wallet deploys every
  singleton/clone-implementation *and* later seeds each newly-registered
  agent's wallet with test ETH — never a real/mainnet key.
- `ORACLE_SIGNER_ADDRESS` / `DISPUTER_ADDRESS` / `GOVERNANCE_ADDRESS` /
  `ARBITRATOR_ADDRESS` — optional, all default to the deployer address for a
  single-operator testnet deploy (see `Deploy.s.sol::run()`'s
  `vm.envOr(...)` calls). A production deployment should split these onto
  separate keys — `GOVERNANCE_ADDRESS`/`DISPUTER_ADDRESS` arbitrate slashing
  disputes *against* agents and must not be the same key that
  deploys/administers everything else.
- `BASESCAN_API_KEY` — optional, needed only for `--verify` to actually
  submit source to BaseScan.

If you're deploying an *incremental* addition onto the already-live Base
Sepolia protocol (the `DeployMarkets.s.sol` case), the invocation is the same
shape, just a different script:

```bash
forge script script/DeployMarkets.s.sol --rpc-url base_sepolia --broadcast --verify
```

This requires `../deployments.baseSepolia.json` to already exist (i.e.
genesis `Deploy.s.sol` has already run once against Base Sepolia — it has,
see `contracts/README.md`'s "Live on Base Sepolia" section and the root
`README.md` for the current live address set).

After deploying, run `make sync-abis` (§4) so `integrity-sdk`/`integrity-cli`
can pick up the new/changed ABI.

## 6. On-chain auth: who signs what

Before writing any function that changes state, understand this repo's
call-routing convention — it determines whether your function should expect
`msg.sender` to be a `SovereignAgent` *contract* address or a raw human/
covered-entity EOA. Full details:
[`docs/wiki/concepts/agent-primitives.md`](../wiki/concepts/agent-primitives.md#call-routing-convention-load-bearing).

The short version:

- **Agent-attributable actions** (anything that should be provably "this
  registered agent did X") route through
  `SovereignAgent.execute(targetAddr, 0, calldata)` — the clone's
  `DEFAULT_ADMIN_ROLE`/permissions are granted to the agent's
  `SovereignAgent` **contract** address, never its raw EOA, so a direct call
  from the EOA will fail an `onlyRole`/ownership check. This is why
  `AgentEndorsementRegistry.endorse` above checks
  `agentRegistry.isRegisteredAgent(msg.sender)` — the "agent" whose
  endorsement is being recorded *is* the `SovereignAgent` contract address,
  reachable only via `execute` in the general case (self-service registries
  like this one and `XibalbaNameService` are the one class of exception,
  since the *whole point* is any registered agent can self-serve without a
  governance/covered-entity intermediary — see `XibalbaNameService.sol`'s
  NatSpec for why that specific contract chose that shape).
- **Human / covered-entity actions** — e.g. `CoveredEntityRegistry`
  registrar calls, `SmartBAA` signing, protocol-governance role grants — are
  direct EOA calls, because the actor genuinely isn't an on-chain agent
  identity at all; there's no `SovereignAgent` contract to route through.
- The one deliberate bootstrap exception on the agent side:
  `AgentPrimitivesFactory.registerPrimitives` itself must be EOA-signed
  (the `SovereignAgent` can't route the call that registers it), and is
  instead gated by checking
  `SovereignAgent.hasRole(DEFAULT_ADMIN_ROLE, msg.sender)`.

If you're unsure which shape a new write function needs, ask: "is this state
change something a registered agent does on its own behalf, or something a
human/covered-entity/governance actor does about an agent?" The former routes
through `SovereignAgent.execute`; the latter is a direct EOA call.
