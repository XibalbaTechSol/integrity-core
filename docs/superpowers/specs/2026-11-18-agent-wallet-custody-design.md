# Agent wallet and key custody — design

Status: **proposed (non-authoritative)**. Date: 2026-11-18. Owner decision: approach A (below).
Review provenance: Devil's Advocate engine is not entitled (`ENGINE_NOT_IN_PLAN`); this design was
red-teamed via the advisor model plus self-review, then a fresh-builder check. It amends SPEC §5.3
only as a *proposal* (see §6.4) until reviewed, implemented, tested and accepted.

## 1. The question this answers

> "When an agent transacts ITK, which wallet does it use, and how is the key saved?"

**Answer.** Every agent that moves Integrity tokens has exactly one on-chain address: its
`SovereignAgent` smart account. That one address is simultaneously

- the agent0 / ERC-8004 passport's `agentWallet`,
- the `AgentRegistry` record's `actor`,
- the `StakeVault` / `AISRegistry` key, and
- the address that holds the agent's ITK and the one the console displays.

No single key controls that address. Control is split into roles inside the contract, and what the
agent itself holds is a bounded **operator** key. What the operator may do is set by its human
**owner** in the console and enforced on-chain.

### 1.1 Key table

| Key | Curve | Where it is saved | What it can do on the `SovereignAgent` | If it leaks | Rotation |
|---|---|---|---|---|---|
| **Owner** (human) | secp256k1 | The human's own wallet (MetaMask/Coinbase/hardware) via the console's browser-wallet path (`agent0.ts` `registerAgent0WithWallet` already does this). **Never on the agent host.** | All admin: set/replace policy, set limits, approve queued spends, add/remove operator and co-signer, rotate owner, sign EIP-1271 (incl. `setAgentWallet` consent). | Full control of the agent's funds. Same blast radius as any self-custody wallet. | `rotateOwner(new)` signed by current owner. Optional recovery delegate is a later item (§9). |
| **Operator** (the agent) | secp256k1 | `integrity_sdk/wallet.py` V3 encrypted keystore at `wallet_dir(agent_id)/keystore.json`, 0600, password from `INTEGRITY_WALLET_PASSWORD`. Unchanged format; **role changes**: it is no longer the controller. | `execute` / `propose` only, always through the policy. Cannot change policy, roles or 1271. | Attacker can spend **up to the owner's configured limits** until the owner revokes it. Cannot raise limits, cannot drain past caps, cannot sign permits. | Owner calls `setOperator(new)`; SDK mints a new keystore. Address of the account does not change. |
| **Shield co-signer** (optional) | secp256k1 | Shield's device key store on the endpoint (separate from Shield's device identity key; TPM/OS keychain where available, 0600 file otherwise). | Countersigns an operator call when the owner selected "Shield must approve". Cannot initiate anything. | Alone: nothing (needs operator too). With a stolen operator key: spends within limits, same as "no co-signer". | Owner calls `setCoSigner(new)`. |
| **Guardian / deployer** | secp256k1 | Whoever sends the deploy + `AgentRegistry.register` tx. | **None after deploy.** The constructor takes `owner` as an argument; the deployer gets no role. | Nothing on the account. | n/a |
| **DID key** | Ed25519 | `did.py` PEM under the profile key home (unchanged). | Not a wallet. Signs BCC commitments, telemetry, and the off-chain registration attestation. | Agent impersonation off-chain; no funds. | Unchanged (out of scope). |

Two deliberate consequences:

