# Phase I tracer-bullet slice — dependency inventory

Written before any Solidity for this slice was touched, per
`docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md`'s process discipline. Every claim below
was read directly from `contracts/node_modules/@openzeppelin/contracts`, not assumed from the
manifest range.

- **Installed OZ version: 5.6.1 exact** (`node_modules/@openzeppelin/contracts/package.json`).
  `contracts/package.json`'s manifest range is `^5.3.0` — wider than what's actually installed;
  this slice is built and tested against 5.6.1 specifically, not the range.
- **Solidity floor: `^0.8.26`** (`draft-AccountERC7579Hooked.sol`'s own pragma). This repo
  compiles at 0.8.28 (`foundry.toml`), which satisfies it.
- **ERC-4337 EntryPoint: v0.9** — `Account.sol`'s `entryPoint()` defaults to
  `ERC4337Utils.ENTRYPOINT_V09`. No real EntryPoint contract is vendored anywhere in
  `node_modules`. This slice never exercises `validateUserOp`/the EntryPoint/prefund path at all
  (explicit scope exclusion) — tests reach `execute()`'s `onlyEntryPointOrSelf` gate via the
  "self" branch only, using `vm.prank(address(account))`, which exercises the real modifier logic
  (`msg.sender == address(this)`) without needing a live EntryPoint.
- **Execution mode dispatch is NOT restricted by the base class.**
  `AccountERC7579._execute` dispatches on `(CallType, ExecType)` decoded from the mode word:
  `CALLTYPE_SINGLE = 0x00`, `CALLTYPE_BATCH = 0x01`, `CALLTYPE_DELEGATECALL = 0xFF`;
  `EXECTYPE_DEFAULT = 0x00`, `EXECTYPE_TRY = 0x01`. All four calltype/exectype combinations are
  live by default. This slice's subclass MUST override `_execute` to reject every mode except
  `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)` — this is real work, not a default the base class already
  provides.
- **`withHook` already wraps `_execute`, `_fallback`, `_installModule`, `_uninstallModule`** at
  the `AccountERC7579Hooked` level — module install/uninstall already routes through the hook by
  construction. The bootstrap case (installing the *first* hook) is exempt by necessity: `hook()`
  returns `address(0)` before install, so `withHook`'s `if (hook_ != address(0))` guard means no
  preCheck/postCheck fires for that one call. This slice installs its kernel via a direct internal
  `_installModule` call from the constructor (never the external, `onlyEntryPointOrSelf`-gated
  `installModule`), and overrides the external `installModule`/`uninstallModule` entry points to
  revert unconditionally after that — enforcing "no post-bootstrap module mutation" by
  construction, not by nobody calling it.
- **`SignerECDSA` (`utils/cryptography/signers/SignerECDSA.sol`) is a ready-made mixin** satisfying
  `Account`'s abstract `_rawSignatureValidation` requirement — a simple ECDSA-recover-and-compare
  against one stored `signer` address, set once in the constructor. Reused as-is; no custom
  signature-validation logic written for this slice.
- **`installModule`/`uninstallModule`/`execute` are all `onlyEntryPointOrSelf`** (`Account.sol`).
  No separate access-control layer needed for the one CALL path this slice allows — the base
  modifier already restricts it to EntryPoint-or-self, which is the correct set for a real ERC-4337
  account regardless of whether this slice exercises EntryPoint at all.

## What this inventory does NOT cover (deliberately out of scope for this slice)

- Real EntryPoint deployment/UserOp validation/signature-aggregation semantics.
- ERC-7579 executor/fallback module behavior beyond confirming they're never installed.
- Gas-metering specifics of the real canonical EntryPoint (irrelevant without one deployed).
