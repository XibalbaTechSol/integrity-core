// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {IntegrityAccount} from "../../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {MODULE_TYPE_HOOK} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {
    ERC7579Utils,
    Mode,
    CallType,
    ExecType,
    ModeSelector,
    ModePayload
} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @dev Deliberately has NO `boundAccount` restriction at all -- unlike the real
/// `IntegrityKernel`, which reverts `onInstall`/`onUninstall`/`preCheck`/`postCheck` unless
/// `msg.sender == boundAccount`. That restriction is exactly what makes the real kernel need to
/// know the account's address in advance; this placeholder is explicitly scoped to NOT need
/// that, which is the entire point of using it for the genesis install (see
/// `docs/plans/2026-08-24-phase1-halmos-harness-proposal.md`).
contract AlwaysPassingPlaceholderKernel {
    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    function onInstall(bytes calldata) external {}
    function onUninstall(bytes calldata) external {}

    function preCheck(address, uint256, bytes calldata) external pure returns (bytes memory) {
        return "";
    }

    function postCheck(bytes calldata) external pure {}
}

/// @title Shared Halmos harness base: real IntegrityAccount + real IntegrityKernel, installed via
/// the genesis-placeholder-then-governance-swap pattern (Option B).
/// @notice `docs/plans/2026-08-24-phase1-halmos-harness-proposal.md`. Extracted from
/// `KernelSwapHarness.t.sol` (which proved this pattern works, `PRODUCTION_GAPS.md` §42) so the
/// four target properties in `docs/plans/2026-08-24-phase1-formal-verification-proposal.md` don't
/// each re-derive the same setup. `KernelSwapHarness.t.sol` itself still drives the swap steps
/// explicitly rather than through `_swapToKernel` below, since testing the swap mechanism IS that
/// file's own point -- hiding it behind a helper there would test less, not the same thing.
abstract contract HalmosKernelFixture is Test {
    address signer;
    address guardian1;
    address guardian2;
    address guardian3;
    address[] guardianSet;

    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant ABOVE_FLOOR_SCORE = 800;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;

    IntegrityAccount account;
    ReputationRegistry reputation;

    /// @dev Genesis-installs a placeholder (no address prediction needed), matching
    /// `KernelSwapHarness.t.sol`'s own `setUp`.
    function _deployPlaceholderGenesisAccount() internal {
        signer = address(0x5150);
        guardian1 = address(0x611);
        guardian2 = address(0x612);
        guardian3 = address(0x613);
        guardianSet = [guardian1, guardian2, guardian3];

        AlwaysPassingPlaceholderKernel genesisKernel = new AlwaysPassingPlaceholderKernel();
        account = new IntegrityAccount(
            signer, address(genesisKernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
    }

    /// @dev Real `ReputationRegistry` clone + real `IntegrityKernel`, bound to `address(account)`
    /// (already concrete -- never predicted). `account` must already be deployed
    /// (`_deployPlaceholderGenesisAccount` first). See `_setZkBoostExpiry`'s own doc comment for
    /// why the score/boost setup below doesn't use `stdStorage`.
    function _deployRealKernel(address trackedToken, uint256 tokenPerOpBudget, uint256 tokenCumulativeBudget)
        internal
        returns (IntegrityKernel)
    {
        return _deployRealKernel(PER_OP_BUDGET, CUMULATIVE_BUDGET, trackedToken, tokenPerOpBudget, tokenCumulativeBudget);
    }

    /// @dev Overload allowing a non-default native-ETH budget pair -- needed by properties that
    /// must isolate the cumulative check as the binding constraint distinct from the per-op check
    /// (e.g. `KernelProperties.t.sol`'s cumulative-containment property: with the DEFAULT
    /// PER_OP_BUDGET/CUMULATIVE_BUDGET ratio, no sequence of per-op-respecting calls can ever
    /// actually trigger the cumulative check, since 1 ether-per-call, up to N calls, never
    /// exceeds 3 ether with a small N -- a real scoping finding, not a hypothetical one).
    function _deployRealKernel(
        uint256 perOpBudget,
        uint256 cumulativeBudget,
        address trackedToken,
        uint256 tokenPerOpBudget,
        uint256 tokenCumulativeBudget
    ) internal returns (IntegrityKernel) {
        ReputationRegistry reputationImpl = new ReputationRegistry();
        reputation = ReputationRegistry(Clones.clone(address(reputationImpl)));
        reputation.initialize(address(this), address(this), address(0), address(0));

        reputation.updateScore(address(account), ABOVE_FLOOR_SCORE);
        _setZkBoostExpiry(reputation, address(account), block.timestamp + 7 days);

        return new IntegrityKernel(
            address(account),
            perOpBudget,
            cumulativeBudget,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            trackedToken,
            tokenPerOpBudget,
            tokenCumulativeBudget,
            AdapterRegistry(address(0)),
            address(0)
        );
    }

    /// @dev Writes AgentScore.zkBoostExpiry directly via a hand-computed storage slot, NOT
    /// stdStorage's `checked_write` -- stdStorage's auto-discovery depends on `vm.record()`,
    /// confirmed unsupported by Halmos. Slot verified, not guessed: `forge inspect
    /// ReputationRegistry storage-layout` gives `scores` at slot 1 (its OZ v5 `Initializable`/
    /// `AccessControlUpgradeable` bases use ERC-7201 namespaced storage, not the linear slot
    /// space, so there's no inherited-storage offset). A `mapping(address => AgentScore)` entry's
    /// base slot is `keccak256(abi.encode(subject, uint256(1)))`; `AgentScore` is `{uint256
    /// baseScore; uint256 lastUpdate; uint256 zkBoostExpiry;}`, so `zkBoostExpiry` is `+2`.
    /// Cross-validated against the real `scores(address)` getter under plain `forge test` before
    /// being trusted under Halmos (see `PRODUCTION_GAPS.md` §42).
    function _setZkBoostExpiry(ReputationRegistry reg, address subject, uint256 expiry) internal {
        bytes32 baseSlot = keccak256(abi.encode(subject, uint256(1)));
        vm.store(address(reg), bytes32(uint256(baseSlot) + 2), bytes32(expiry));
    }

    /// @dev Drives the real governance swap path to completion: propose, two guardian approvals,
    /// warp past the timelock, execute. `account` must already have a pending-swap-eligible
    /// kernel installed (i.e. this is not the FIRST install, which happens via the constructor).
    function _swapToKernel(address newKernel) internal {
        vm.prank(address(account));
        account.proposeKernelSwap(newKernel);

        (, uint256 readyAt) = account.pendingKernelSwap();
        uint256 swapNonce = account.kernelSwapNonce();

        vm.prank(guardian1);
        account.approveKernelSwap(swapNonce, newKernel);
        vm.prank(guardian2);
        account.approveKernelSwap(swapNonce, newKernel);

        vm.warp(readyAt);

        vm.prank(address(account));
        account.executeKernelSwap(newKernel);
    }

    function _singleCallMode() internal pure returns (bytes32) {
        return Mode.unwrap(
            ERC7579Utils.encodeMode(
                ERC7579Utils.CALLTYPE_SINGLE, ERC7579Utils.EXECTYPE_DEFAULT, ModeSelector.wrap(0), ModePayload.wrap(0)
            )
        );
    }
}
