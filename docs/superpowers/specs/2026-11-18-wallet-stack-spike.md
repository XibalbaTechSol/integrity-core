# Wallet-stack spike: decision record

Status: **spike result for owner review (Plan 1 Task 1). Plan 1b does not start until the owner has seen this.**
Date: 2026-11-18. Serves: `2026-11-18-agent-wallet-custody-design.md` §5 and §6.1–§6.4.

**Evidence.** The evidence is `contracts/test/spike/WalletStackSpike.t.sol`, which is throwaway, plus its
local interface and stub files in the same folder. Nothing was vendored. Every component used is
the live Base Sepolia deployment, exercised inside a fork. To reproduce:

```bash
cd contracts
forge test --match-path test/spike/WalletStackSpike.t.sol \
  --fork-url https://sepolia.base.org --fork-block-number 60684000 -vv
# => Suite result: ok. 18 passed; 0 failed; 0 skipped
```

- The fork uses the public read-only endpoint, pinned at block **60684000**.
- Nothing is broadcast. The keys come from `makeAddrAndKey` and are test-only.
- Without a Base Sepolia fork, every spike test calls `vm.skip`. Plain `forge test` (CI) gives
  `385 tests passed, 0 failed, 17 skipped (402 total tests)`, the same 385 as the pre-spike
  baseline. (17 tests existed when the baseline ran; 18 exist now.)

## Summary

**Pick: Safe v1.4.1 + Rhinestone Safe7579 adapter v1.0.0 + Smart Sessions (`0x…8bDABA`).**

The hook is installed as Safe7579 **SIG hooks** on the four execution selectors, not as the
global hook (see Q2 finding F2). Two extra pieces are needed:

1. **An `IntegrityGuard`**, a Safe Guard. It can be the same contract as `IntegrityHook`.
2. **A verifier rule**: the only enabled Safe module is Safe7579.

The role source is **path-based** and needs no extra contract (Q3). All seven questions are
answered on this stack. Nexus and Kernel were evaluated from source only. The brief's trigger for
running them (Q2 or Q3 needing more than one extra contract) was not met, and the source reading
shows neither removes the hard part (Q3), as explained under "Alternatives" below.

**Security finding for the owner (F4, Q4).** The deployed Smart Sessions ERC-1271 path does not
bind the `hash` argument:
- A session that may sign *any* ERC-7739 content validates *any* digest.
- This is observed on the live contract, and upstream `main` has the same code.
- Session-key 1271 must stay disabled (I4). The system must refuse to enable any session with
  non-empty `erc7739Policies`.

---

## 1. Chosen stack

**Stack:** Safe v1.4.1 + Safe7579 v1.0.0 + Smart Sessions. Every component is **already deployed
on Base Sepolia**, and none is deployed from source in the fork.

`test_Q1_componentsHaveCode_andAccountDeploys` logs the `eth_getCode` byte length of each
component at block 60684000. The table also includes `cast code` reads at head
(block ~60684483).

