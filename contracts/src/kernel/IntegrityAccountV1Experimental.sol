// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccountERC7579Hooked} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579Hooked.sol";
import {AccountERC7579} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579.sol";
import {SignerECDSA} from "@openzeppelin/contracts/utils/cryptography/signers/SignerECDSA.sol";
import {MODULE_TYPE_HOOK} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {ERC7579Utils, Mode, CallType, ExecType} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @title IntegrityAccountV1Experimental
/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md).
/// @dev NOT the full Phase I `IntegrityAccount` the plan describes, and NOT a general-purpose
/// ERC-4337/ERC-7579 account. Deliberately narrow, by construction rather than by policy:
///
///  - Non-upgradeable. No proxy, no upgrade path, immutable kernel binding set once at
///    construction via a direct internal `_installModule` call (never the external,
///    `onlyEntryPointOrSelf`-gated `installModule`).
///  - Exactly one hook module, installed atomically in the constructor. `installModule` and
///    `uninstallModule` are overridden below to revert unconditionally -- no post-bootstrap
///    module mutation is reachable through this contract's own external surface, at all.
///  - `execute()` accepts ONLY `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)`. Batch, delegatecall, and
///    try-execution modes are rejected before reaching the base class's dispatch logic.
///  - No executor modules, no fallback modules can ever be installed (module mutation is fully
///    disabled, see above) -- `executeFromExecutor` and the fallback path are therefore
///    unreachable in practice, though not separately overridden here since the disabled
///    `installModule`/`uninstallModule` already make populating either module type impossible.
///  - This slice never exercises the ERC-4337 EntryPoint/UserOp/prefund path. `execute()` is
///    reachable only via `onlyEntryPointOrSelf`'s "self" branch in this slice's own test suite.
///
/// See `IntegrityKernelV1Experimental` for exactly what guarantee the installed hook provides --
/// this account only guarantees that the hook fires on every reachable state-changing path,
/// not what the hook itself checks.
contract IntegrityAccountV1Experimental is AccountERC7579Hooked, SignerECDSA {
    using ERC7579Utils for Mode;

    error ModuleMutationDisabled();
    error UnsupportedExecutionMode(CallType callType, ExecType execType);

    constructor(address signerAddr, address kernel) SignerECDSA(signerAddr) {
        _installModule(MODULE_TYPE_HOOK, kernel, "");
    }

    /// @dev No module mutation reachable through this contract's external surface, ever, after
    /// construction -- the one hook installed in the constructor is permanent by construction.
    function installModule(uint256, address, bytes calldata) public pure override {
        revert ModuleMutationDisabled();
    }

    /// @dev See {installModule}.
    function uninstallModule(uint256, address, bytes calldata) public pure override {
        revert ModuleMutationDisabled();
    }

    /// @dev Rejects every execution mode except (CALLTYPE_SINGLE, EXECTYPE_DEFAULT) before
    /// delegating to the base class, which otherwise supports batch and delegatecall too.
    function _execute(Mode mode, bytes calldata executionCalldata) internal override returns (bytes[] memory) {
        (CallType callType, ExecType execType,,) = mode.decodeMode();
        bool allowed = callType == ERC7579Utils.CALLTYPE_SINGLE && execType == ERC7579Utils.EXECTYPE_DEFAULT;
        if (!allowed) revert UnsupportedExecutionMode(callType, execType);
        return super._execute(mode, executionCalldata);
    }

    /// @dev AccountERC7579 and SignerECDSA both define this (AccountERC7579's own version
    /// deliberately disables raw signatures in favour of the ERC-7579 validator-module pattern
    /// -- see its own doc comment). This slice has no validator module (module mutation is fully
    /// disabled, see {installModule}), so it explicitly resolves the diamond in favour of the
    /// real ECDSA check.
    function _rawSignatureValidation(bytes32 hash, bytes calldata signature)
        internal
        view
        override(AccountERC7579, SignerECDSA)
        returns (bool)
    {
        return SignerECDSA._rawSignatureValidation(hash, signature);
    }
}
