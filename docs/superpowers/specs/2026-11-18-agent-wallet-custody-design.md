# Agent wallet and key custody — design

Status: **proposed (non-authoritative)**. Date: 2026-11-18. Revision 2 (supersedes the
`SovereignAgent` v2 patch design in revision 1, commit `4bed6847`).
Review provenance: the Devil's Advocate engine is not entitled (`ENGINE_NOT_IN_PLAN`). This design
was red-teamed with the advisor model and self-review, then put through a fresh-builder check. That
builder check covered revision 1; its questions that still apply are answered in §10. Any SPEC
change here (§7.5) is a *proposed amendment*, not authoritative, until it has been reviewed,
implemented, tested and accepted.

## 1. The question this answers

> "When an agent moves ITK, which wallet does it use, and how is the key saved?"

**Answer.** Every agent that can move Integrity tokens has exactly one on-chain address: a
**standard, audited ERC-4337 / ERC-7579 smart wallet**. Integrity does not build the wallet. It
ships **modules** that install into it. That one address is all of the following at once:

- the agent0 / ERC-8004 passport's `agentWallet` (the wallet mints its own passport, §6.4)
- the `AgentRegistry` record's `actor`
- the `StakeVault` / `AISRegistry` key
- the holder of the agent's ITK, and the address the console displays

Control is split between keys. The **owner** is a human wallet. The agent holds only a **session
key**, whose limits are set by a human and enforced on-chain.

### 1.1 Key table

| Key | Where it is saved | What it can do | If it leaks | Rotation |
|---|---|---|---|---|
| **Owner** (human) | The human's own wallet (browser or hardware), signing through the console. Never on the agent host. | Everything: install or remove modules, set limits, approve or override spends, rotate the session key, rotate the owner. Also holds the registry guardian role and the passport (§5, I3). | Full control: the same blast radius as any self-custody wallet. | The owner rotates itself through the wallet's owner-management call, and the registry guardian moves in the same flow (§6.5). |
| **Session key** (the agent) | `integrity_sdk/wallet.py` V3 encrypted keystore, `wallet_dir(agent_id)/keystore.json`, mode 0600, password in `INTEGRITY_WALLET_PASSWORD`. Format unchanged; the **role** changes. | Submit UserOperations that pass the session-key module's permissions **and** the Integrity hook. Cannot install or remove modules, change limits, or sign EIP-1271. | Spends up to the human-set limits until the owner revokes it. | The owner revokes and enables a new session key; the SDK creates a new keystore. **The address does not change.** |
| **Host owner key** (only for a self-run agent, §6.7) | A second keystore on the host, separate file, separate password, never the session key. | Can only **tighten** the limits a human fixed at creation, revoke or rotate the session key, and register the agent. Cannot raise any limit or remove the Integrity hook. | The attacker can only lower limits or freeze the agent (a DoS), never spend more. | A human claims the agent (§6.7), which replaces it. |
| **Shield co-signer** (optional) | Shield's device key store, separate from Shield's identity key. | Countersigns a session-key operation when the owner turned on "Shield must approve". Cannot start one. | On its own: nothing. | The owner changes the co-signer address. |
| **DID key** | `did.py` PEM file (unchanged). | Not a wallet. Signs BCC commitments, telemetry, and the registration attestation. | Off-chain impersonation; no access to funds. | Unchanged. |

## 2. Intent and why

- One address per agent for every ITK interaction, so AIS, stake and payments build up on the same
  identity the passport advertises.
- Spend authority is **configurable per agent in the console**: limits / Shield must approve /
  owner must approve, in any combination. A console setting is a promise the chain keeps.
- **Integrity ships rules, not wallets.** Any ERC-7579 wallet that installs the Integrity modules
  is an Integrity agent. This widens adoption and leaves wallet security to audited code.

**Goals.** The single-address invariant. On-chain enforcement of the console settings. The agent
holds only a bounded session key. The live agent0 `agentWallet` is set correctly. The archived
kernel's problems are fixed (§3.2).

**Non-goals.** Writing our own account or session-key validator. Mainnet. Social recovery. An
off-chain signing service (approach B), which stays possible through the SDK `Signer` seam.
Shield-side co-signer implementation (§8).

**Anti-goals.**
- Any key on the agent host can raise its own limits or remove the hook.
- A second "agent wallet" address that drifts away from `actor`.
- The console shows an owner's personal wallet as if it were the agent's.
- Enforcement code that ships without a live, scheduled check (the archived kernel sat dormant
  for 84 days).

## 3. Current state and history (verified 2026-11-18, `origin/main` c4a20aeb)