1. The existing operator keystore is acceptable to keep hot on the agent host **only because** its
   power is now bounded on-chain. Without the role split (today's contract) it is not.
2. Guardian ≠ owner by construction. CLI registrations where no human wallet is present pass the
   CLI's own EVM keystore as `owner` and print a warning that the agent is self-owned (see §8, D2).

## 2. Intent and why

- One address per agent for every ITK interaction, so reputation (AIS), stake and payments accrue
  to the same identity the passport advertises.
- Spending authority is **configurable per agent in the console**: no one / spending limits /
  Shield must approve / owner must approve (combinable).
- A console setting is a promise the chain keeps. The product sells verifiable control evidence,
  so an advisory setting the agent can route around would be a failure even if it "works".

**Goals.** Single-address invariant; on-chain-enforced spend authority with the four modes; the agent
holds only a bounded key; owner configures from the console with their own wallet; agent0 passport
`agentWallet` actually set on the live registry.

**Non-goals (this design).** Off-chain signer/KMS custody (approach B) and hybrid soft rules (C) —
the signer interface leaves room for them. ERC-4337 bundlers/paymasters. Gas sponsorship. Mainnet.
Social recovery.

**Anti-goals.** Any path where a key on the agent host can raise its own limits or replace its
policy. Any second "agent wallet" address that diverges from `actor`. Console showing an owner's
personal wallet as the agent's.

## 3. Current state (verified 2026-11-18, `origin/main` c4a20aeb)

- `SovereignAgent.sol`: a single `DEFAULT_ADMIN_ROLE` "controller" gates `execute` (both overloads),
  `setExecutionPolicy`, `rotateController`, and EIP-1271 `isValidSignature` (`:298`). The operator
  key and the admin key are therefore the same key, and it can remove its own policy.
- `ConstraintExecutionPolicy.sol`: one admin, **global** (not per-agent) `maxValue`,
  `allowedTarget`, `tokenOutCap`, `minAis`. Caps are **per call**; `check` is `view` (SPEC §5.3).
  `_tokenAmount` decodes `transfer`, `approve`, `transferFrom`, `safeTransferFrom` only.
- `ITK.sol` / `IntegrityToken.sol`: `ERC20 + ERC20Burnable + AccessControl`, no permit/3009.
  `burn`/`burnFrom` are not decoded by the policy.
- `AgentRegistry.sol`: actor must match the pinned runtime codehash of the canonical
  `SovereignAgent` (`:58-61`); an actor is bound forever to the fingerprint that first bound it
  (`actorClaimedBy`). `StakeVault.stake` credits `msg.sender`.
- **Live agent0 registry** `0x8004A818…BD9e` (Base Sepolia, impl `0x7274e874…9c02`): has
  `setAgentWallet(uint256,address,uint256,bytes)` and `unsetAgentWallet(uint256)`. A
  `register(uri, [("agentWallet", …)])` call **reverts `reserved key`** (eth_call, 2026-11-18).
  Therefore `erc8004.py:286` (confined path) and `agent0.ts:176` (console field) cannot succeed
  against the live registry; on the default path `agentWallet` falls back to the minter, and the
  console displays `agentWallet || owner` (`agent0.ts:276`).
- SDK `wallet.py`: per-agent V3 keystore, password from env, documented as "the agent's own wallet
  signs the SovereignAgent deployment" — that wallet is today's controller.

## 4. Approaches considered

| | A. On-chain smart account (**chosen**) | B. Off-chain signer holds the key | C. Hybrid |
|---|---|---|---|
| Where rules are enforced | `SovereignAgent` + policy, on-chain | Shield on device or hosted KMS signer | Hard caps on-chain, soft rules off-chain |
| Agent holds | Bounded operator key | Nothing | Bounded operator key |
| Console change | Owner-signed tx (gas) | API write, instant | Both |
| Trust | Chain | Our signer | Chain for caps, signer for prompts |
| Cost now | Contract revision, registry redeploy | Signer service, no contract work | Both |

Owner chose **A** (2026-11-18): it is the only option where "configurable in console" is enforced
independent of where the agent runs, and most of the machinery (`execute` policy hook,
`ConstraintExecutionPolicy`) already exists. The SDK signer interface (§6.6) keeps C open.

## 5. Invariants

- **I1 — one address.** For any agent that can move ITK:
  `passport.agentWallet == AgentRegistry.records[fp].actor == SovereignAgent address`, and the
  stake/AIS key is that address. Checked by the Oracle on sync (§6.7) and by the SDK before any
  value-bearing call.
- **I2 — the address never changes.** Key rotation happens through roles inside the account. A new
  address would orphan stake, AIS history and `actorClaimedBy`.
- **I3 — no admin power on the agent host.** No key the SDK stores on the agent host holds the
  owner role (except an explicitly self-owned CLI agent, which is flagged everywhere it is shown).
- **I4 — no policy bypass.** Every way the account can move value or authorize a spend goes through
  the policy, or is owner-only.

## 6. Design

### 6.1 `SovereignAgent` v2 roles

- `OWNER_ROLE` (exactly one holder; replaces `DEFAULT_ADMIN_ROLE` as controller). Constructor:
  `(did, owner, operator, registry)`; the deployer receives nothing.
- `OPERATOR_ROLE` (one holder; the SDK keystore).
- `coSigner` (optional address, zero = none).

| Function | Who |
|---|---|
| `execute(...)` both overloads | operator **or** owner; always through policy + mode checks |
| `propose(target,value,data)` / `approve(id)` / `cancel(id)` | operator proposes; owner approves (executes) or cancels; proposals expire |
| `setExecutionPolicy`, `setOperator`, `setCoSigner`, `setMode`, `rotateOwner` | owner only |
| `isValidSignature` (EIP-1271) | **owner signatures only** (I4: an operator-valid 1271 would let a leaked operator key authorize off-policy approvals on any permit-style token or registry) |

`rotateController` is removed (replaced by `rotateOwner`/`setOperator`).

### 6.2 Spend authority modes (what the console configures)

Stored on the account, owner-set, combinable:

- **Limits** — per token: max per call, max per rolling window (window length owner-set, e.g. 24h);
  native value cap; target allowlist (on by default, I4).
- **Shield must approve** — `execute` additionally requires an EIP-712 signature from `coSigner`
  over `(account, target, value, keccak(data), nonce, deadline)`.
- **Owner must approve above X** — calls whose decoded token amount exceeds threshold X (or all
  calls, X = 0) revert on `execute`; the operator uses `propose`, the owner `approve`s from the
  console.
- **No one** — none of the above set; policy still applies its allowlist and AIS floor if configured.

### 6.3 Per-agent policy

Make constraint storage keyed by `agent` (`mapping(address agent => Constraints)`) with the agent's
owner (read from the account) as the only writer, so one deployed policy serves every agent and the
console writes one tx per change. (Builder may choose per-agent instances instead if it simplifies
auditing; I1–I4 must hold either way.)

Decoder additions: `burn(uint256)`, `burnFrom(address,uint256)`; unknown selectors on a
`tokenKnown` target are denied (fail closed) rather than passed.

### 6.4 Window limits without changing `check` to non-view

The rolling-window counter lives **in the account**, updated in `execute` after a successful
dispatch; the policy reads `spentInWindow(token)` from the account inside its `view` `check`.
This keeps the `IExecutionPolicy.check` signature unchanged. It is still a behavioural addition to
SPEC §5.3 (the host now carries metering state), so it is filed as a **proposed amendment**, not
authoritative until review + implementation evidence + tests + acceptance.

### 6.5 Registry and passport binding

- **`AgentRegistry` codehash pin.** v2 changes the runtime codehash, so v1-pinned registries reject
  v2 actors. Redeploy `AgentRegistry` with the v2 reference instance (testnet). Do not add a mutable
  pin (it would be a governance key that can swap every agent's account logic).
- **agent0 `agentWallet`.** Mint the passport **without** an `agentWallet` metadata entry (the live
  registry reverts on it). Then call `setAgentWallet(agentId, account, deadline, sig)` where `sig`
  is the owner's signature validated through the account's EIP-1271 (§6.1). Keep the
  `sovereignActor` / `integrityDid` metadata entries. Remove the `agentWallet` field from the
  console registration form; show the result instead.
- Passport **owner** (ERC-721 holder) = the human owner. The passport's owner and the account's
  owner should be the same key; the console sets both in one flow.

### 6.6 SDK

- New `integrity_sdk/account.py`: `AgentAccount` (resolve address from passport/registry; enforce I1;
  read mode/limits/spent; `execute`, `propose`; decode `PolicyDenied`/`CoSignerRequired`/
  `ApprovalRequired` into typed errors with the console URL to resolve them).
- `wallet.py` keeps the keystore; it is renamed in docs/API to "operator key". Add a `Signer`
  protocol (`address`, `sign_tx`, `sign_typed_data`) with `KeystoreSigner` as the only
  implementation now — the seam for approach C/B later (Shield-held or KMS signer).
- `registration_onchain.register_onchain(confined=True)` becomes the path for any ITK-capable agent:
  deploy v2 account with `owner` (required argument; CLI falls back to its keystore and flags
  self-owned), `operator` = operator keystore address; register; mint passport; `setAgentWallet`.
- `erc8004.py`: drop the `agentWallet` metadata entry; add `set_agent_wallet` using the owner signer.
- Readiness (`readiness.py`): add `account_invariant` check (I1) and `operator_is_not_owner` (I3).

### 6.7 Oracle

Extend `POST /v1/agent/{did}/erc8004` and `/onchain/sync` to read `getAgentWallet`/`actor` and
record `wallet_invariant: ok | mismatch | unset`. Expose it so the console and Shield can refuse to
show/transact on a mismatch.

### 6.8 Console

- Agent page shows the one account address, its ITK balance, stake, AIS, and mode; "agent wallet not
  set" instead of the owner fallback; a self-owned badge when owner == operator's host key.
- "Spending" settings panel: limits per token and window, allowlist, Shield-approve toggle,
  owner-approve threshold. Each save = one owner-signed tx from the browser wallet; panel shows the
  on-chain value read back, not the form value.
- Approvals inbox: pending proposals with approve/cancel.

### 6.9 Shield

Out of scope to implement here beyond: a co-signer key store and an endpoint that countersigns an
operator request after its local policy decision. Tracked as a follow-up in xibalba-shield.

## 7. Migration

Base Sepolia only. Existing v1 actors are **not** migrated in place (I2 forbids moving the address,
and v1 cannot gain roles). Decision: redeploy registry + v2 accounts and re-register; v1 stake is
unstaked and restaked to the new account; v1 AIS history is **not** carried over. Acceptable on
testnet; recorded explicitly so it is not repeated on mainnet.

## 8. Decisions for the owner (open)

- **D1 — ITK requires an account.** Under A, an agent on the default existence-only registration
  path has no account and therefore cannot hold, stake or pay ITK. This partly reverses
  "primitives too constricting". Options: (a) accept — existence-only agents are identity-only;
  (b) lazily deploy the account the first time an agent needs ITK (deterministic CREATE2 address
  so it can be advertised earlier).
- **D2 — self-owned CLI agents.** Allow agents whose owner is the CLI keystore on the same host
  (convenient, violates the spirit of I3), or require a human owner wallet for any ITK-capable agent.

## 9. Left to the builder

Exact storage layout, event names, proposal expiry default, window implementation (fixed bucket vs
rolling), CREATE2 salt scheme if D1(b), error names, test matrix (must include: operator cannot
call any owner function; leaked-operator spend stops at limits; 1271 rejects operator sigs; unknown
selector on known token denied; `burn` capped; I1 mismatch detected by Oracle; live-registry
`setAgentWallet` round-trip on Base Sepolia). Recovery delegate is a later item.