| Component | Address | Code bytes | Source / verification |
|---|---|---|---|
| EntryPoint v0.7 | `0x0000000071727De22E5E9d8BAf0edAc6f37da032` | 16035 | spec §3.1 |
| Safe singleton v1.4.1 | `0x41675C099F32341bf84BFc5382aF534df5C7461a` | 23579 | `VERSION()` = "1.4.1"; permissionless 0.5.2 default |
| SafeProxyFactory v1.4.1 (**factory**) | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` | 3054 | permissionless 0.5.2 default |
| Safe singleton v1.5.0 | `0xFf51A5898e281Db6DfC7855790607438dF2ca44b` | 21451 | `VERSION()` = "1.5.0" (has a module guard; not exercised) |
| SafeProxyFactory v1.5.0 | `0x14F2982D601c9458F93bd70B218933A6f8165e7b` | 3321 | permissionless 0.5.2 |
| Safe7579 adapter v1.0.0 | `0x7579EE8307284F293B1927136486880611F20002` | 20014 | Sourcify exact_match `src/Safe7579.sol:Safe7579` (solc 0.8.26, paris) |
| Safe7579Launchpad v1.0.0 | `0x7579011aB74c46090561ea277Ba79D510c6C00ff` | 11335 | Sourcify; permissionless `erc7579LaunchpadAddress` |
| **Smart Sessions** (session validator) | `0x00000000008bDABA73cD9815d79069c247Eb4bDA` | 23608 | module-sdk 0.4.0 `SMART_SESSIONS_ADDRESS`; Sourcify match (0.8.28, cancun) |
| Smart Sessions compatibility fallback | `0x000000000052e9685932845660777DF43C2dC496` | 2439 | module-sdk 0.4.0 |
| **OwnableValidator** (owner validator / session signer) | `0x000000000013fdB5234E4E3162a810F54d9f7E98` | 12702 | module-sdk 0.4.0 top-level `OWNABLE_VALIDATOR_ADDRESS`; Sourcify exact_match |
| SudoPolicy | `0x0000003111cD8e92337C100F22B7A9dbf8DEE301` | 1148 | module-sdk 0.4.0 `module/smart-sessions/policies/sudo-policy` |
| Rhinestone module registry (ERC-7484) | `0x000000000069E2a187AEFFb852bF3cCdC95151B2` | 18522 | module-sdk 0.4.0 (not used: registry set to `address(0)`) |
| agent0 identity registry (proxy) | `0x8004A818BFB912233c491871b3d84c89A494BD9e` | 130 | impl `0x7274e874ca62410a93bd8bf61c69d8045e399c02` (Sourcify exact_match) |

**Address hygiene.**
- **Two Smart Sessions deployments are verified:** `0x…8bDABA` and `0x00000000002B0eCfbD0496EE71e01257dA0E37DE`
  (23940 bytes). Diffing the Sourcify sources shows they differ only in registry use (`2B0e` checks
  the ERC-7484 registry) and in `8bDABA` adding `Session.permitERC4337Paymaster`. The pick is
  `8bDABA`, the one module-sdk 0.4.0 names.
- **module-sdk 0.4.0 gives two policy and validator sets.** The top-level `constants.js` and the
  per-module `constants.js` files disagree. For example, OwnableValidator is `0x…13fdB5` at top
  level but `0x2483DA3A338895199E5e538530213157e931Bf06` per module, and SudoPolicy is
  `0x0000000000FEEc8D…` at top level but `0x0000003111cD…` per module. All of them have code.
  - The spike uses the top-level OwnableValidator, because it implements `ISessionValidator`.
  - It uses the per-module SudoPolicy.
  - Plan 1b must pin one coherent set and record it.
- **Two zero-code hits are wrong addresses, not missing deployments:**
  - `0x00000000BA4e9e8c71A7F4c8e2BC7B29F0Ca1f18` (my guess at a Nexus 1.2.0 factory).
  - `0x000000000032375a7cf3A3A0dA7bc1E8c16BF0f9` (my guess at UniActionPolicy; the module-sdk
    addresses are `0x0000006DDA6c…` and `0x0000000000714C…`, both with code).

**Account deployment used by the spike.**
- `SafeProxyFactory.createProxyWithNonce(singleton141, setup(...), salt)`.
- `setup` sets the fallback handler to Safe7579, then delegatecalls a small helper
  (`SpikeSafe7579Setup`). The helper calls `enableModule(Safe7579)` and then
  `Safe7579.initializeAccount(...)` on the Safe itself.
- This stands in for the Rhinestone **Safe7579Launchpad**, which does the same during the first
  UserOperation.
- **Production should use the Launchpad**, because it is audited and counterfactual through
  `initCode`. Not demonstrated in this spike: the Launchpad's first-op flow.

Modules installed:
- Validators: OwnableValidator(owner, threshold 1), and Smart Sessions (with the agent session
  enabled in `onInstall`).
- Hook: the stub, as SIG hooks.
- Registry: `address(0)`. An attested registry would reject our unattested hook.

## 2. Execution paths: the hook does not see every one. An `IntegrityGuard` is needed.

| Path | 7579 hook sees it? | Safe 1.4.1 Guard sees it? | Test |
|---|---|---|---|
| Session-key UserOp → `execute` | **yes**, `msgSender == EntryPoint`, selector `0xe9ae5c53` | no | `test_Q2_sessionKeyUserOp_runsThroughHook`: logs `hook.msgSender 0x0000000071727De22E5E9d8BAf0edAc6f37da032`, `0xe9ae5c53`; guard count unchanged |
| Owner `execTransaction(to = target)` | **no** | **yes** | `test_Q2_ownerExecTransaction_skipsHook_guardSeesIt`: `hook count unchanged 0`, `guard count 1` |
| Another Safe-native module (`execTransactionFromModule`) | **no** | **no** (1.4.1 has no module guard) | `test_Q2_otherSafeModule_skipsHookAndGuard_on141`: pings executed, both counts unchanged; `verify after extra module: Safe modules != [Safe7579]` |
| Owner `execTransaction(to = self, execute(...))` | **yes**, `msgSender == account` | yes | `test_Q2_ownerSelfExecute_hookSeesAccountAsSender`: `owner self-execute hook.msgSender 0x17aE…66cC` (the Safe) |
| Owner-signed UserOp (OwnableValidator or validator-0 fallback to Safe `checkSignatures`) | **yes**, `msgSender == EntryPoint` | no | `test_Q3_ownerUserOp_lookslikeSessionOp_atHook` |
| 7579 `executeFromExecutor` | yes (SIG hook on `0xd691c964`) | no | from source; the account has no executors, and `verify()` requires none |
| 7579 delegatecall through `execute` | yes (hook sees it) | no | from source. Smart Sessions rejects `CALLTYPE_DELEGATECALL` (`UnsupportedCallType`). The hook must class it as owner-only. Not demonstrated |
| `uninstallModule(hook)` | **no**: Safe7579 uses `tryWithHook`, which skips the hook being removed | via execTransaction only | from source. A session cannot reach it: `test_Q4_sessionCannotUninstallHookOrInstallModule` logs `NoPoliciesSet` (`0x1c792c05`) ×3 |

**Answer.**
- **An `IntegrityGuard` is needed.** It is a Safe Guard that runs the same owner-path checks
  (freeze, registered, floor, window) on `execTransaction`. It can be the same deployed contract
  as `IntegrityHook`, implementing both interfaces.
- **The Safe-native module path is closed only by state, not by a check:**
  - `verify()` requires the module list to be exactly `[Safe7579]`.
  - The guard should treat an `enableModule` call to self as "ungoverned" (§6.5).
  - A Safe 1.5.0 base adds `setModuleGuard`. It is deployed on Base Sepolia but **not
    demonstrated** with Safe7579 v1.0.0.

**F2. The hook must be a SIG hook, not the global hook.**
- Safe7579 runs the global hook on **every** fallback-routed call, through
  `execTransactionFromModuleReturnData`, which is state-changing and emits events.
- Any fallback view reached by STATICCALL therefore reverts. That includes `eip712Domain()`, which
  every ERC-7739 signer and Smart Sessions read during EIP-1271.
- `test_Q4_globalHook_breaksStaticFallback_sigHooksDoNot` logs
  `static eip712Domain ok? SIG-hook: true GLOBAL-hook: false`.
- So `IntegrityHook` is installed as SIG hooks on these four selectors:
  - `execute` `0xe9ae5c53`
  - `executeFromExecutor` `0xd691c964`
  - `installModule` `0x9517e29f`
  - `uninstallModule` `0xa71763a8`
- **Design note:** uninstalling one SIG entry calls `hook.onUninstall`. `IntegrityHook` must not
  wipe an account's config while other selector entries remain.

## 3. Role source: path-based. `IOperationContext.roleOf(account)`

A 7579 hook is not told which validator approved an operation.
`test_Q3_ownerUserOp_lookslikeSessionOp_atHook` shows that an owner-signed UserOp and a
session-key UserOp look **identical** at the hook:
- The log shows `session op msgSender 0x…da032` and `owner   op msgSender 0x…da032`.
- `msgData` hashes are equal.

So a role cannot come from the hook arguments alone on the 4337 path. The rule that works on this
stack, with no extra contract and no state carried across operations, is:

| Where the check runs | Condition | `roleOf` |
|---|---|---|
| `IntegrityGuard.checkTransaction` | Safe `execTransaction` (owner signatures checked by Safe) | **Owner** |
| `IntegrityHook.preCheck` | `msgSender == account` (owner `execTransaction` → self → `execute`) | **Owner** |
| `IntegrityHook.preCheck` | `msgSender == EntryPoint` | **Session** (non-owner). Fail closed: owner-signed UserOps land here too and get session limits. The owner's override path is `execTransaction`, which the console uses. |
| `IntegrityHook.preCheck` | anything else (executor) | deny (no executors are allowed) |

**Why `msgSender == account` cannot be forged by a session key.**
- A session op whose target is the account's own `execute` would make the inner preCheck report
  `msgSender == account`.
- Smart Sessions refuses this itself, even when the owner grants that action:
  `test_Q3_sessionSelfExecute_refusedBySmartSessions` calls the live validator, which reverts
  `InvalidSelfCall()` (`0x540733ea`), and `handleOps` rejects the op (AA23).
- Defence in depth: `IntegrityHook` must still classify `target == account` from a non-owner as
  admin and deny it.

**Maintenance.**
- On this stack the hook cannot tell a maintenance session from an agent session; both arrive from
  EntryPoint.
- Recommendation: make Maintenance a second Smart Session whose action policies allow only:
  - the hook's tighten-only setters
  - `removeSession`, through Smart Sessions' `FALLBACK_ACTIONID_SMARTSESSION_CALL`. That route
    needs a selector-restricting policy, or it would also allow `enableSessions`. **Not
    demonstrated.**
- The hook treats every non-owner config write as tighten-only, so I5 holds without knowing which
  session signed.
- Effect: the Safe adapter's `roleOf` returns only `{None, Owner, Session}`, never `Maintenance`.
  **Plan 1b interface impact:** keep `Maintenance` in the enum for other stacks, or drop it. This is
  an owner decision.

**`coSignatureOf(account)`.** This needs a channel from validation to execution, which the
path-based rule does not have. **Not demonstrated** (co-signer deferred, D-J). Two candidates for
later:
- **Stateless.** Carry the co-signature inside the executed batch, as an extra call to the hook
  that `preCheck` verifies from `msgData`.
- **Transient marker.** A Smart Sessions UserOp policy records it in transient storage, keyed by
  `(account, keccak(callData))`. This needs tests for mixed bundles (owner and session ops in both
  orders) and for a reverting op. Bundler ERC-7562 compliance cannot be shown on a fork.

**Considered and not chosen:** a transient role marker written during validation. Owner UserOps
through the validator-0 fallback write no marker, so the marker could only separate Session from
Maintenance, which the hook does not need.

## 4. Session-key EIP-1271: refused by configuration (proved)

**Configuration that refuses 1271.** Enable the agent session with
`erc7739Policies = ERC7739Data({ allowedERC7739Content: [], erc1271Policies: [] })`.
- Smart Sessions then returns `false` before any signature check: the content is not enabled, and
  `minPoliciesToEnforce = 1` with no policies.
- Removing or adding validators stays owner-only.

`test_Q4_productionSession_refuses1271_everyRoute` covers every Safe7579 1271 route:
- **Smart Sessions route, before the compatibility fallback is installed:** reverts, because the
  Safe has no `eip712Domain()`.
- **Smart Sessions route, with the compatibility fallback installed:** returns `0xffffffff`
  (logged `route SmartSessions (prod config): 0xffffffff`).
- **Validator `address(0)` → Safe `checkSignatures`, signed by the session key:** reverts `GS026`.
  **Control:** the owner's signature over the same SafeMessage digest returns `0x1626ba7e`.
- **Empty data → Safe `signedMessages`:** reverts `Hash not approved`.

**Positive control.** `test_Q4_positiveControl_permissiveSessionAccepts1271` uses the **same
encoding** under a session with one allowed content type plus a SudoPolicy 1271 policy, and gets
`0x1626ba7e`. So the refusal above comes from the configuration, not from a malformed signature.

**F4. Finding: the 1271 hash is unbound.**
- In the same test, the same signature checked against an **unrelated digest** also returns
  `0x1626ba7e` (logged `permissive session, UNRELATED hash: 0x1626ba7e`, and asserted).
- Cause: `SmartSessionERC7739._erc1271IsValidSignatureViaNestedEIP712` rebuilds the TypedDataSign
  hash from the signature and never compares it to the `hash` argument. Solady's reference has
  this check (`xor(keccak256(0x1e, 0x42), hash)`).
- The code is the same in the verified `0x…8bDABA` source and in upstream `erc7579/smartsessions`
  `main` at `f5aaf867`.
- Consequence: any session allowed to sign any 7739 content can authorise **every** digest,
  including USDC EIP-3009 and Permit2.
- **Requirements:**
  - The SDK and console must never enable a session with non-empty `erc7739Policies`.
  - The hook can't enumerate those settings, so this is an off-chain invariant plus an Oracle
    check (`isERC1271PolicyEnabled` / content lookups). **Not demonstrated.**
- Not yet checked against Rhinestone's audit notes or disclosed. Owner decision.

**Admin calls are unreachable for the session key.** `test_Q4_sessionCannotUninstallHookOrInstallModule`
shows that `uninstallModule(hook)`, both direct and through `execute(target = account)`, and
`installModule(executor)` are each refused by the live validator with
`NoPoliciesSet(permissionId)` (`0x1c792c05…`). `handleOps` reverts `FailedOpWithRevert(AA23)`, and
the hook stays installed.

## 5. Passport mint: works. `agentWallet == wallet`.

`test_Q5_walletMintsPassport_agentWalletIsWallet`: the wallet calls the live registry's
`register("ipfs://spike", [("integrityDid", …), ("sovereignActor", wallet)])` through an
owner-signed UserOp on the 7579 path.
- Logged: `agentId 10767`, `ownerOf 0x17aE…66cC`, `agentWallet 0x17aE…66cC` (the wallet).
- `getMetadata(agentId, "integrityDid")` reads back.
- The hook saw the call.

**How the receiver works.** `onERC721Received` is answered by Safe7579's `receiverFallback`
(the erc7579 `Receiver`), before the hook.

**Negative control.** `test_Q5_negativeControl_noFallbackHandler_mintReverts`: with the fallback
handler cleared, the same mint through `execTransaction` reverts `GS013`. This proves the
Safe7579 fallback is what makes the mint succeed.

## 6. Genuineness + owner: `IAccountVerifier.verify(account)`

The candidate is implemented as `_verify` in the spike. It is property-based: it reads state, and
it works whether the account came from the factory or the Launchpad.
- `account.codehash == 0xd7d408ebcd99b2b70be43e20253d6d92a8ea8fab29bd3be7f55b10032331fb4c`
  (SafeProxy 1.4.1 runtime). It is owner-independent: a second Safe with another owner has the
  same hash (asserted).
- `masterCopy()` (`0xa619486e`) equals the Safe 1.4.1 singleton.
- The fallback handler slot (`0x6c9a…18d5`) equals Safe7579.
- Safe modules equal exactly `[Safe7579]`.
- Guard slot (`0x4a20…34c8`) equals `IntegrityGuard`.
- `getOwners().length == 1`, `getThreshold() == 1`, and the owner has no code (D-M).
- Safe7579 has no global hook, and `IntegrityHook` is the SIG hook on all four selectors.
- There are no 7579 executors.
- The validators are a subset of `{SmartSessions, OwnableValidator}`, and the OwnableValidator
  owners equal `[Safe owner]`.

**Owner.** `getOwners()[0]`.

Evidence:
- `test_Q6_verify_genuineAccount_andProvenance`: `verify: true 0x57DB…6e3D ok`.
- `test_Q6_verify_rejects_secondSafeOwner`: `not single-owner 1/1`.
- `test_Q6_verify_rejects_validatorOwnerDrift`: `OwnableValidator owners != Safe owner`.
- `test_Q6_verify_rejects_hookRemoved`: `IntegrityHook missing on an execution selector`.
- `test_Q2_otherSafeModule…`: `Safe modules != [Safe7579]`.

**Factory provenance** is also provable when the caller supplies `(initializer, saltNonce)`:
`CREATE2(SafeProxyFactory, keccak(keccak(initializer) ‖ saltNonce), keccak(proxyCreationCode ‖ singleton)) == account`
holds (asserted in `test_Q6_verify_genuineAccount_andProvenance`). The property checks are the
authority, though, because the Launchpad flow uses a different initializer.

**Recommendation: two owner sets.** Safe owners and OwnableValidator owners can drift. Prefer **not**
installing OwnableValidator: the owner signs Safe-native `execTransaction`, the console path, and
the validator-0 fallback remains for owner UserOps. Then `verify()` requires the validators to be
exactly `[SmartSessions]`, and I3 has one owner set.

## 7. Build compatibility

**Not compiled under our settings** (0.8.28, cancun, via_ir), and not vendored:
- Safe7579 v1.0.0 was compiled with solc 0.8.26, EVM `paris`, non-IR, 200 runs.
- Smart Sessions was compiled with 0.8.28, `cancun`, 833 runs.
- OwnableValidator `0x…13fdB5` was compiled with 0.8.28, `cancun`, optimizer off.

Recompiling would change bytecode. That breaks the codehash checks in Q6 and the canonical
addresses.

**How to deploy on Anvil (D-D): replay the published CREATE2 deployment transactions.**
`test_Q7_replayPublishedInitCode_landsOnCanonicalAddress` does this on the fork:
1. Read the original deploy tx input (`salt ‖ initcode`) via `vm.rpc`. Smart Sessions' tx is
   `0x447b3488…658e`; Safe7579's is `0x0f714677…a9ed`. Both go to the Safe singleton CREATE2
   factory `0x914d7Fec6aaC8cd542e72Bca78B30650d45643d7`.
2. Assert `CREATE2(factory, salt, keccak(initcode)) == canonical`.
3. Wipe the canonical address (code and nonce), and wipe Safe7579's constructor child
   `Safe7579DCUtil` at `0x45D7deB1229E0254a0561a2769B4A28e4e67Df00`.
4. Replay.

Logged: `replayed 0x…8bDABA 23608`, `constructor child 0x45D7…Df00 2498`,
`replayed 0x7579EE…0002 20014`, with codehash equal to live.

**What Plan 1b needs on a fresh Anvil:**
- **CREATE2 factories:**
  - the Safe singleton factory `0x914d…43d7`, via `anvil_setCode`, since Anvil does not preinstall it
  - Arachnid `0x4e59b448…`, which Anvil preinstalls
- **Then replay the deploy txs for:**
  - EntryPoint v0.7. Its constructor creates `SenderCreator`, so replay rather than etch runtime.
  - Safe 1.4.1 singleton, proxy factory, and MultiSend
  - Safe7579 and its Launchpad
  - Smart Sessions and its compatibility fallback
  - OwnableValidator and SudoPolicy

**Not demonstrated:**
- an actual Anvil run
- replays for components other than Smart Sessions and Safe7579

Etching runtime code is **not** sufficient: it skips constructors, and modules pin EntryPoint in
immutables.

---

## Alternatives (source-level only, not fork-run)

The trigger for running Nexus or Kernel was Q2 or Q3 needing more than one extra contract. It was
not met, and these are recorded so the choice can be checked.

**Biconomy Nexus.**
- Source: `bcnmy/nexus` `main`, 2026-08-07. Deployed: impl v1.0.2
  `0x000000aC74357BFEa72BBD0781833631F732cf19` (21551 bytes), factory
  `0x000000c3A93d2c5E02Cb053AC675665b1c4217F9`, K1Validator
  `0x0000002D6DB27c52E3C11c1Cf24072004AC75cBa`, impl v1.2.0
  `0x000000004F43C49e93C970E84001853a70923B03`.
- Every execution entry has `withHook`: `execute`, `executeFromExecutor`, `executeUserOp`,
  `executeComposable`, `uninstallModule`, `upgradeToAndCall`. So no guard is needed.
- But **every** owner operation is an EntryPoint UserOp, so the hook's `msgSender` is always
  EntryPoint. Nexus has **no** path-based owner signal. Telling owner from session would need the
  transient-marker channel from validation to execution, plus mixed-bundle tests.
- Net: one fewer contract (no guard), but a harder, unproven role source. The Q3 answer is worse.

**ZeroDev Kernel v3.**
- Tag v3.1 `03f7f5c`. Deployed: v3.1 `0xBAC849bB641841b44E965fB01A4Bf5F074f84b4D`, v3.3
  `0xd6CEDDe84be40893d153Be9d467CD6aD37875b28`, ECDSA validator
  `0x845ADb2C711129d4f3966735eD98a9F09fC4cE57`.
- Hooks are bound **per validator**. That would make the role intrinsic, but a hooked validator
  requires `userOp.callData` to start with `executeUserOp` (`OnlyExecuteUserOp`).
- Smart Sessions rejects `executeUserOp` (`UnsupportedExecutionType`; see smartsessions issue #17).
  So Kernel with Smart Sessions cannot use per-validator hooks. Kernel's `execute` also has no hook.
- This rules Kernel out with Smart Sessions.

## Concerns and open items for the owner

1. **F4, Smart Sessions 1271 hash binding** (Q4). Decide whether to disclose to Rhinestone. Keep
   the "no session 1271" invariant as a hard SDK, console and Oracle rule.
2. **Owner UserOps get session limits** (Q3, fail closed). The owner's limit override works only
   through `execTransaction`. This is acceptable if the console signs Safe transactions; confirm.
3. **The `Maintenance` role cannot be told apart** on Safe (Q3). Decide the enum shape for Plan 1b.
4. **Safe 1.4.1 module bypass** is closed by verifier state, not by a check. Safe 1.5.0's module
   guard would close it with a check, but it was not tested with Safe7579 v1.0.0.
5. **Launchpad deployment flow not exercised.** Plan 1b's fork tests should deploy through
   `Safe7579Launchpad`, as production will.
6. `IntegrityHook.onUninstall` must tolerate per-selector uninstall (F2).

## Sources

- Sourcify v2 API, chain 84532: verified sources, compiler settings and deployment txs for
  Safe7579, Smart Sessions (both), the compatibility fallback, OwnableValidator (both), SudoPolicy,
  and the agent0 registry implementation.
- `@rhinestone/module-sdk@0.4.0` (jsDelivr) `_esm/constants.js` and the per-module `constants.js`
  files.
- `permissionless@0.5.2` `_esm/accounts/safe/toSafeSmartAccount.js`: Safe, Safe7579 and Launchpad
  defaults.
- GitHub source, read only:
  - `rhinestonewtf/safe7579`, tag v1.0.0
  - `erc7579/smartsessions` `main` at `f5aaf867`
  - `bcnmy/nexus` `main`
  - `zerodevapp/kernel` tag v3.1
- Base Sepolia public RPC `https://sepolia.base.org` (read-only), for `cast code`, `cast tx` and
  `VERSION()`.