### 3.1 Today

- **`SovereignAgent` is a bespoke account.** `IAccount.sol` says it is "deliberately NOT an ERC-4337"
  account. One `DEFAULT_ADMIN_ROLE` controller gates `execute`, `setExecutionPolicy`,
  `rotateController` and EIP-1271, so the agent's key can remove its own policy.
- **`ConstraintExecutionPolicy`** stores its rules globally rather than per agent, caps each call
  only, has a `view` `check`, and does not decode `burn`/`burnFrom`.
- **`AgentRegistry`**:
  - It pins the actor's runtime codehash to the `SovereignAgent` build (`:62`, `:116`, `:310`).
  - Its guardian keeps `setActor`, `clearActor`, `setDomain`, `proposeGuardian` and `retire`.
  - `register_onchain` passes the agent's own keystore as the guardian.
- **`StakeVault.lockForAction(agent, req)`** requires `msg.sender == agent` (`:213`). `stake`
  credits `msg.sender`.
- **The live agent0 registry** `0x8004A818…BD9e` is `IdentityRegistryUpgradeable`, impl
  `0x7274e874…9c02`, with verified source (read 2026-11-18). It behaves like this:
  - **Reserved key.** `register(uri, [("agentWallet", …)])` reverts `reserved key`, so the
    `erc8004.py:286` and `agent0.ts:176` paths cannot succeed.
  - **Default wallet.** On register, `agentWallet = msg.sender`.
  - **Changing it.** `setAgentWallet(agentId, newWallet, deadline, sig)` checks `sig` through ECDSA
    or **EIP-1271** (`IERC1271.isValidSignature`), and `deadline` may be at most 5 minutes ahead.
  - **Transfer.** Transferring the NFT clears `agentWallet`.
- **EntryPoint v0.7** `0x0000000071727De22E5E9d8BAf0edAc6f37da032` and **v0.8**
  `0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108` both have code on Base Sepolia (read 2026-11-18).

### 3.2 The archived kernel, and why this differs

Phase I (tag `kernel-phase1-archive`, `docs/archive/2026-11/kernel-phase1/README.md`) had two parts:
- **`IntegrityAccount`**: our own 983-line wallet on OpenZeppelin's draft account library, with
  `installModule`/`uninstallModule` disabled.
- **`IntegrityKernel`**: an ERC-7579 hook bound to one account, with constructor-fixed budgets,
  ETH plus one token, and no calldata decoding.

It was archived 2026-11-16 for four reasons. This design answers each one:

| Archive reason | Answer here |
|---|---|
| Disconnected from registration v3 (it read `ReputationRegistry`) | The hook reads `AISRegistry` and binds through `AgentRegistry` from day one. |
| No product consumer | Console-configured ITK spending is the consumer. |
| Deployed reference went dormant (stale snapshot, every `execute` reverted) | The floor reads the AIS checkpoint with a defined staleness rule (§6.2). A scheduled live canary on Base Sepolia runs one operation daily and alerts on failure (§9). |
| Halmos proofs not run continuously | The proofs are ported to the new hook and run in CI (§9). |

## 4. Approaches considered

| | **1. Standard wallet + Integrity modules (chosen)** | 2. Patch `SovereignAgent` (rev. 1) | 3. Any address, off-chain enforcement |
|---|---|---|---|
| Wallet code we own | None | All of it | None |
| Enforcement | On-chain hook + session-key permissions | On-chain policy | Shield / signer service |
| Registry binding | "Integrity hook installed" | Codehash pin | Anything |
| Pre-deployment address | Yes (counterfactual) | No | Yes |
| Gas sponsorship | Paymaster available | No | n/a |

The owner chose **1** on 2026-11-18. Approach 2 keeps a bespoke wallet, the codehash pin, and
deploy-before-ITK. Approach 3 gives up chain enforcement of console settings.

## 5. Invariants

- **I1. One address.** For any ITK-capable agent:
  `passport.agentWallet == AgentRegistry.actor(fp) == the smart wallet == StakeVault/AISRegistry key`.
  The Oracle checks this on sync, and the SDK checks it before any value-bearing call.
- **I2. The address never changes.** Keys rotate inside the wallet. A new address would orphan
  stake, AIS and `actorClaimedBy`.
- **I3. One human owner.**
  - The same human key is the wallet owner, the `AgentRegistry` guardian, and the passport's NFT
    holder through the wallet (§6.4).
  - The SDK and Oracle refuse any registration where these differ. Exception: a self-run agent
    (§6.7), whose host owner key is limited by I5.
- **I4. No bypass.** Every way the wallet can move value or authorize a spend passes through the
  Integrity hook, or is owner-only:
  - EIP-1271 is validated by the owner validator only.
  - Session keys cannot sign 1271.
  - Removing the hook is owner-only.
- **I5. Agent-host keys can only tighten.** No key stored on the agent host can raise a limit,
  lower the AIS floor, or remove the hook.
- **I6. Protocol AIS floor.** Governance sets a network-wide minimum AIS for spending. Owners may
  set a higher per-agent floor, never a lower one.

## 6. Design

### 6.1 The wallet (we pick it, we do not write it)

**Selection criteria:**
- an ERC-7579 account with open module install
- an audited ERC-7579 session-key validator with per-key permission policies (target, selector,
  value, usage or spend limits)
- live deployments on Base Sepolia (`eth_getCode` verified before use)
- counterfactual address through a factory
- EIP-1271 through the owner validator only

**My pick, to confirm in plan step 1:**
- **Safe + the Safe7579 adapter + Rhinestone Smart Sessions.** Safe is the most audited account.
- Fallback: Biconomy Nexus or ZeroDev Kernel v3 with the same Smart Sessions.

The plan's first task is a **spike** that deploys one on Base Sepolia, installs a stub hook, and
sends one session-key UserOperation through EntryPoint v0.7. The pick is final only after that
spike passes.

### 6.2 `IntegrityHook` (ERC-7579 hook, ours)

**One deployment for all agents.** Configuration is keyed by `account`
(`mapping(address account => Config)`), and is installed with `onInstall(initConfig)`.

**`preCheck`** runs on every execution. It enforces, in order:
1. **Not frozen.** `StakeVault.stakeOf(account).frozen == false`.
2. **Registered.** `AgentRegistry.agentOf(account) != 0` and the record is not retired.
3. **AIS floor.**
   - `AISRegistry.latest(account).score >= max(protocolFloor, account.ownerFloor)`.
   - A checkpoint older than `maxCheckpointAge` (governance-set) is denied with `AisStale`.
   - The console shows a fix (request a checkpoint). The rule is documented so it cannot fail
     silently the way the kernel did.
4. **Target allowlist.** Default on, owner-set.
5. **Token amount.** It decodes `transfer`, `transferFrom`, `approve`, `safeTransferFrom`, `burn`
   and `burnFrom`. An unknown selector on a known token is denied (fail closed).
6. **Limits.** Per-call cap and rolling-window cap per token, plus a native value cap.
7. **Mode gates.**
   - Shield co-signature (EIP-712 over account, target, value, `keccak(data)`, nonce and deadline,
     carried in the UserOperation signature extension).
   - Owner-approve threshold: anything above X needs owner validation.

**`postCheck`** updates the window counter from the **measured balance delta** (the kernel's
method, so non-decoded movement still counts) and calls the stake lock (§6.6).

**Config writers.**
- **The owner**, through the wallet: limits, allowlist, modes, and an owner floor at or above the
  protocol floor.
- **Governance role**: `protocolFloor` and `maxCheckpointAge`.
- **The host owner key** (§6.7): tighten only. The hook rejects any write that loosens a value
  fixed at creation.

**Owner override.** An operation validated by the owner validator skips the limits and mode gates
but still passes checks 1–3, because frozen, retired and below-floor apply to everyone. It counts
toward the window.

### 6.3 Session-key permissions

The agent's session key is enabled through the session-key validator with these policies:
- only targets on the Integrity allowlist
- spend and usage limits that mirror the hook's caps
- an expiry

This is defence in depth. The hook is the authority. The session-key policies make a leaked key
useless outside Integrity targets even if the hook were misconfigured.

### 6.4 agent0 passport: the wallet mints it

- The smart wallet calls `register(uri, [("integrityDid", …), ("sovereignActor", …)])` itself.
- Because `agentWallet` defaults to `msg.sender`, the passport's wallet is the smart wallet, with
  no 5-minute signature dance.
- The NFT is held by the wallet, so the human controls it through the owner key (I3).
- **No `agentWallet` metadata entry.** Remove that path from `erc8004.py` and the field from the
  console form.
- An NFT transfer clears `agentWallet` (live registry behaviour). The console therefore treats
  "move passport" as a two-step re-point, and the Oracle flags `unset`.
- Existing passports minted by CLI keys: re-mint from the wallet as part of migration (§7).

### 6.5 `AgentRegistry` v3 (redeploy)

- **Replace the codehash pin with a module check.** The actor must be a contract with
  `isModuleInstalled(MODULE_TYPE_HOOK, IntegrityHook, "")` true, and the hook must hold a config
  for it. Consent: `msg.sender == actor` (a UserOperation from the wallet) or EIP-1271 from the
  owner.
- **Guardian is the wallet owner** (I3). Guardian powers (`setActor`, `clearActor`, `setDomain`,
  `retire`) stay, but registration requires `guardian == owner of actor`, read from the owner
  validator. `rotateOwner` in the console moves both, in one flow.
- **Hook removal is detected.** If the owner uninstalls the hook, `preCheck` no longer runs. The
  registry exposes `isGoverned(actor)` (hook installed), and the Oracle marks the agent
  `ungoverned`. AIS and stake consumers must treat ungoverned agents as non-transacting. Removal
  stays possible so owners are never trapped, but it is visible.

### 6.6 StakeVault

`lockForAction` requires `msg.sender == agent`, but a hook calls as itself. Add `LOCKER_ROLE`,
granted to `IntegrityHook`, with `lockForAction(agent, req)` allowed when
`hasRole(LOCKER_ROLE, msg.sender)` and the hook reports `agent` as installed. `stake` stays
`msg.sender`-credited; the wallet stakes through a normal UserOperation.

### 6.7 Self-run agents (no human wallet at runtime)

Owner decision 2026-11-18: allowed **if a human sets the limits in advance**.

- **At creation** a human enters the limits in the CLI and confirms them interactively, for example
  via `integrity register --onchain --limits <file>` with an explicit confirmation prompt. They
  become the **ceiling**, stored in the hook as `creationCeiling`.
- **The host owner key** (separate keystore from the session key) is the wallet owner. The hook
  enforces I5: it can lower limits, revoke or rotate the session key and retire the agent, but
  writes above the ceiling and hook removal are refused.
  - The wallet's owner validator alone cannot stop the owner uninstalling the hook. The plan
    must pick one mechanism:
    - (a) the hook marks a self-run account as `locked`, and `AgentRegistry` plus the Oracle treat
      it as ungoverned the moment the hook is removed (§6.5); or
    - (b) a wallet whose uninstall is guardable by a hook.
  - (a) is my default.
- **Claiming.** A human later claims the agent from the console. The host owner key signs a
  rotation to the human wallet, after which normal owner rules apply.
- Console and Oracle label these agents **self-run** with the creation ceiling shown.

### 6.8 SDK

- `integrity_sdk/account.py`, an `AgentAccount` that:
  - computes the counterfactual address
  - resolves I1
  - builds, signs and sends UserOperations to a bundler URL (config)
  - reads config, window and floors
  - maps hook reverts (`LimitExceeded`, `AisBelowFloor`, `AisStale`, `CoSignerRequired`,
    `OwnerApprovalRequired`, `Frozen`) to typed errors carrying the console URL that resolves them
- `wallet.py`: unchanged storage; documented as the **session key**. Add a `Signer` protocol with
  `KeystoreSigner` as its only implementation now. It is the seam for a Shield- or KMS-held signer
  later.
- `registration_onchain.register_onchain` supports two paths:
  - **human-owned**: produce the DID attestation and session-key address, then hand off to the
    console (§6.9)
  - **self-run**: §6.7
- `erc8004.py`:
  - drop the `agentWallet` metadata entry
  - mint through the wallet
  - add `set_agent_wallet` for re-pointing (owner EIP-1271, deadline ≤ 5 min)
- `readiness.py`: add `wallet_invariant` (I1), `session_key_not_owner` (I3/I5) and `hook_installed`.
- Retire `SovereignAgent` paths and the `confined` flag (replaced by "ITK-capable").

### 6.9 Console (integrity-console, in this plan)

- **Registration handoff.**
  - The agent host runs `integrity register --onchain`. That registers off-chain, gets the Oracle
    attestation, and writes a **pending on-chain registration** to the Oracle. The pending record
    holds the DID, the session-key address and the attestation, never any secret.
  - The console shows "finish setup". The human's wallet then, in one batched flow:
    - deploys the wallet
    - installs the hook and the session key with limits
    - registers in `AgentRegistry`
    - mints the passport
- **Agent page.** Shows:
  - the single address, ITK balance, stake and AIS
  - mode and limits, **read back from chain**
  - "not governed" or "wallet not set" states (never the owner fallback)
  - a self-run badge
- **Spending panel.** Limits per token and window, allowlist, Shield-approve toggle, owner-approve
  threshold, owner AIS floor (at or above the protocol floor). Each save is one owner-signed
  operation.
- **Approvals.** Above-threshold operations are prepared by the agent and stored in the Oracle as
  unsigned UserOperations. The owner signs them in the console, which is the override in §6.2.
  There is no on-chain queue.

### 6.10 Oracle

- Pending-registration store (above).
- `/onchain/sync` and `/erc8004` record:
  - `wallet_invariant: ok | mismatch | unset`
  - `governed: bool`
  - `ownership: human | self-run`
- `controller` in API responses is replaced by `owner`, `session_key` and `wallet`.
  `IntegrityIdentityReadV1.isController` reports the owner.

## 7. Migration and live rollout (Base Sepolia; the plan runs it)

Owner decision: **the plan performs the rollout**, not just scripts. Render autoDeploy is on, so
merging Oracle changes deploys them. The ordering guards against a half-cutover:

1. Deploy `IntegrityHook`, `AgentRegistry` v3 and the `StakeVault` upgrade or redeploy. Re-grant
   `DomainRegistry` `REGISTRAR_ROLE`, the attester role and the hook's `LOCKER_ROLE`, verifying
   each with `eth_getCode` and `hasRole` before writing `deployments.baseSepolia.json`.
2. Ship the Oracle change, which **reads both registries** (v3 is authoritative, v1 is read-only
   legacy), and merge it. Verify `/healthz` and a v1 agent still resolving.
3. Re-register the system agents (Claude, Codex, agy, Hermes) on v3:
   - human-owned by the owner's wallet: one console "finish setup" each, owner present
   - their v1 records are retired by their v1 guardians
4. v1 stake (if any) is unstaked and restaked from the new wallet. **v1 AIS history is not
   carried over** (testnet, recorded so it is not repeated on mainnet).
5. Remove v1 reads from the Oracle in a follow-up PR once every live agent resolves on v3.

Each step has a readback check and a stop condition. The step-3 signatures need the owner present.

## 8. Out of scope (follow-ups)

- Shield co-signer key store and countersign endpoint (xibalba-shield). "Shield must approve"
  ships in the hook and console but cannot be end-to-end tested until that lands; the plan tests
  it with a test co-signer key.
- Paymaster sponsorship (designed for, not built).
- Mainnet, social recovery, ERC-6492 pre-deploy signatures.

## 9. Verification the plan must include

- **Halmos proofs** of the archived kernel ported to `IntegrityHook` and run in CI:
  - budget containment per call and across calls
  - token plus native conjunction
  - AIS gating
  - reentrancy
- **Forge tests:**
  - a session key cannot call any owner function or install or uninstall modules
  - a leaked session key's spending stops at the limits
  - 1271 rejects session-key signatures
  - an unknown selector on a known token is denied
  - `burn` is capped
  - the host owner key cannot exceed the ceiling
  - the owner override skips limits but not freeze or floor
  - a stale AIS checkpoint is denied with `AisStale`
  - hook removal makes the agent ungoverned
- **Fork tests** against Base Sepolia: the chosen wallet stack, EntryPoint v0.7, and the live agent0
  registry (`register` from the wallet sets `agentWallet == wallet`).
- **Live canary:** a scheduled daily UserOperation from a canary agent on Base Sepolia, which
  alerts on failure, so enforcement cannot go dormant unnoticed.

## 10. Decisions record

| # | Decision | Source |
|---|---|---|
| D-A | Standard ERC-4337/7579 wallet + Integrity modules (approach 1) | Owner, 2026-11-18 |
| D-B | One human key = wallet owner = registry guardian = passport holder | Owner, 2026-11-18 |
| D-C | Protocol AIS floor; owners may only raise | Owner, 2026-11-18 |
| D-D | Plan runs the Base Sepolia rollout | Owner, 2026-11-18 |
| D-E | Self-run agents allowed if a human sets the limits in advance (creation ceiling, tighten-only host key) | Owner, 2026-11-18; the mechanism in §6.7 is the designer's interpretation |
| D-F | Owner-signed operations override limits but not freeze/registration/floor | Designer's call |
| D-G | Approvals are owner-signed UserOperations, not an on-chain queue | Designer's call |
| D-H | Console registration handoff through the Oracle pending record; console work is in this plan | Designer's call |
| D-I | Wallet stack: Safe + Safe7579 + Smart Sessions, confirmed by spike | Designer's call |
| D-J | Shield co-signer implementation deferred | Designer's call |

## 11. Left to the builder

- storage layout, event and error names, and the window algorithm (fixed buckets or rolling)
- the governance role holder for `protocolFloor`
- the exact UserOperation signature encoding for the co-signer
- bundler choice for tests
- the shape of the Oracle pending-record API
- whether `StakeVault` is upgraded or redeployed (driven by whether it holds live stake)
