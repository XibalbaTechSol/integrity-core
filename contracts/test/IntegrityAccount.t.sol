// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StdStorage, stdStorage} from "forge-std/StdStorage.sol";
import {IntegrityAccount} from "../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
import {IntegrityToken} from "../src/oracle/IntegrityToken.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {Account as ERC4337Account} from "@openzeppelin/contracts/account/Account.sol";
import {MODULE_TYPE_HOOK} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {
    ERC7579Utils,
    Mode,
    CallType,
    ExecType,
    ModeSelector,
    ModePayload
} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @dev Deliberately conforms only to the shallow `isModuleType` probe `proposeKernelSwap` now
/// performs -- used to prove that probe genuinely rejects a non-conforming address, not just a
/// zero address.
contract NonHookModule {
    function isModuleType(uint256) external pure returns (bool) {
        return false;
    }
}

/// @dev Adversarial fixture for the Devil's Advocate review's area-1/area-4 finding: a kernel
/// that passes the shallow `isModuleType` probe (so it installs) but reverts unconditionally in
/// `preCheck` -- demonstrating the probe cannot and does not verify hook-logic correctness, and
/// that this class of failure has no on-chain rescue path once installed.
contract AlwaysRevertingKernel {
    error AlwaysReverts();

    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    function onInstall(bytes calldata) external {}
    function onUninstall(bytes calldata) external {}

    function preCheck(address, uint256, bytes calldata) external pure returns (bytes memory) {
        revert AlwaysReverts();
    }

    function postCheck(bytes calldata) external pure {}
}

/// @dev Adversarial fixture for the guardian-quorum proposal's own adversarial-pass requirement:
/// "interaction with the existing reentrancy windows -- does a reentrant call during
/// onInstall/onUninstall see stale or fresh approval state?" Both `onInstall` and `onUninstall`
/// fire strictly AFTER `executeKernelSwap` has already `delete`d `pendingKernelSwap`, but BEFORE
/// any cleanup of `kernelSwapNonce`/`kernelSwapApprovalCount` (there is none -- a fresh nonce on
/// the next `proposeKernelSwap` is what makes old approvals irrelevant, not an explicit clear).
/// This fixture captures exactly what a reentrant caller observes at that moment, and separately
/// proves the quorum-relevant state-changing entry points cannot themselves be reached from
/// inside the callback -- `msg.sender` there is this contract's own address, which is neither
/// `address(account)` nor a registered guardian.
contract ReentrancyObserverKernel {
    IntegrityAccount public immutable account;

    bool public onInstallCalled;
    address public observedPendingKernelAtInstall;
    uint256 public observedPendingReadyAtAtInstall;
    uint256 public observedApprovalCountAtInstall;
    bool public reentrantProposeRevertedAtInstall;
    bool public reentrantApproveRevertedAtInstall;

    bool public onUninstallCalled;
    address public observedPendingKernelAtUninstall;
    uint256 public observedApprovalCountAtUninstall;

    constructor(IntegrityAccount account_) {
        account = account_;
    }

    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    /// @dev Reads `account.kernelSwapNonce()` live rather than a value fixed at construction --
    /// this same instance plays "new kernel" (onInstall fires) in one swap and "old kernel"
    /// (onUninstall fires) in a later one, and the currently-relevant nonce differs between them.
    function onInstall(bytes calldata) external {
        onInstallCalled = true;
        (address pendingKernel, uint256 readyAt) = account.pendingKernelSwap();
        observedPendingKernelAtInstall = pendingKernel;
        observedPendingReadyAtAtInstall = readyAt;
        observedApprovalCountAtInstall = account.kernelSwapApprovalCount(account.kernelSwapNonce());

        // Reentrant attempts from a non-self, non-guardian caller must both fail closed --
        // proving this window cannot be used to mutate quorum state, even though it remains open
        // for observation.
        try account.proposeKernelSwap(address(this)) {
            reentrantProposeRevertedAtInstall = false;
        } catch {
            reentrantProposeRevertedAtInstall = true;
        }
        try account.approveKernelSwap(account.kernelSwapNonce(), address(this)) {
            reentrantApproveRevertedAtInstall = false;
        } catch {
            reentrantApproveRevertedAtInstall = true;
        }
    }

    function onUninstall(bytes calldata) external {
        onUninstallCalled = true;
        (address pendingKernel,) = account.pendingKernelSwap();
        observedPendingKernelAtUninstall = pendingKernel;
        observedApprovalCountAtUninstall = account.kernelSwapApprovalCount(account.kernelSwapNonce());
    }

    function preCheck(address, uint256, bytes calldata) external pure returns (bytes memory) {
        return "";
    }

    function postCheck(bytes calldata) external pure {}
}

/// @dev Adversarial fixture for the reentrancy-guard proposal
/// (docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md): attempts a genuinely
/// reentrant call into the account's UNGATED `fallback()` (not the `onlyEntryPointOrSelf`-gated
/// `execute()`, which a hostile kernel could never reach directly -- its caller identity from the
/// account's perspective is the kernel's own address) from both `onInstall` (playing "new kernel")
/// and `onUninstall` (playing "old kernel"), recording whether each attempt was rejected.
contract ReentrantFallbackKernel {
    IntegrityAccount public immutable account;

    // Both the guarded and unguarded paths ultimately revert the reentrant call (the account
    // never installs a fallback handler, so `_fallback` fails closed regardless) -- the REVERT
    // REASON, not success/failure, is what proves the guard actually intercepts the call before
    // `preCheck` runs, rather than merely happening to fail for an unrelated, pre-existing reason.
    bytes4 public installReentrantRevertSelector;
    bytes4 public uninstallReentrantRevertSelector;

    constructor(IntegrityAccount account_) {
        account = account_;
    }

    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    function onInstall(bytes calldata) external {
        installReentrantRevertSelector = _attemptReentrantFallback();
    }

    function onUninstall(bytes calldata) external {
        uninstallReentrantRevertSelector = _attemptReentrantFallback();
    }

    function _attemptReentrantFallback() internal returns (bytes4 revertSelector) {
        (bool success, bytes memory returnData) =
            address(account).call(abi.encodeWithSignature("aSelectorThatDoesNotExist()"));
        if (success) return bytes4(0);
        if (returnData.length < 4) return bytes4(0);
        return bytes4(returnData);
    }

    function preCheck(address, uint256, bytes calldata) external pure returns (bytes memory) {
        return "";
    }

    function postCheck(bytes calldata) external pure {}
}

/// @dev Adversarial fixture for the constant-drift finding a Devil's Advocate review surfaced:
/// exposes the same `scores`/`ZK_BOOST_BPS`/`BPS_DENOMINATOR` shape as the real
/// `ReputationRegistry`, but with DIFFERENT boost constants, to prove
/// `IntegrityKernel`'s constructor-time cross-check genuinely rejects a mismatch
/// rather than silently trusting its own local mirror.
contract MismatchedBoostRegistry {
    uint256 public constant ZK_BOOST_BPS = 20_000;
    uint256 public constant BPS_DENOMINATOR = 10_000;

    function scores(address) external pure returns (uint256 baseScore, uint256 lastUpdate, uint256 zkBoostExpiry) {
        return (0, 0, 0);
    }
}

/// @dev Fixture for the epoch/timelock deployment-invariant proposal's Option B (fail-open,
/// 2026-08-19): a fully-conforming, working hook module that deliberately does NOT implement
/// `epochLengthSeconds()` at all -- representing a legitimate future kernel that doesn't use
/// reputation epoch-snapshotting (e.g. budget-only, no reputation check). Used to prove
/// `_checkEpochCompatibility`'s `try`/`catch` genuinely skips the invariant for such a kernel
/// rather than rejecting it outright, matching the account's own disclosed fail-open caveat.
contract NonSnapshottingKernel {
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

/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md),
/// extended with a second reference adapter
/// (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md). NOT the full Phase I kernel.
/// Non-deployable, non-upgradeable, single CALL mode only, two conjunctive conditions (a
/// native-value spend budget and a reputation floor). See both proposal docs for full scope
/// boundaries -- this test file only proves what those documents claim, nothing more.
contract IntegrityAccountTest is Test {
    using stdStorage for StdStorage;

    address signer;
    uint256 signerKey;
    address recipient = makeAddr("recipient");

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant ABOVE_FLOOR_SCORE = 800;
    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    // Must be >= MODULE_ACTION_TIMELOCK as of the epoch/timelock deployment-invariant check
    // (2026-08-19, PRODUCTION_GAPS.md §37) -- `_checkEpochCompatibility` now rejects a genesis
    // or swapped-in kernel whose epoch is shorter than this account's timelock. Was `1 days`
    // (deliberately shorter than MODULE_ACTION_TIMELOCK) before that check existed, specifically
    // so the default fixture could demonstrate the pre-existing SnapshotStale interaction bug
    // this invariant closes -- that demonstration is now `test_deployingMismatchedGenesisPairRevertsAtConstruction`'s
    // job via a dedicated, deliberately-uncompliant standalone kernel, not the shared fixture's.
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;

    IntegrityKernel kernel;
    IntegrityAccount account;
    ReputationRegistry reputation;
    address[] guardianSet;
    address guardian1;
    address guardian2;
    address guardian3;

    /// @dev A SECOND account+kernel pair with `trackedToken` enabled, deployed here (not lazily
    /// inside a test body) specifically so its storage is in the same cold/warm state relative to
    /// each test body as the shared `kernel`/`account` pair above -- deploying it inside a test
    /// body instead would leave the token's balance slot warm from the same-transaction mint,
    /// understating the real (first-touch-per-transaction) gas cost `preCheck` pays in production.
    /// See `docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md`.
    uint256 constant TOKEN_PER_OP_BUDGET = 10 ether;
    uint256 constant TOKEN_CUMULATIVE_BUDGET = 25 ether;
    IntegrityKernel tokenKernel;
    IntegrityAccount tokenAccount;
    IntegrityToken token;

    function setUp() public {
        (signer, signerKey) = makeAddrAndKey("signer");
        guardian1 = makeAddr("guardian1");
        guardian2 = makeAddr("guardian2");
        guardian3 = makeAddr("guardian3");
        guardianSet = [guardian1, guardian2, guardian3];

        // ReputationRegistry disables initializers on its own implementation constructor
        // (standard OZ upgradeable-safety pattern) -- deploy a real EIP-1167 clone, same as
        // AgentPrimitivesFactory does in production, rather than a bare `new` (which would
        // revert InvalidInitialization on `initialize`). effectiveScore/updateScore never touch
        // zkVerifier/stateAnchor (confirmed in the proposal doc), so address(0) for both is fine.
        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        // Kernel and account are mutually referential (kernel binds to the account address,
        // account installs the kernel at construction) -- CREATE2-predicted address breaks the
        // circularity without needing a two-step "deploy then bind" flow that would leave a
        // window where the account exists with no kernel installed.
        address predictedAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        // Set the score BEFORE the account exists at its predicted address -- effectiveScore is
        // keyed by address regardless of whether anything is deployed there yet.
        reputation.updateScore(predictedAccount, ABOVE_FLOOR_SCORE);
        // isZkBoosted has no direct setter -- submitZkAttestation is the real path, and it's
        // out of scope for a kernel-level test (see the assurance-tier proposal doc). Writing
        // the AgentScore.zkBoostExpiry storage slot directly is the standard Foundry technique
        // for reaching state that's real production state but not reachable through a simple
        // mock call.
        _setZkBoostExpiry(predictedAccount, block.timestamp + 7 days);
        kernel = new IntegrityKernel(
            predictedAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0
        );
        account = new IntegrityAccount(
            signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        assertEq(address(account), predictedAccount, "CREATE address prediction must match actual deployment");
        vm.deal(address(account), 10 ether);

        // Second pair, token-tracking enabled -- same CREATE-prediction dance, same reputation
        // registry (a fresh score entry keyed by the new predicted address).
        token = new IntegrityToken(address(this), 0);
        address predictedTokenAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        reputation.updateScore(predictedTokenAccount, ABOVE_FLOOR_SCORE);
        _setZkBoostExpiry(predictedTokenAccount, block.timestamp + 7 days);
        tokenKernel = new IntegrityKernel(
            predictedTokenAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(token),
            TOKEN_PER_OP_BUDGET,
            TOKEN_CUMULATIVE_BUDGET
        );
        tokenAccount = new IntegrityAccount(
            signer, address(tokenKernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        assertEq(
            address(tokenAccount), predictedTokenAccount, "CREATE address prediction must match actual deployment"
        );
        vm.deal(address(tokenAccount), 10 ether);
        // Minted here, in setUp -- NOT in the test body -- specifically so the token's balance
        // storage slot for tokenAccount is genuinely COLD when a test body first reads it via
        // `preCheck`. Foundry treats setUp() and the test function as separate top-level calls,
        // so EIP-2929 access-list warmth does NOT carry over between them -- exactly why
        // `reputation`'s storage (also written in setUp, read cold in every test body) cost ~2.6k
        // for its first cross-contract read, per this kernel's own contract-level doc comment.
        // Minting inside a test body instead would make the SAME transaction's later `preCheck`
        // read see a WARM slot, understating the real first-touch-per-transaction cost a
        // production `preCheck` call actually pays.
        token.mint(address(tokenAccount), 100 ether);
    }

    /// @dev Gathers exactly enough guardian approvals (2-of-3) for `nonce` to satisfy
    /// executeKernelSwap's quorum check. Callers that need to test below-threshold or
    /// non-guardian paths approve directly instead of using this helper.
    function _approveWithTwoGuardians(uint256 nonce, address newKernel) internal {
        vm.prank(guardian1);
        account.approveKernelSwap(nonce, newKernel);
        vm.prank(guardian2);
        account.approveKernelSwap(nonce, newKernel);
    }

    /// @dev AgentScore is {uint256 baseScore; uint256 lastUpdate; uint256 zkBoostExpiry;} --
    /// depth(2) selects the third field. Confirmed against the real struct layout in
    /// ReputationRegistry.sol, not guessed.
    function _setZkBoostExpiry(address subject, uint256 expiry) internal {
        stdstore.target(address(reputation)).sig("scores(address)").with_key(subject).depth(2).checked_write(expiry);
    }

    function _singleCallMode() internal pure returns (bytes32) {
        return Mode.unwrap(
            ERC7579Utils.encodeMode(
                ERC7579Utils.CALLTYPE_SINGLE, ERC7579Utils.EXECTYPE_DEFAULT, ModeSelector.wrap(0), ModePayload.wrap(0)
            )
        );
    }

    function test_inBudgetCallSucceedsAndCommits() public {
        uint256 recipientBalanceBefore = recipient.balance;
        uint256 sendAmount = 0.5 ether;

        // Equivalent to ERC7579Utils.encodeSingle(recipient, sendAmount, "") -- inlined because
        // encodeSingle's third parameter is `bytes calldata`, which a bare "" literal cannot
        // satisfy outside of an external call boundary.
        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            recipient.balance, recipientBalanceBefore + sendAmount, "recipient must receive the in-budget transfer"
        );
    }

    function test_overPerOpBudgetCallRevertsBeforeAnyStateChange() public {
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;
        uint256 overBudgetAmount = PER_OP_BUDGET + 1;

        bytes memory executionCalldata = abi.encodePacked(recipient, overBudgetAmount, bytes(""));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.PerOperationBudgetExceeded.selector, overBudgetAmount, PER_OP_BUDGET
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            address(account).balance, accountBalanceBefore, "account balance must be unchanged after a reverted call"
        );
        assertEq(recipient.balance, recipientBalanceBefore, "recipient must not receive anything from a reverted call");
        assertFalse(kernel.armed(), "the armed guard must not be left set after a reverted call");
    }

    function test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget() public {
        // Three calls at PER_OP_BUDGET each = 3 ether, each individually within the 1 ether
        // per-op cap, and the running total lands exactly AT the 3 ether cumulative cap
        // (allowed -- the boundary itself is not a violation). A fourth call, even a small
        // one well within the per-op cap on its own, must fail purely on cumulative grounds.
        vm.startPrank(address(account));
        account.execute(_singleCallMode(), abi.encodePacked(recipient, PER_OP_BUDGET, bytes("")));
        account.execute(_singleCallMode(), abi.encodePacked(recipient, PER_OP_BUDGET, bytes("")));
        account.execute(_singleCallMode(), abi.encodePacked(recipient, PER_OP_BUDGET, bytes("")));
        assertEq(kernel.cumulativeSpentWei(), 3 * PER_OP_BUDGET);
        assertEq(
            kernel.cumulativeSpentWei(), CUMULATIVE_BUDGET, "test setup must land exactly at the cumulative boundary"
        );

        uint256 fourthCallAmount = 0.1 ether;
        uint256 recipientBalanceBeforeFourthCall = recipient.balance;
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.CumulativeBudgetExceeded.selector,
                CUMULATIVE_BUDGET,
                fourthCallAmount,
                CUMULATIVE_BUDGET
            )
        );
        account.execute(_singleCallMode(), abi.encodePacked(recipient, fourthCallAmount, bytes("")));
        vm.stopPrank();

        assertEq(
            recipient.balance,
            recipientBalanceBeforeFourthCall,
            "the over-cumulative-budget fourth call must not move any funds"
        );
        assertEq(kernel.cumulativeSpentWei(), CUMULATIVE_BUDGET, "cumulative spend must not advance on a reverted call");
    }

    // --- (c): batch/delegatecall/module-install must all be rejected or unreachable -----------

    function test_batchExecutionModeIsRejected() public {
        Mode batchMode = ERC7579Utils.encodeMode(
            ERC7579Utils.CALLTYPE_BATCH, ERC7579Utils.EXECTYPE_DEFAULT, ModeSelector.wrap(0), ModePayload.wrap(0)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.UnsupportedExecutionMode.selector,
                ERC7579Utils.CALLTYPE_BATCH,
                ERC7579Utils.EXECTYPE_DEFAULT
            )
        );
        vm.prank(address(account));
        account.execute(Mode.unwrap(batchMode), "");
    }

    function test_delegatecallExecutionModeIsRejected() public {
        Mode delegateMode = ERC7579Utils.encodeMode(
            ERC7579Utils.CALLTYPE_DELEGATECALL, ERC7579Utils.EXECTYPE_DEFAULT, ModeSelector.wrap(0), ModePayload.wrap(0)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.UnsupportedExecutionMode.selector,
                ERC7579Utils.CALLTYPE_DELEGATECALL,
                ERC7579Utils.EXECTYPE_DEFAULT
            )
        );
        vm.prank(address(account));
        account.execute(Mode.unwrap(delegateMode), "");
    }

    function test_tryExecTypeIsRejectedEvenWithSingleCalltype() public {
        Mode tryMode = ERC7579Utils.encodeMode(
            ERC7579Utils.CALLTYPE_SINGLE, ERC7579Utils.EXECTYPE_TRY, ModeSelector.wrap(0), ModePayload.wrap(0)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.UnsupportedExecutionMode.selector,
                ERC7579Utils.CALLTYPE_SINGLE,
                ERC7579Utils.EXECTYPE_TRY
            )
        );
        vm.prank(address(account));
        account.execute(Mode.unwrap(tryMode), "");
    }

    function test_moduleInstallIsUnconditionallyDisabled() public {
        vm.expectRevert(IntegrityAccount.ModuleMutationDisabled.selector);
        vm.prank(address(account));
        account.installModule(4, address(0xBEEF), "");
    }

    function test_moduleUninstallIsUnconditionallyDisabled() public {
        // Even an attempt to uninstall the ALREADY-installed real kernel must be rejected --
        // this is what makes the kernel binding permanent, not just "nobody happens to call it".
        vm.expectRevert(IntegrityAccount.ModuleMutationDisabled.selector);
        vm.prank(address(account));
        account.uninstallModule(4, address(kernel), "");
    }

    // --- (d): the hook frame's armed guard actually does its job ------------------------------

    function test_postCheckCannotBeCalledDirectlyWithoutAPrecedingPreCheck() public {
        vm.expectRevert(IntegrityKernel.NotArmed.selector);
        vm.prank(address(account));
        kernel.postCheck(abi.encode(address(account).balance));
    }

    function test_preCheckAndPostCheckRejectCallersOtherThanTheBoundAccount() public {
        address stranger = makeAddr("stranger");
        vm.expectRevert(abi.encodeWithSelector(IntegrityKernel.Unauthorized.selector, stranger));
        vm.prank(stranger);
        kernel.preCheck(stranger, 0, "");

        vm.expectRevert(abi.encodeWithSelector(IntegrityKernel.Unauthorized.selector, stranger));
        vm.prank(stranger);
        kernel.postCheck(abi.encode(uint256(0)));
    }

    /// @dev The concrete scenario the `armed` guard exists for: the account's own `_execute`
    /// making a low-level call whose target is `address(account)` itself, with calldata encoding
    /// a NESTED `execute()` call -- a genuine self-call, not a proxy for it, so the nested
    /// invocation's `msg.sender` really is `address(account)`, satisfying `onlyEntryPointOrSelf`
    /// for real. Without the `armed` guard, the reentrant call's own preCheck would proceed
    /// (armed is only ever set by the outer preCheck, not yet cleared at this point in the call
    /// stack), letting a call sequence bypass proper cumulative accounting. With the guard, the
    /// reentrant attempt must revert `AlreadyArmed`, and that revert propagates out to fail the
    /// ENTIRE outer call too (Solidity call semantics -- an exception anywhere unwinds the whole
    /// transaction), so no funds move at all, from either the outer or the nested call.
    function test_reentrantExecuteDuringAnInFlightCallIsRejected() public {
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory nestedCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        bytes memory nestedExecuteCall = abi.encodeCall(account.execute, (_singleCallMode(), nestedCalldata));
        // Outer call: target is the account itself, value 0, calldata is the nested execute()
        // call -- a genuine self-call, so the nested invocation's msg.sender really is the
        // account, not this test contract or a third-party attacker contract.
        bytes memory outerCalldata = abi.encodePacked(address(account), uint256(0), nestedExecuteCall);

        vm.prank(address(account));
        vm.expectRevert(IntegrityKernel.AlreadyArmed.selector);
        account.execute(_singleCallMode(), outerCalldata);

        assertEq(
            address(account).balance,
            accountBalanceBefore,
            "no funds may move when the reentrant attempt fails the whole call"
        );
        assertEq(recipient.balance, recipientBalanceBefore);
        assertFalse(kernel.armed(), "armed must be false again once the whole transaction has unwound");
    }

    // --- reputation-floor adapter (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md)

    function test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget() public {
        // setUp() leaves the account ZK-boosted by default (for the assurance-tier adapter's own
        // tests), and effectiveScore() applies the boost BEFORE the floor comparison -- a raw
        // baseScore of MIN_EFFECTIVE_SCORE-1 (499) boosted by 1.15x is 573, which is ABOVE the
        // floor and would make this test wrongly pass. Use a base score low enough to stay below
        // the floor even after boosting, and compute the exact boosted value the contract itself
        // would compute (399's own integer math, not a hand-rounded guess) for the revert assertion.
        uint256 belowFloorBaseScore = 400;
        reputation.updateScore(address(account), belowFloorBaseScore);
        // Reputation is now cached (docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md)
        // -- a registry mutation is not visible to preCheck until refreshed.
        kernel.refreshReputationSnapshot();
        uint256 boostedScore = (belowFloorBaseScore * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        assertLt(boostedScore, MIN_EFFECTIVE_SCORE, "test setup must stay below the floor even after the ZK boost");

        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.ReputationBelowFloor.selector, boostedScore, MIN_EFFECTIVE_SCORE
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            address(account).balance,
            accountBalanceBefore,
            "a below-floor call must move no funds, even a well-within-budget amount"
        );
        assertEq(recipient.balance, recipientBalanceBefore);
    }

    function test_scoreExactlyAtTheFloorSucceeds() public {
        reputation.updateScore(address(account), MIN_EFFECTIVE_SCORE);
        // Without this refresh, the cache would still hold setUp()'s stale ABOVE_FLOOR_SCORE
        // (boosted to 920), and this test would spuriously pass without ever exercising the
        // actual floor boundary it claims to test -- caught during the snapshot-mechanism build.
        kernel.refreshReputationSnapshot();
        uint256 recipientBalanceBefore = recipient.balance;
        uint256 sendAmount = 0.1 ether;

        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            recipient.balance,
            recipientBalanceBefore + sendAmount,
            "a score exactly at the floor must succeed, the boundary itself is not a violation"
        );
    }

    /// @dev Confirms all three checks are genuinely independent -- an above-floor, ZK-boosted
    /// account is still bound by the budget check; passing the other two conditions does not
    /// somehow short-circuit it.
    function test_aboveFloorButOverBudgetCallStillRevertsOnBudget() public {
        // setUp already leaves the account above the reputation floor (ABOVE_FLOOR_SCORE) and
        // ZK-boosted by default -- this single test already covers "all other checks pass,
        // budget is still independently enforced" for both of them.
        uint256 overBudgetAmount = PER_OP_BUDGET + 1;
        bytes memory executionCalldata = abi.encodePacked(recipient, overBudgetAmount, bytes(""));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.PerOperationBudgetExceeded.selector, overBudgetAmount, PER_OP_BUDGET
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    // --- assurance-tier adapter (docs/plans/2026-08-17-phase1-assurance-tier-adapter-proposal.md)

    function test_nonBoostedAccountRevertsEvenWhenBudgetAndReputationBothPass() public {
        _setZkBoostExpiry(address(account), 0);
        kernel.refreshReputationSnapshot();
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.AssuranceTierNotMet.selector, address(account))
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            address(account).balance,
            accountBalanceBefore,
            "a non-boosted call must move no funds even when budget and reputation both pass"
        );
        assertEq(recipient.balance, recipientBalanceBefore);
    }

    /// @dev A real time-based boundary, not just a static true/false -- isZkBoosted's own logic
    /// is `block.timestamp <= zkBoostExpiry`, so an attestation that has JUST expired (expiry in
    /// the past) must be treated identically to never having been boosted at all.
    function test_expiredBoostIsTreatedAsNotBoosted() public {
        _setZkBoostExpiry(address(account), block.timestamp - 1);
        assertFalse(
            reputation.isZkBoosted(address(account)),
            "test setup must genuinely be expired, not accidentally still live"
        );
        kernel.refreshReputationSnapshot();

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.AssuranceTierNotMet.selector, address(account))
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    // --- gas assertions (whitepaper Table 4: preCheck <= 40k total) ---------------------------

    /// @dev SUPERSEDES the prior `test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`
    /// -- that test documented a real, measured over-budget finding (~40,129 gas with all three
    /// checks reading live cross-contract state). Reputation epoch-snapshotting
    /// (docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md) resolves it for real, not
    /// by loosening a threshold: `preCheck` now reads a local cache instead of making two
    /// cross-contract calls, and this is the live confirmation. Measured directly, not estimated.
    /// The steady-state case (post-refresh, within-epoch, exercised here via setUp()'s own
    /// constructor-time snapshot with no additional refresh needed) is what matters for the
    /// Table 4 claim -- see `test_refreshReputationSnapshotGasCost` for the amortized cost this
    /// design defers, not eliminates.
    function test_preCheckGasIsUnderPaperTable4BudgetWithCachedReputation() public {
        vm.prank(address(account));
        uint256 gasBefore = gasleft();
        kernel.preCheck(address(account), 0, "");
        uint256 gasUsed = gasBefore - gasleft();

        assertLt(
            gasUsed,
            40_000,
            "the whole point of epoch-snapshotting is to bring preCheck back under the whitepaper's "
            "Table 4 budget for the steady-state, non-refresh path -- if this fails, the fix did "
            "not actually resolve the finding it was built to close"
        );
        assertGt(
            gasUsed,
            30_000,
            "regression floor -- a further, unexplained drop could mean a check silently stopped "
            "doing real work rather than a genuine optimization"
        );

        // Clean up the armed state this direct call left behind, so it doesn't leak into any
        // test that happens to run after this one in the same suite (Foundry gives each test
        // function a fresh contract deployment via setUp, so this is defensive, not required).
        vm.prank(address(account));
        kernel.postCheck(abi.encode(address(account).balance, uint256(0)));
    }

    /// @dev The gas this design defers rather than eliminates -- makes the "amortized, not free"
    /// tradeoff visible as its own regression, not hidden by only reporting the cheap path. Also
    /// confirms `refreshReputationSnapshot` is genuinely cheaper than today's live-read cost would
    /// be (one external call to the `scores` struct getter instead of two separate calls to
    /// `effectiveScore`/`isZkBoosted`), per the proposal doc's efficiency claim.
    function test_refreshReputationSnapshotGasCost() public {
        uint256 gasBefore = gasleft();
        kernel.refreshReputationSnapshot();
        uint256 gasUsed = gasBefore - gasleft();

        assertLt(
            gasUsed,
            40_000,
            "refresh should cost less than the old two-external-call live-read design did in "
            "total, since it now makes only one external call to the scores struct getter"
        );
    }

    /// @dev The staleness window is a real, accepted gap, not a rounding error (see the proposal
    /// doc's "Real risk worth naming explicitly"). Proves it directly: a real reputation change
    /// is genuinely invisible to preCheck until a refresh, even while the snapshot is otherwise
    /// still within its epoch (this is not the SnapshotStale case -- that is tested separately).
    function test_withinEpochPreCheckDoesNotReflectARealReputationChangeUntilRefreshed() public {
        uint256 belowFloorScore = 400;
        reputation.updateScore(address(account), belowFloorScore);
        // Deliberately NOT calling kernel.refreshReputationSnapshot() -- proving the cache is a
        // real cache, not accidentally still reading live state.
        assertLt(
            block.timestamp,
            kernel.snapshotTakenAt() + kernel.epochLengthSeconds(),
            "sanity: still within the epoch, so this must not be the SnapshotStale case"
        );

        uint256 recipientBalanceBefore = recipient.balance;
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(
            recipient.balance,
            recipientBalanceBefore + 0.1 ether,
            "the call must succeed using the stale-but-not-yet-expired cached score, "
            "even though the real registry score has since dropped below the floor"
        );
    }

    /// @dev Mutation-tested alongside its own guard: a snapshot older than epochLengthSeconds
    /// must block execution even when the underlying reputation is genuinely fine, rather than
    /// silently falling back to a live read or (worse) silently permitting the call.
    function test_staleSnapshotRevertsEvenWhenRealReputationWouldPass() public {
        vm.warp(block.timestamp + REPUTATION_EPOCH_LENGTH + 1);

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.SnapshotStale.selector, 1, block.timestamp, REPUTATION_EPOCH_LENGTH
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    /// @dev Confirms refresh is genuinely permissionless (a stranger can call it, not only the
    /// bound account) and that it actually restores normal operation after a staleness revert.
    function test_refreshBySomeoneOtherThanTheAccountRestoresOperationAfterStaleness() public {
        vm.warp(block.timestamp + REPUTATION_EPOCH_LENGTH + 1);
        address keeper = makeAddr("keeper");
        vm.prank(keeper);
        kernel.refreshReputationSnapshot();

        uint256 recipientBalanceBefore = recipient.balance;
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
        assertEq(recipient.balance, recipientBalanceBefore + 0.1 ether);
    }

    function test_constructorRevertsOnZeroEpochLength() public {
        vm.expectRevert(IntegrityKernel.ZeroEpochLength.selector);
        new IntegrityKernel(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, 0,
            address(0), 0, 0
        );
    }

    /// @dev SUPERSEDES an earlier version of this test that only compared two hardcoded literals
    /// against each other and never touched `kernel` at all (caught by an independent
    /// adversarial review -- ZK_BOOST_BPS/BPS_DENOMINATOR are `private` on the kernel, so nothing
    /// external could even read them to verify a real match). This is a genuine differential
    /// test: refresh the cache, then assert it equals a REAL live `effectiveScore()` read against
    /// the same registry, at the same moment -- the only way to actually catch a rounding,
    /// boundary, or order-of-operations divergence between the kernel's reimplementation and the
    /// registry's own math.
    function test_refreshedSnapshotMatchesALiveEffectiveScoreRead() public {
        kernel.refreshReputationSnapshot();
        assertEq(kernel.snapshotScore(), reputation.effectiveScore(address(account)));
        assertEq(kernel.snapshotIsZkBoosted(), reputation.isZkBoosted(address(account)));
    }

    /// @dev The real, code-level guard the differential test above builds on: the constructor
    /// cross-checks its local ZK_BOOST_BPS/BPS_DENOMINATOR against the REAL bound registry's own
    /// values and reverts on any mismatch, so a future ReputationRegistry deployment with
    /// different constants fails loudly at deploy time instead of silently producing wrong
    /// cached scores forever.
    function test_constructorRevertsWhenBoostConstantsMismatchTheRegistry() public {
        MismatchedBoostRegistry mismatched = new MismatchedBoostRegistry();
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.BoostConstantsMismatch.selector,
                11_500,
                mismatched.ZK_BOOST_BPS(),
                10_000,
                mismatched.BPS_DENOMINATOR()
            )
        );
        new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(mismatched),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0
        );
    }

    function test_constructorRevertsOnEpochLengthTooLong() public {
        uint256 tooLong = kernel.MAX_EPOCH_LENGTH_SECONDS() + 1;
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.EpochLengthTooLong.selector, tooLong, kernel.MAX_EPOCH_LENGTH_SECONDS()
            )
        );
        new IntegrityKernel(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, tooLong,
            address(0), 0, 0
        );
    }

    function test_refreshReputationSnapshotEmitsEvent() public {
        vm.expectEmit(address(kernel));
        emit IntegrityKernel.ReputationSnapshotRefreshed(
            reputation.effectiveScore(address(account)), reputation.isZkBoosted(address(account)), block.timestamp
        );
        kernel.refreshReputationSnapshot();
    }

    /// @dev The compounding case a Devil's Advocate review flagged as untested: the existing
    /// expired-boost test always refreshes immediately after mutating the registry, which only
    /// proves "after a refresh, an expired boost is rejected." This proves the OTHER half -- while
    /// still within the epoch (not the SnapshotStale case), a boost that expires in the REAL
    /// registry is invisible to preCheck until refreshed, and BOTH the assurance-tier flag AND the
    /// boosted (1.15x) score stay stale-permissive simultaneously, not just one of them.
    function test_withinEpochBoostExpiryIsNotReflectedUntilRefreshed() public {
        _setZkBoostExpiry(address(account), block.timestamp + 1);
        kernel.refreshReputationSnapshot();
        assertTrue(kernel.snapshotIsZkBoosted(), "sanity: cache must start boosted");
        uint256 boostedSnapshotScore = kernel.snapshotScore();

        vm.warp(block.timestamp + 2);
        assertFalse(reputation.isZkBoosted(address(account)), "sanity: the real boost must have genuinely expired");
        assertLt(
            block.timestamp,
            kernel.snapshotTakenAt() + kernel.epochLengthSeconds(),
            "sanity: still within the epoch, so this must not be the SnapshotStale case"
        );

        // Deliberately NOT refreshing -- the stale cache must still report boosted=true and the
        // same boosted score, even though the real registry now says otherwise.
        assertTrue(kernel.snapshotIsZkBoosted(), "the cache must stay stale-permissive on the assurance tier");
        assertEq(kernel.snapshotScore(), boostedSnapshotScore, "the cache must stay stale-permissive on the score");

        uint256 recipientBalanceBefore = recipient.balance;
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
        assertEq(
            recipient.balance,
            recipientBalanceBefore + 0.1 ether,
            "the call must succeed on the stale-but-not-yet-expired cache despite the real boost having expired"
        );
    }

    // --- kernel-swap governance (timelocked, atomic, single-signer) ---------------------------

    function _deployKernel(uint256 minEffectiveScore) internal returns (IntegrityKernel) {
        return new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            minEffectiveScore,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0
        );
    }

    function test_proposeKernelSwapRevertsOnZeroKernel() public {
        vm.expectRevert(IntegrityAccount.ZeroKernel.selector);
        vm.prank(address(account));
        account.proposeKernelSwap(address(0));
    }

    function test_proposeKernelSwapRevertsIfAlreadyPending() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.expectRevert(IntegrityAccount.SwapAlreadyPending.selector);
        account.proposeKernelSwap(address(newKernel));
        vm.stopPrank();
    }

    function test_cancelKernelSwapRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccount.NoSwapPending.selector);
        vm.prank(address(account));
        account.cancelKernelSwap();
    }

    function test_executeKernelSwapRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccount.NoSwapPending.selector);
        vm.prank(address(account));
        account.executeKernelSwap(address(0xBEEF));
    }

    function test_executeKernelSwapRevertsOnParameterMismatch() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        address otherKernel = address(0xBEEF);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.SwapMismatch.selector, address(newKernel), otherKernel
            )
        );
        account.executeKernelSwap(otherKernel);
        vm.stopPrank();
    }

    function test_executeKernelSwapRevertsBeforeTimelockElapses() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        (, uint256 readyAt) = account.pendingKernelSwap();
        vm.warp(readyAt - 1);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.TimelockNotElapsed.selector, readyAt, readyAt - 1)
        );
        account.executeKernelSwap(address(newKernel));
        vm.stopPrank();
    }

    function test_cancelKernelSwapThenReproposeSucceeds() public {
        IntegrityKernel firstProposed = _deployKernel(MIN_EFFECTIVE_SCORE);
        IntegrityKernel secondProposed = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(firstProposed));
        account.cancelKernelSwap();
        // A second propose immediately after cancel must succeed -- cancel must fully clear the
        // pending slot, not just mark it cancelled.
        account.proposeKernelSwap(address(secondProposed));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // REPUTATION_EPOCH_LENGTH is >= MODULE_ACTION_TIMELOCK (enforced at proposal time as of
        // 2026-08-19's epoch/timelock deployment invariant -- see `_checkEpochCompatibility`),
        // so the currently-installed kernel's genesis-time snapshot is still exactly at the
        // boundary here, not stale. This refresh is kept anyway as defense-in-depth against exact
        // timestamp-boundary timing rather than relied upon to paper over a mismatch (the old
        // 1-day-epoch/3-day-timelock fixture this comment used to describe no longer exists; see
        // `test_deployingMismatchedGenesisPairRevertsAtConstruction` for that scenario now).
        kernel.refreshReputationSnapshot();
        vm.stopPrank();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(secondProposed));
        vm.startPrank(address(account));
        account.executeKernelSwap(address(secondProposed));
        vm.stopPrank();
        assertEq(account.hook(), address(secondProposed), "the cancelled proposal must not be the one that lands");
    }

    function test_kernelSwapSucceedsAfterTimelockElapsesAndInstallsTheNewKernel() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // See test_cancelKernelSwapThenReproposeSucceeds -- kept as defense-in-depth against
        // exact timestamp-boundary timing, not because the epoch is shorter than the timelock
        // (it isn't, as of the epoch/timelock deployment invariant).
        kernel.refreshReputationSnapshot();
        vm.stopPrank();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(newKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));

        assertEq(account.hook(), address(newKernel), "hook() must reflect the new kernel after a completed swap");
        // The pending slot must be cleared, not left with a stale (already-executed) entry.
        (address stalePending, uint256 staleReadyAt) = account.pendingKernelSwap();
        assertEq(stalePending, address(0));
        assertEq(staleReadyAt, 0);

        // The NEW kernel's own snapshot was also taken at ITS construction time, before the warp
        // above -- kept as the same defense-in-depth refresh before it mediates the post-swap
        // execute() call below.
        newKernel.refreshReputationSnapshot();

        // The account must remain fully functional post-swap: an in-budget call through the new
        // kernel still succeeds, proving the swap didn't leave the account permanently unhooked.
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    /// @dev Empirically verifies the mediation asymmetry documented in the contract's top-level
    /// NatSpec, rather than leaving it as an asserted comment: the swap's uninstall half is
    /// wrapped by `withHook` while `_hook` still points at the OLD kernel, so the old kernel's
    /// own `preCheck` genuinely fires and can genuinely block the swap.
    function test_executeKernelSwapUninstallHalfIsMediatedByOldKernel() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);

        // Drop the account below the CURRENTLY INSTALLED (old) kernel's reputation floor after
        // proposing but before executing -- if the uninstall half were unmediated, this would
        // have no effect on the swap at all.
        // Same base score used by test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget --
        // MIN_EFFECTIVE_SCORE - 1 (499) boosted (573) would land ABOVE the 500 floor, so it can't
        // be used here either; 400 boosted (460) genuinely stays under it.
        uint256 belowFloorScore = 400;
        // Boosted, so effectiveScore = belowFloorScore * 1.15 -- must still land under the floor,
        // matching the same boost-aware boundary discipline used elsewhere in this file.
        uint256 boostedScore = (belowFloorScore * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        assertLt(boostedScore, MIN_EFFECTIVE_SCORE, "sanity: the boosted score must still be below the floor");
        reputation.updateScore(address(account), belowFloorScore);
        // This refresh is required to pull the new low score into the cache -- without it,
        // preCheck would still see setUp()'s stale ABOVE_FLOOR_SCORE, and the revert below
        // would never happen. (REPUTATION_EPOCH_LENGTH >= MODULE_ACTION_TIMELOCK now, so the
        // 3-day warp above alone does not exhaust the epoch -- this refresh is about the score
        // value, not staleness.)
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(newKernel));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.ReputationBelowFloor.selector, boostedScore, MIN_EFFECTIVE_SCORE
            )
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));

        // The swap must not have partially applied -- still the old kernel, still pending.
        assertEq(account.hook(), address(kernel), "a reverted swap must leave the old kernel installed");
        (address stillPending, uint256 stillReadyAt) = account.pendingKernelSwap();
        assertEq(stillPending, address(newKernel), "a reverted swap must not silently clear the pending proposal");
        assertGt(stillReadyAt, 0, "a reverted swap must not silently clear the pending proposal");
    }

    /// @dev The install half's own `withHook` sees `hook() == address(0)` (the uninstall half
    /// already cleared it moments earlier in the same call), so it never fires ANY hook -- not
    /// the old kernel, and not the new one either. Proven here by giving the new kernel a
    /// reputation floor the account cannot meet: if the install half were mediated by the new
    /// kernel, this swap would revert with ReputationBelowFloor. It does not.
    function test_executeKernelSwapInstallHalfIsUnmediated() public {
        // An unreachably high floor guarantees the account could never pass this new kernel's
        // own preCheck if it were actually invoked during the swap.
        uint256 unreachableFloor = 1_000_000;
        IntegrityKernel strictKernel = _deployKernel(unreachableFloor);

        vm.prank(address(account));
        account.proposeKernelSwap(address(strictKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Outgoing kernel's snapshot must be fresh to mediate the uninstall half at all -- see
        // test_cancelKernelSwapThenReproposeSucceeds for why.
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(strictKernel));

        // Succeeds despite the new kernel's floor being unreachable -- proving the install half
        // never consults it.
        vm.prank(address(account));
        account.executeKernelSwap(address(strictKernel));
        assertEq(
            account.hook(),
            address(strictKernel),
            "the swap must land even though the new kernel's own floor is unreachable"
        );

        // Only NOW, on a genuine post-swap execute(), does the new kernel's real preCheck run --
        // and it correctly rejects, confirming the earlier success wasn't because the check is
        // broken, only that it wasn't invoked during installation. strictKernel's own snapshot
        // was taken at ITS construction (before the warp above); this refresh is kept as
        // defense-in-depth against exact timestamp-boundary timing so this reverts with the
        // intended ReputationBelowFloor, not SnapshotStale (REPUTATION_EPOCH_LENGTH >=
        // MODULE_ACTION_TIMELOCK now, so the warp alone should not exhaust the epoch either way).
        strictKernel.refreshReputationSnapshot();
        uint256 boostedAboveFloorScore = (ABOVE_FLOOR_SCORE * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.ReputationBelowFloor.selector, boostedAboveFloorScore, unreachableFloor
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    // --- Devil's Advocate review findings (2026-08-17): code-level fixes and their regressions ---

    function test_constructorRevertsOnZeroTimelock() public {
        vm.expectRevert(IntegrityAccount.ZeroTimelock.selector);
        new IntegrityAccount(signer, address(kernel), 0, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK);
    }

    function test_proposeKernelSwapRevertsOnNonConformingKernel() public {
        NonHookModule notAHook = new NonHookModule();
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.NewKernelNotAHookModule.selector, address(notAHook))
        );
        vm.prank(address(account));
        account.proposeKernelSwap(address(notAHook));
    }

    // --- epoch/timelock deployment invariant (2026-08-19 proposal, PRODUCTION_GAPS.md §37) -----

    function test_deployingMismatchedGenesisPairRevertsAtConstruction() public {
        uint256 shortEpoch = MODULE_ACTION_TIMELOCK - 1;
        IntegrityKernel mismatchedKernel = new IntegrityKernel(
            address(this), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, shortEpoch,
            address(0), 0, 0
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.EpochTooShortForTimelock.selector, shortEpoch, MODULE_ACTION_TIMELOCK
            )
        );
        new IntegrityAccount(
            signer, address(mismatchedKernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
    }

    function test_proposeKernelSwapRevertsWhenNewKernelEpochShorterThanTimelock() public {
        uint256 shortEpoch = MODULE_ACTION_TIMELOCK - 1;
        IntegrityKernel mismatchedKernel = new IntegrityKernel(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, shortEpoch,
            address(0), 0, 0
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.EpochTooShortForTimelock.selector, shortEpoch, MODULE_ACTION_TIMELOCK
            )
        );
        vm.prank(address(account));
        account.proposeKernelSwap(address(mismatchedKernel));
    }

    function test_guardianProposeActionRevertsWhenNewKernelEpochShorterThanTimelock() public {
        uint256 shortEpoch = MODULE_ACTION_TIMELOCK - 1;
        IntegrityKernel mismatchedKernel = new IntegrityKernel(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, shortEpoch,
            address(0), 0, 0
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.EpochTooShortForTimelock.selector, shortEpoch, MODULE_ACTION_TIMELOCK
            )
        );
        vm.prank(guardian1);
        account.guardianProposeAction(false, address(mismatchedKernel));
    }

    /// @dev Option B's deliberate fail-open case, as an explicit, asserted test outcome rather
    /// than an accident: a kernel that doesn't implement `epochLengthSeconds()` at all must
    /// still be proposable and swappable -- the invariant simply doesn't apply to it.
    function test_kernelSwapSucceedsForAKernelWithNoEpochConcept() public {
        NonSnapshottingKernel simpleKernel = new NonSnapshottingKernel();
        vm.prank(address(account));
        account.proposeKernelSwap(address(simpleKernel));
        (address pending,) = account.pendingKernelSwap();
        assertEq(
            pending, address(simpleKernel), "propose must succeed for a kernel with no epoch concept -- Option B"
        );

        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Defense-in-depth against exact timestamp-boundary timing, same reasoning as
        // test_cancelKernelSwapThenReproposeSucceeds -- unrelated to this kernel's missing epoch.
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(simpleKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(simpleKernel));
        assertEq(
            account.hook(),
            address(simpleKernel),
            "swap to a non-snapshotting kernel must fully succeed -- Option B fail-open, not a partial state"
        );
    }

    function test_governanceFunctionsRevertForNonSelfNonEntryPointCaller() public {
        address stranger = makeAddr("stranger");
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);

        vm.expectRevert(abi.encodeWithSelector(ERC4337Account.AccountUnauthorized.selector, stranger));
        vm.prank(stranger);
        account.proposeKernelSwap(address(newKernel));

        // Get a real proposal in place (as the account itself) so cancel/execute have something
        // to reject a stranger from touching, not just "nothing pending."
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));

        vm.expectRevert(abi.encodeWithSelector(ERC4337Account.AccountUnauthorized.selector, stranger));
        vm.prank(stranger);
        account.cancelKernelSwap();

        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        vm.expectRevert(abi.encodeWithSelector(ERC4337Account.AccountUnauthorized.selector, stranger));
        vm.prank(stranger);
        account.executeKernelSwap(address(newKernel));
    }

    /// @dev Devil's Advocate area 1/4/5: `proposeKernelSwap`'s `isModuleType` probe can only
    /// reject an address that doesn't even superficially conform to the hook-module interface --
    /// it cannot verify `preCheck`/`postCheck` correctness. A kernel that conforms but reverts
    /// unconditionally in `preCheck` installs cleanly and then permanently bricks the account: no
    /// `execute()` can ever succeed again, AND no rescue swap can succeed either, because the
    /// rescue's own uninstall half must call the broken kernel's `preCheck` first. This is a real,
    /// disclosed, unresolved risk for this experimental slice (see the contract's own top-level
    /// NatSpec and the module-governance proposal doc) -- this test makes it a permanent
    /// regression fixture rather than only a documented claim.
    function test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath() public {
        AlwaysRevertingKernel brokenKernel = new AlwaysRevertingKernel();

        vm.startPrank(address(account));
        account.proposeKernelSwap(address(brokenKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Outgoing kernel's snapshot must be fresh to mediate the uninstall half -- see
        // test_cancelKernelSwapThenReproposeSucceeds for why.
        kernel.refreshReputationSnapshot();
        vm.stopPrank();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(brokenKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(brokenKernel));
        assertEq(
            account.hook(),
            address(brokenKernel),
            "the broken kernel installs cleanly -- the isModuleType probe cannot catch this class"
        );

        // Every subsequent execute() now reverts forever.
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        // And there is no rescue: proposing and waiting out the timelock for a real, healthy
        // replacement kernel still fails, because executeKernelSwap's uninstall half must call
        // the broken kernel's preCheck first.
        IntegrityKernel rescueKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(rescueKernel));
        // This is a genuine second vm.warp call within this test function. An independent
        // adversarial review flagged that a second vm.warp call can silently fail to advance
        // block.timestamp under some Foundry optimizer configurations -- checked directly here,
        // not assumed away: this call's target only needs to be in the future relative to
        // whatever block.timestamp already is, so a no-op second warp would make the assertion
        // below fail with TimelockNotElapsed instead of the expected AlwaysReverts. It doesn't --
        // confirming time genuinely advanced a second time for this specific call pattern (a real
        // state-changing external call sits between the two warps, unlike the flagged repro's
        // back-to-back-warps-with-no-call-between shape).
        vm.warp(block.timestamp + 2 * MODULE_ACTION_TIMELOCK);
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(rescueKernel));
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.executeKernelSwap(address(rescueKernel));
    }

    // --- guardian quorum (2026-08-18 proposal) ------------------------------------------------

    function test_constructorRevertsOnZeroGuardianThreshold() public {
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.InvalidGuardianThreshold.selector, 0, guardianSet.length
            )
        );
        new IntegrityAccount(signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, 0, RESCUE_TIMELOCK);
    }

    function test_constructorRevertsWhenThresholdExceedsGuardianCount() public {
        uint256 tooHigh = guardianSet.length + 1;
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.InvalidGuardianThreshold.selector, tooHigh, guardianSet.length
            )
        );
        new IntegrityAccount(signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, tooHigh, RESCUE_TIMELOCK);
    }

    function test_constructorRevertsOnDuplicateGuardian() public {
        address[] memory dup = new address[](2);
        dup[0] = guardian1;
        dup[1] = guardian1;
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.DuplicateGuardian.selector, guardian1));
        new IntegrityAccount(signer, address(kernel), MODULE_ACTION_TIMELOCK, dup, 1, RESCUE_TIMELOCK);
    }

    function test_constructorRevertsOnZeroAddressGuardian() public {
        address[] memory withZero = new address[](2);
        withZero[0] = guardian1;
        withZero[1] = address(0);
        vm.expectRevert(IntegrityAccount.ZeroGuardian.selector);
        new IntegrityAccount(signer, address(kernel), MODULE_ACTION_TIMELOCK, withZero, 1, RESCUE_TIMELOCK);
    }

    function test_executeKernelSwapRevertsBelowGuardianThreshold() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        vm.stopPrank();

        // Only ONE of the two required guardians approves.
        uint256 nonce = account.kernelSwapNonce();
        vm.prank(guardian1);
        account.approveKernelSwap(nonce, address(newKernel));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.InsufficientGuardianApprovals.selector, 1, GUARDIAN_THRESHOLD
            )
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));
    }

    function test_executeKernelSwapSucceedsAtExactGuardianThreshold() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        vm.stopPrank();

        _approveWithTwoGuardians(account.kernelSwapNonce(), address(newKernel));

        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));
        assertEq(account.hook(), address(newKernel), "exact-threshold approval count must be sufficient");
    }

    function test_approveKernelSwapDoesNotDoubleCountTheSameGuardianUnderTheSameNonce() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        uint256 nonce = account.kernelSwapNonce();

        vm.startPrank(guardian1);
        account.approveKernelSwap(nonce, address(newKernel));
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.GuardianAlreadyApproved.selector, guardian1, nonce)
        );
        account.approveKernelSwap(nonce, address(newKernel));
        vm.stopPrank();

        assertEq(account.kernelSwapApprovalCount(nonce), 1, "a repeated approval from the same guardian must not count twice");
    }

    function test_approveKernelSwapRevertsForNonGuardian() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));

        address stranger = makeAddr("stranger");
        uint256 nonce = account.kernelSwapNonce();
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, stranger));
        vm.prank(stranger);
        account.approveKernelSwap(nonce, address(newKernel));
    }

    function test_approveKernelSwapRevertsOnWrongNonce() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        uint256 realNonce = account.kernelSwapNonce();
        uint256 wrongNonce = realNonce + 1;

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianNonceMismatch.selector, realNonce, wrongNonce
            )
        );
        vm.prank(guardian1);
        account.approveKernelSwap(wrongNonce, address(newKernel));
    }

    /// @dev Falsification #1 from the proposal doc's "the reversal, stated plainly" section,
    /// proven empirically rather than left as an asserted comment (matching the discipline
    /// `test_executeKernelSwapInstallHalfIsUnmediated` already uses for the swap's own asymmetry):
    /// `approveKernelSwap` is a state-changing entry point no hook mediates. Install a kernel that
    /// reverts unconditionally in `preCheck` -- if `approveKernelSwap` were routed through
    /// `execute()`/`withHook`, this call would revert `AlwaysReverts`. It does not.
    function test_approveKernelSwapIsNotMediatedByTheInstalledHook() public {
        AlwaysRevertingKernel brokenKernel = new AlwaysRevertingKernel();
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(brokenKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        vm.stopPrank();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(brokenKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(brokenKernel));
        assertEq(account.hook(), address(brokenKernel), "sanity: the broken kernel must actually be installed");

        // Propose a rescue swap. The broken kernel's own preCheck now reverts unconditionally, so
        // if approveKernelSwap ran through the hook, EVERY approval below would revert too.
        IntegrityKernel rescueKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(rescueKernel));
        uint256 nonce = account.kernelSwapNonce();

        vm.prank(guardian1);
        account.approveKernelSwap(nonce, address(rescueKernel));
        vm.prank(guardian2);
        account.approveKernelSwap(nonce, address(rescueKernel));

        assertEq(account.kernelSwapApprovalCount(nonce), 2, "approvals must succeed even with a permanently-reverting hook installed");
    }

    /// @dev An approval cast against a proposal that was then cancelled must not carry over if the
    /// SAME `newKernel` address is proposed again under a fresh nonce -- the nonce, not the
    /// (newKernel) pair, is what scopes an approval.
    function test_approvalFromACancelledProposalDoesNotCountTowardARepropose() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        uint256 firstNonce = account.kernelSwapNonce();
        vm.stopPrank();

        vm.prank(guardian1);
        account.approveKernelSwap(firstNonce, address(newKernel));
        assertEq(account.kernelSwapApprovalCount(firstNonce), 1);

        vm.startPrank(address(account));
        account.cancelKernelSwap();
        // Re-propose the SAME newKernel address -- gets a fresh nonce.
        account.proposeKernelSwap(address(newKernel));
        uint256 secondNonce = account.kernelSwapNonce();
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        vm.stopPrank();

        assertGt(secondNonce, firstNonce, "sanity: repropose must get a new nonce");
        assertEq(account.kernelSwapApprovalCount(secondNonce), 0, "the earlier nonce's approval must not carry over");

        // guardian1's earlier approval, replayed under the OLD nonce, must still be rejected --
        // and only ONE net-new guardian (guardian2) has approved the new nonce, which is below
        // threshold, proving the old approval genuinely did not silently count.
        vm.prank(guardian2);
        account.approveKernelSwap(secondNonce, address(newKernel));
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.InsufficientGuardianApprovals.selector, 1, GUARDIAN_THRESHOLD
            )
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));
    }

    /// @dev The pre-existing single-signer preconditions (pending-exists, address-match, timelock)
    /// must still independently gate execution ALONGSIDE the new quorum check, not be superseded
    /// by it -- proven by satisfying full quorum up front and confirming each of those checks
    /// still fires first, exactly as before this slice.
    function test_existingSingleSignerPreconditionsStillGateAlongsideQuorum() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.stopPrank();
        // Full quorum gathered immediately -- well before the timelock elapses.
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(newKernel));

        (, uint256 readyAt) = account.pendingKernelSwap();
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.TimelockNotElapsed.selector, readyAt, block.timestamp)
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));

        vm.warp(readyAt);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.SwapMismatch.selector, address(newKernel), address(0xBEEF)
            )
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(0xBEEF));
    }

    /// @dev The proposal doc's adversarial-pass requirement, item 3: "interaction with the
    /// existing reentrancy windows (does a reentrant call during onInstall/onUninstall see stale
    /// or fresh approval state?)". Answer, proven rather than assumed: `pendingKernelSwap` is
    /// ALREADY cleared (empty) at both callback points -- `delete pendingKernelSwap` runs before
    /// either half -- but `kernelSwapApprovalCount` for the just-consumed nonce is NOT cleared,
    /// so a reentrant reader sees the full, fresh approval count alongside an empty pending slot.
    /// Separately proves this window cannot be used to MUTATE quorum state: `proposeKernelSwap`
    /// reverts (msg.sender inside the callback is the kernel contract itself, neither `self` nor
    /// the entry point) and `approveKernelSwap` reverts (that same address is not a guardian).
    /// Exercises BOTH halves with the same fixture instance -- it plays "new kernel" (onInstall
    /// fires) in the first swap, then "old kernel" (onUninstall fires) in a second swap out of
    /// it, so both callback sites are covered by one adversarial contract.
    function test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending() public {
        ReentrancyObserverKernel observerKernel = new ReentrancyObserverKernel(account);

        // Swap 1: setUp()'s real kernel -> observerKernel. Its onInstall fires during this swap.
        vm.prank(address(account));
        account.proposeKernelSwap(address(observerKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Outgoing kernel's snapshot must be fresh -- see test_cancelKernelSwapThenReproposeSucceeds.
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(observerKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(observerKernel));
        assertEq(account.hook(), address(observerKernel), "sanity: observer kernel must actually be installed");

        assertTrue(observerKernel.onInstallCalled(), "onInstall must have fired during swap 1");
        assertEq(
            observerKernel.observedPendingKernelAtInstall(),
            address(0),
            "pendingKernelSwap must already be cleared by the time onInstall fires"
        );
        assertEq(observerKernel.observedPendingReadyAtAtInstall(), 0);
        assertEq(
            observerKernel.observedApprovalCountAtInstall(),
            GUARDIAN_THRESHOLD,
            "kernelSwapApprovalCount is NOT cleared alongside pendingKernelSwap -- a reentrant reader sees it fresh"
        );
        assertTrue(
            observerKernel.reentrantProposeRevertedAtInstall(),
            "a reentrant proposeKernelSwap from inside onInstall must fail closed (caller is the kernel, not self/entryPoint)"
        );
        assertTrue(
            observerKernel.reentrantApproveRevertedAtInstall(),
            "a reentrant approveKernelSwap from inside onInstall must fail closed (caller is not a registered guardian)"
        );

        // Swap 2: observerKernel -> a plain new kernel. Its onUninstall fires during this swap.
        // observerKernel's own preCheck is an unconditional no-op (no reputation check), so no
        // refresh is needed before this swap's uninstall half mediates it.
        IntegrityKernel finalKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(finalKernel));
        // Warp to the pending swap's exact readyAt rather than `block.timestamp + X` a second
        // time in this function -- a known via_ir optimizer quirk documented elsewhere in this
        // file can silently no-op a repeated `block.timestamp`-relative warp.
        (, uint256 secondReadyAt) = account.pendingKernelSwap();
        vm.warp(secondReadyAt);
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(finalKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(finalKernel));
        assertEq(account.hook(), address(finalKernel), "sanity: final kernel must actually be installed");

        assertTrue(observerKernel.onUninstallCalled(), "onUninstall must have fired during swap 2");
        assertEq(
            observerKernel.observedPendingKernelAtUninstall(),
            address(0),
            "pendingKernelSwap must already be cleared by the time onUninstall fires, same as the install half"
        );
        assertEq(
            observerKernel.observedApprovalCountAtUninstall(),
            GUARDIAN_THRESHOLD,
            "kernelSwapApprovalCount for swap 2's nonce is likewise visible fresh, not stale/zeroed, during onUninstall"
        );
    }

    /// @dev The genuinely new failure mode this slice introduces (proposal doc, "What this does
    /// NOT prove"): guardian quorum-gathering takes real elapsed time, which can itself exhaust
    /// the outgoing kernel's `epochLengthSeconds` even when the snapshot was fresh at the moment
    /// approval-gathering began. This must NOT be conflated with the pre-existing
    /// timelock-vs-epoch collision every other success-path test already routes around with a
    /// single upfront refresh: the staleness here is manufactured strictly BETWEEN two guardian
    /// approvals, after a refresh, so `_approveWithTwoGuardians` (which casts both approvals
    /// back-to-back with no warp between) cannot be reused for this test.
    function test_quorumGatheringCanStaleTheSnapshotBetweenApprovals() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Fresh snapshot at the moment approval-gathering begins.
        kernel.refreshReputationSnapshot();
        uint256 nonce = account.kernelSwapNonce();

        vm.prank(guardian1);
        account.approveKernelSwap(nonce, address(newKernel));

        // Elapsed time between the two guardians' approvals alone exhausts the epoch -- the
        // timelock has already elapsed and is not warped again here.
        vm.warp(block.timestamp + REPUTATION_EPOCH_LENGTH + 1);

        vm.prank(guardian2);
        account.approveKernelSwap(nonce, address(newKernel));
        assertEq(account.kernelSwapApprovalCount(nonce), GUARDIAN_THRESHOLD, "sanity: full quorum was reached");

        // Full quorum, timelock long elapsed -- yet execute still reverts, and for staleness, not
        // InsufficientGuardianApprovals: the failure genuinely moved from "not enough guardians"
        // to "reputation snapshot too old" once quorum-gathering itself consumed the epoch.
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.SnapshotStale.selector,
                block.timestamp - (REPUTATION_EPOCH_LENGTH + 1),
                block.timestamp,
                REPUTATION_EPOCH_LENGTH
            )
        );
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));

        // Recoverable: anyone may permissionlessly refresh, then the identical call succeeds.
        kernel.refreshReputationSnapshot();
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));
        assertEq(account.hook(), address(newKernel), "swap must land once the snapshot is refreshed post-quorum");
    }

    // --- guardian emergency action: closes unilateral swap DENIAL (2026-08-18 proposal) -------

    /// @dev Gathers unanimous (3-of-3) guardian approval for the currently pending guardian
    /// action. Distinct from `_approveWithTwoGuardians` -- that helper is for `executeKernelSwap`'s
    /// M-of-N execution quorum; this is for `executeGuardianAction`'s deliberately stricter N-of-N.
    function _approveGuardianActionUnanimously(uint256 nonce) internal {
        vm.prank(guardian1);
        account.approveGuardianAction(nonce);
        vm.prank(guardian2);
        account.approveGuardianAction(nonce);
        vm.prank(guardian3);
        account.approveGuardianAction(nonce);
    }

    function test_guardianProposeActionRevertsForNonGuardian() public {
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, address(this)));
        account.guardianProposeAction(true, address(0));
    }

    function test_guardianProposeActionForcePropose_RevertsOnZeroKernel() public {
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.ZeroKernel.selector);
        account.guardianProposeAction(false, address(0));
    }

    function test_guardianProposeActionForcePropose_RevertsOnNonHookModule() public {
        NonHookModule notAHook = new NonHookModule();
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.NewKernelNotAHookModule.selector, address(notAHook)
            )
        );
        account.guardianProposeAction(false, address(notAHook));
    }

    function test_guardianProposeActionRevertsIfAlreadyPending() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        vm.prank(guardian2);
        vm.expectRevert(IntegrityAccount.GuardianActionAlreadyPending.selector);
        account.guardianProposeAction(true, address(0));
    }

    function test_approveGuardianActionRevertsForNonGuardian() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        uint256 nonce = account.guardianActionNonce();
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, address(this)));
        account.approveGuardianAction(nonce);
    }

    function test_approveGuardianActionRevertsWhenNothingPending() public {
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.NoGuardianActionPending.selector);
        account.approveGuardianAction(0);
    }

    function test_approveGuardianActionRevertsOnWrongNonce() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        uint256 currentNonce = account.guardianActionNonce();
        uint256 wrongNonce = currentNonce + 1;
        vm.prank(guardian2);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianActionNonceMismatch.selector, currentNonce, wrongNonce
            )
        );
        account.approveGuardianAction(wrongNonce);
    }

    function test_approveGuardianActionRevertsOnDoubleApproval() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        uint256 nonce = account.guardianActionNonce();
        vm.prank(guardian1);
        account.approveGuardianAction(nonce);
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianActionAlreadyApproved.selector, guardian1, nonce
            )
        );
        account.approveGuardianAction(nonce);
    }

    function test_executeGuardianActionRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccount.NoGuardianActionPending.selector);
        account.executeGuardianAction();
    }

    /// @dev Mutation target: this is the security-relevant guard closing the gap between
    /// `guardianThreshold` (M-of-N, sufficient for ordinary execution quorum) and the strictly
    /// higher N-of-N bar this emergency path requires. Only 2 of 3 guardians approve -- enough
    /// for `executeKernelSwap`'s own quorum, deliberately NOT enough here.
    function test_executeGuardianActionRevertsBelowUnanimity() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        uint256 nonce = account.guardianActionNonce();
        vm.prank(guardian1);
        account.approveGuardianAction(nonce);
        vm.prank(guardian2);
        account.approveGuardianAction(nonce);

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.InsufficientGuardianActionApprovals.selector, 2, 3)
        );
        account.executeGuardianAction();
    }

    /// @notice The narrower denial case: signer proposes a swap, then goes dark (never cancels).
    /// Guardians force-cancel it, unanimously, with zero signer involvement.
    function test_guardianForceCancel_StuckSignerProposal() public {
        IntegrityKernel unwantedKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(unwantedKernel));
        (, uint256 readyAtBefore) = account.pendingKernelSwap();
        assertGt(readyAtBefore, 0, "sanity: a swap is genuinely pending before the rescue");

        vm.prank(guardian2);
        account.guardianProposeAction(true, address(0));
        uint256 nonce = account.guardianActionNonce();
        _approveGuardianActionUnanimously(nonce);

        account.executeGuardianAction();

        (, uint256 readyAtAfter) = account.pendingKernelSwap();
        assertEq(readyAtAfter, 0, "force-cancel must clear the stuck proposal");
        assertEq(account.hook(), address(kernel), "force-cancel must not itself touch the installed kernel");
    }

    /// @notice The wider denial case: signer never proposes anything at all (key lost/absent).
    /// Guardians force-propose a swap themselves, with zero signer involvement anywhere in the
    /// flow -- including the final `executeKernelSwap` call, which a guardian (not the signer)
    /// submits, per the executeKernelSwap access-control widening this proposal also required.
    function test_guardianForcePropose_UnresponsiveSigner_FullRescueWithNoSignerInvolvement() public {
        IntegrityKernel rescueKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        (, uint256 readyAtBefore) = account.pendingKernelSwap();
        assertEq(readyAtBefore, 0, "sanity: nothing pending before the rescue -- the harder denial case");

        vm.prank(guardian1);
        account.guardianProposeAction(false, address(rescueKernel));
        uint256 actionNonce = account.guardianActionNonce();
        _approveGuardianActionUnanimously(actionNonce);

        uint256 kernelSwapNonceBefore = account.kernelSwapNonce();
        vm.prank(guardian3);
        account.executeGuardianAction();

        assertEq(
            account.kernelSwapNonce(),
            kernelSwapNonceBefore + 1,
            "a force-proposed swap must bump kernelSwapNonce exactly as proposeKernelSwap does"
        );
        (address pendingKernelAddr, uint256 readyAt) = account.pendingKernelSwap();
        assertEq(pendingKernelAddr, address(rescueKernel), "force-propose must target the guardian-agreed kernel");
        assertGt(readyAt, block.timestamp, "force-propose must still respect the normal timelock, not bypass it");

        // The force-proposed swap is now indistinguishable from a signer-proposed one: it needs
        // the ordinary M-of-N execution quorum via the EXISTING approveKernelSwap mechanism, and
        // is subject to the same timelock -- no shortcut for either.
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(rescueKernel));

        // The signer is never invoked anywhere in this test -- a guardian submits the final call.
        vm.prank(guardian2);
        account.executeKernelSwap(address(rescueKernel));

        assertEq(account.hook(), address(rescueKernel), "the rescued account must end up on the guardian-chosen kernel");
    }

    /// @notice A force-propose is rejected while a (possibly unrelated) swap is already pending --
    /// guardians must force-cancel first, a separate unanimous action, rather than atomically
    /// overriding an in-flight proposal.
    function test_guardianForcePropose_RevertsIfSwapAlreadyPending() public {
        IntegrityKernel signerProposed = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(signerProposed));

        IntegrityKernel guardianWanted = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(guardian1);
        account.guardianProposeAction(false, address(guardianWanted));
        uint256 nonce = account.guardianActionNonce();
        _approveGuardianActionUnanimously(nonce);

        vm.expectRevert(IntegrityAccount.SwapAlreadyPending.selector);
        account.executeGuardianAction();
    }

    /// @notice A force-cancel is rejected when nothing is pending -- there is nothing to cancel,
    /// guardians should force-propose instead.
    function test_guardianForceCancel_RevertsWhenNoSwapPending() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        uint256 nonce = account.guardianActionNonce();
        _approveGuardianActionUnanimously(nonce);

        vm.expectRevert(IntegrityAccount.NoSwapPending.selector);
        account.executeGuardianAction();
    }

    /// @notice `executeKernelSwap`'s widened caller set (entry point, self, OR any guardian) does
    /// NOT lower what is required to succeed -- a guardian submitting the call before quorum is
    /// reached still hits the exact same `InsufficientGuardianApprovals` guard a signer would.
    function test_executeKernelSwapCallableByGuardian_StillEnforcesExecutionQuorum() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        // Zero execution approvals gathered -- a guardian submitting the call is still bound by
        // the same quorum check any other caller would be.
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.InsufficientGuardianApprovals.selector, 0, GUARDIAN_THRESHOLD)
        );
        vm.prank(guardian1);
        account.executeKernelSwap(address(newKernel));
    }

    /// @notice A non-guardian, non-signer, non-entry-point address may not submit
    /// `executeKernelSwap` even once every substantive precondition (including quorum) is
    /// satisfied -- the widened caller set is exactly {entry point, self, guardians}, not "anyone."
    function test_executeKernelSwapRevertsForUnrelatedCaller_EvenAtFullQuorum() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(newKernel));

        address stranger = makeAddr("stranger");
        vm.expectRevert(abi.encodeWithSelector(ERC4337Account.AccountUnauthorized.selector, stranger));
        vm.prank(stranger);
        account.executeKernelSwap(address(newKernel));
    }

    // --- guardian-set rotation (2026-08-18 proposal) -------------------------------------------

    /// @dev Gathers unanimous approval from the CURRENT 3-guardian set for the pending rotation.
    function _approveGuardianRotationUnanimously(uint256 nonce) internal {
        vm.prank(guardian1);
        account.approveGuardianRotation(nonce);
        vm.prank(guardian2);
        account.approveGuardianRotation(nonce);
        vm.prank(guardian3);
        account.approveGuardianRotation(nonce);
    }

    function test_proposeGuardianRotationRevertsForNonGuardian() public {
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, address(this)));
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
    }

    function test_proposeGuardianRotationAddition_RevertsOnZeroAddress() public {
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.ZeroGuardian.selector);
        account.proposeGuardianRotation(true, address(0));
    }

    function test_proposeGuardianRotationAddition_RevertsIfAlreadyAGuardian() public {
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.DuplicateGuardian.selector, guardian2)
        );
        account.proposeGuardianRotation(true, guardian2);
    }

    function test_proposeGuardianRotationRemoval_RevertsIfNotAGuardian() public {
        address notAGuardian = makeAddr("notAGuardian");
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.GuardianNotFound.selector, notAGuardian)
        );
        account.proposeGuardianRotation(false, notAGuardian);
    }

    /// @dev With 3 guardians and GUARDIAN_THRESHOLD = 2, removing one guardian leaves 2 -- exactly
    /// at the threshold, still valid. A second removal would drop to 1, below threshold, and must
    /// revert. This test proves the boundary, not just the interior case.
    function test_proposeGuardianRotationRemoval_RevertsWhenItWouldDropBelowThreshold() public {
        // First removal: 3 -> 2, exactly at GUARDIAN_THRESHOLD. Must succeed.
        vm.prank(guardian1);
        account.proposeGuardianRotation(false, guardian3);
        _approveGuardianRotationUnanimously(account.guardianRotationNonce());
        account.executeGuardianRotation();
        assertEq(account.guardians().length, 2, "sanity: down to exactly threshold after first removal");

        // Second removal: 2 -> 1, below GUARDIAN_THRESHOLD (2). Must revert.
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianRemovalWouldBreakThreshold.selector, 1, GUARDIAN_THRESHOLD
            )
        );
        account.proposeGuardianRotation(false, guardian2);
    }

    function test_proposeGuardianRotationRevertsIfAlreadyPending() public {
        vm.prank(guardian1);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
        vm.prank(guardian2);
        vm.expectRevert(IntegrityAccount.GuardianRotationAlreadyPending.selector);
        account.proposeGuardianRotation(true, makeAddr("anotherNewGuardian"));
    }

    function test_approveGuardianRotationRevertsOnWrongNonce() public {
        vm.prank(guardian1);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
        uint256 currentNonce = account.guardianRotationNonce();
        uint256 wrongNonce = currentNonce + 1;
        vm.prank(guardian2);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianRotationNonceMismatch.selector, currentNonce, wrongNonce
            )
        );
        account.approveGuardianRotation(wrongNonce);
    }

    function test_approveGuardianRotationRevertsOnDoubleApproval() public {
        vm.prank(guardian1);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
        uint256 nonce = account.guardianRotationNonce();
        vm.prank(guardian1);
        account.approveGuardianRotation(nonce);
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.GuardianRotationAlreadyApproved.selector, guardian1, nonce
            )
        );
        account.approveGuardianRotation(nonce);
    }

    /// @dev Mutation target: only 2 of 3 guardians approve -- enough for ordinary
    /// `guardianThreshold` execution quorum, deliberately NOT enough for rotation's unanimous bar.
    function test_executeGuardianRotationRevertsBelowUnanimity() public {
        vm.prank(guardian1);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
        uint256 nonce = account.guardianRotationNonce();
        vm.prank(guardian1);
        account.approveGuardianRotation(nonce);
        vm.prank(guardian2);
        account.approveGuardianRotation(nonce);

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.InsufficientGuardianRotationApprovals.selector, 2, 3
            )
        );
        account.executeGuardianRotation();
    }

    function test_executeGuardianRotationRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccount.NoGuardianRotationPending.selector);
        account.executeGuardianRotation();
    }

    /// @notice Full addition end-to-end: the new guardian is unusable until the rotation
    /// executes, and immediately usable (can approve a real kernel-swap execution) afterward.
    function test_guardianAddition_FullLifecycle_NewGuardianCanActAfterward() public {
        address newGuardianAddr = makeAddr("newGuardian");

        vm.prank(guardian1);
        account.proposeGuardianRotation(true, newGuardianAddr);
        uint256 nonce = account.guardianRotationNonce();
        _approveGuardianRotationUnanimously(nonce);
        account.executeGuardianRotation();

        assertEq(account.guardians().length, 4, "guardian count must grow by one");
        address[] memory current = account.guardians();
        bool found;
        for (uint256 i = 0; i < current.length; i++) {
            if (current[i] == newGuardianAddr) found = true;
        }
        assertTrue(found, "the newly-added address must appear in guardians()");

        // The new guardian can immediately participate in an ordinary kernel-swap quorum.
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        uint256 swapNonce = account.kernelSwapNonce();
        vm.prank(newGuardianAddr);
        account.approveKernelSwap(swapNonce, address(newKernel));
        vm.prank(guardian1);
        account.approveKernelSwap(swapNonce, address(newKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(newKernel));
        assertEq(account.hook(), address(newKernel), "the new guardian's approval must count toward real quorum");
    }

    /// @notice Full removal end-to-end: the removed guardian can no longer approve anything,
    /// including a rotation attempting to reinstate them.
    function test_guardianRemoval_FullLifecycle_RemovedGuardianCanNoLongerAct() public {
        vm.prank(guardian1);
        account.proposeGuardianRotation(false, guardian3);
        uint256 nonce = account.guardianRotationNonce();
        _approveGuardianRotationUnanimously(nonce);
        account.executeGuardianRotation();

        assertEq(account.guardians().length, 2, "guardian count must shrink by one");

        vm.prank(guardian3);
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, guardian3));
        account.approveKernelSwap(0, address(0));

        vm.prank(guardian3);
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, guardian3));
        account.proposeGuardianRotation(true, guardian3);
    }

    /// @notice The liveness bug found while writing rotation tests: guardians unanimously agree
    /// to force-cancel a stuck swap, but the signer independently cancels it first (a normal race,
    /// not an attack) -- executeGuardianAction can no longer succeed (NoSwapPending), and without
    /// cancelPendingGuardianAction there would be no way to clear the now-permanently-stuck
    /// pendingGuardianAction slot, which would otherwise block every future
    /// proposeKernelSwap/guardianProposeAction/proposeGuardianRotation call forever.
    function test_cancelPendingGuardianAction_RecoversFromSignerRaceThatWouldOtherwiseBrickGovernance()
        public
    {
        IntegrityKernel someKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(someKernel));

        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        _approveGuardianActionUnanimously(account.guardianActionNonce());

        // The signer independently cancels the swap the guardians were about to force-cancel --
        // ordinary, good-faith behavior, not malicious.
        vm.prank(address(account));
        account.cancelKernelSwap();

        // The guardian action can no longer execute -- the world moved on.
        vm.expectRevert(IntegrityAccount.NoSwapPending.selector);
        account.executeGuardianAction();

        // Without the fix, pendingGuardianAction would now be permanently stuck, blocking every
        // GUARDIAN-side governance entry point (the signer's own proposeKernelSwap was never
        // gated on guardian-action state, so it stays usable throughout -- only
        // guardianProposeAction/proposeGuardianRotation check pendingGuardianAction.active).
        // Confirm that's genuinely what would happen without the escape hatch.
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.GuardianActionAlreadyPending.selector);
        account.guardianProposeAction(true, address(0));
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.GuardianActionAlreadyPending.selector);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));

        // The fix: anyone can clear the stuck slot, and the guardian-side paths resume working.
        account.cancelPendingGuardianAction();
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        (, uint256 readyAt) = account.pendingKernelSwap();
        assertEq(readyAt, 0, "sanity: nothing pending, this force-cancel proposal is just to prove the path works again");
    }

    /// @notice Rotation cannot be proposed while a kernel swap is pending -- must be force- or
    /// signer-cancelled first, per the "only one governance process in flight" invariant.
    function test_proposeGuardianRotationRevertsWhileKernelSwapPending() public {
        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(newKernel));

        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.SwapAlreadyPending.selector);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
    }

    /// @notice Rotation cannot be proposed while a guardian emergency action is pending, and
    /// symmetrically neither a kernel swap nor a guardian action can be proposed while a rotation
    /// is pending -- the invariant holds in both directions, not just one.
    function test_crossMechanismLock_HoldsInBothDirections() public {
        vm.prank(guardian1);
        account.guardianProposeAction(true, address(0));
        vm.prank(guardian2);
        vm.expectRevert(IntegrityAccount.GuardianActionAlreadyPending.selector);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));
        // Clean up the guardian action so the next part of this test starts from a clean slate --
        // via the dedicated cancel escape hatch, not by relying on executeGuardianAction to revert
        // (a revert would undo any cleanup attempted in the same call).
        account.cancelPendingGuardianAction();

        vm.prank(guardian1);
        account.proposeGuardianRotation(true, makeAddr("newGuardian"));

        IntegrityKernel newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        vm.expectRevert(IntegrityAccount.GuardianRotationInProgress.selector);
        account.proposeKernelSwap(address(newKernel));

        vm.prank(guardian2);
        vm.expectRevert(IntegrityAccount.GuardianRotationInProgress.selector);
        account.guardianProposeAction(true, address(0));
    }

    // --- swap reentrancy guard (2026-08-18 proposal) --------------------------------------------

    /// @dev `_fallback` is unconditionally reachable (no access control, unlike `execute()`) and
    /// the account never installs a fallback handler module, so a reentrant fallback call
    /// reverts EITHER WAY -- `ERC7579MissingFallbackHandler` without the guard,
    /// `ReentrantDuringSwap` with it. The revert SELECTOR, not success/failure, is what proves
    /// the guard actually intercepts the call before `preCheck` runs (closing the self-mediation
    /// risk), rather than merely happening to fail for an unrelated, pre-existing reason.
    function test_reentrantFallbackDuringInstallIsRejected() public {
        ReentrantFallbackKernel reentrantKernel = new ReentrantFallbackKernel(account);

        vm.prank(address(account));
        account.proposeKernelSwap(address(reentrantKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(reentrantKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(reentrantKernel));

        assertEq(
            reentrantKernel.installReentrantRevertSelector(),
            IntegrityAccount.ReentrantDuringSwap.selector,
            "a hostile new kernel's onInstall reentrant attempt must be blocked by the swap-in-progress guard"
        );
    }

    function test_reentrantFallbackDuringUninstallIsRejected() public {
        ReentrantFallbackKernel reentrantKernel = new ReentrantFallbackKernel(account);

        vm.prank(address(account));
        account.proposeKernelSwap(address(reentrantKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(reentrantKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(reentrantKernel));

        // A second swap away from the now-installed reentrant fixture -- its onUninstall fires
        // as the OLD kernel this time.
        IntegrityKernel finalKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(finalKernel));
        // Warp to the pending swap's exact readyAt rather than `block.timestamp + X` a second
        // time in this function -- a known via_ir optimizer quirk documented elsewhere in this
        // file can silently no-op a repeated `block.timestamp`-relative warp.
        (, uint256 secondReadyAt) = account.pendingKernelSwap();
        vm.warp(secondReadyAt);
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(finalKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(finalKernel));

        assertEq(
            reentrantKernel.uninstallReentrantRevertSelector(),
            IntegrityAccount.ReentrantDuringSwap.selector,
            "a hostile old kernel's onUninstall reentrant attempt must be blocked by the swap-in-progress guard"
        );
    }

    // --- guardian emergency funds-recovery sweep (2026-08-18 proposal) -------------------------

    address rescueRecipient = makeAddr("rescueRecipient");

    function _approveRescueSweepUnanimously(uint256 nonce) internal {
        vm.prank(guardian1);
        account.approveGuardianRescueSweep(nonce);
        vm.prank(guardian2);
        account.approveGuardianRescueSweep(nonce);
        vm.prank(guardian3);
        account.approveGuardianRescueSweep(nonce);
    }

    function test_proposeGuardianRescueSweepRevertsForNonGuardian() public {
        vm.expectRevert(abi.encodeWithSelector(IntegrityAccount.NotAGuardian.selector, address(this)));
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
    }

    function test_proposeGuardianRescueSweepRevertsOnZeroRecipient() public {
        vm.prank(guardian1);
        vm.expectRevert(IntegrityAccount.ZeroRescueRecipient.selector);
        account.proposeGuardianRescueSweep(payable(address(0)), 1 ether, false);
    }

    function test_proposeGuardianRescueSweepRevertsIfAlreadyPending() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        vm.prank(guardian2);
        vm.expectRevert(IntegrityAccount.RescueSweepAlreadyPending.selector);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
    }

    function test_approveGuardianRescueSweepRevertsOnWrongNonce() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        uint256 currentNonce = account.rescueSweepNonce();
        uint256 wrongNonce = currentNonce + 1;
        vm.prank(guardian2);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.RescueSweepNonceMismatch.selector, currentNonce, wrongNonce
            )
        );
        account.approveGuardianRescueSweep(wrongNonce);
    }

    function test_approveGuardianRescueSweepRevertsOnDoubleApproval() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        uint256 nonce = account.rescueSweepNonce();
        vm.prank(guardian1);
        account.approveGuardianRescueSweep(nonce);
        vm.prank(guardian1);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.RescueSweepAlreadyApproved.selector, guardian1, nonce
            )
        );
        account.approveGuardianRescueSweep(nonce);
    }

    /// @dev Mutation target: only 2 of 3 guardians approve -- enough for ordinary
    /// `guardianThreshold` execution quorum, deliberately NOT enough for the sweep's unanimous bar.
    function test_executeGuardianRescueSweepRevertsBelowUnanimity() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        uint256 nonce = account.rescueSweepNonce();
        vm.prank(guardian1);
        account.approveGuardianRescueSweep(nonce);
        vm.prank(guardian2);
        account.approveGuardianRescueSweep(nonce);

        vm.warp(block.timestamp + RESCUE_TIMELOCK);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccount.InsufficientRescueSweepApprovals.selector, 2, 3)
        );
        account.executeGuardianRescueSweep();
    }

    function test_executeGuardianRescueSweepRevertsBeforeTimelockElapses() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        uint256 nonce = account.rescueSweepNonce();
        _approveRescueSweepUnanimously(nonce);

        (,,,, uint256 readyAt) = account.pendingRescueSweep();
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.RescueTimelockNotElapsed.selector, readyAt, block.timestamp
            )
        );
        account.executeGuardianRescueSweep();
    }

    function test_executeGuardianRescueSweepRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccount.NoRescueSweepPending.selector);
        account.executeGuardianRescueSweep();
    }

    function test_executeGuardianRescueSweepRevertsWhenPartialAmountExceedsBalance() public {
        uint256 tooMuch = address(account).balance + 1 ether;
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), tooMuch, false);
        uint256 nonce = account.rescueSweepNonce();
        _approveRescueSweepUnanimously(nonce);
        vm.warp(block.timestamp + RESCUE_TIMELOCK);

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccount.RescueSweepAmountExceedsBalance.selector,
                tooMuch,
                address(account).balance
            )
        );
        account.executeGuardianRescueSweep();
    }

    function test_guardianRescueSweep_PartialAmount_Succeeds() public {
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = rescueRecipient.balance;

        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 2 ether, false);
        uint256 nonce = account.rescueSweepNonce();
        _approveRescueSweepUnanimously(nonce);
        vm.warp(block.timestamp + RESCUE_TIMELOCK);
        account.executeGuardianRescueSweep();

        assertEq(address(account).balance, accountBalanceBefore - 2 ether, "exactly the requested amount must leave");
        assertEq(rescueRecipient.balance, recipientBalanceBefore + 2 ether, "the recipient must receive exactly that amount");
        (bool active,,,,) = account.pendingRescueSweep();
        assertFalse(active, "the pending sweep must be cleared after execution");
    }

    function test_guardianRescueSweep_FullBalance_DrainsEverythingRegardlessOfRequestedAmount() public {
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = rescueRecipient.balance;
        assertGt(accountBalanceBefore, 0, "sanity: the account must actually hold funds for this test to mean anything");

        // The `amount` field is irrelevant when sweepFullBalance is true -- proven, not assumed,
        // by passing a value that does not match the real balance.
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 wei, true);
        uint256 nonce = account.rescueSweepNonce();
        _approveRescueSweepUnanimously(nonce);
        vm.warp(block.timestamp + RESCUE_TIMELOCK);
        account.executeGuardianRescueSweep();

        assertEq(address(account).balance, 0, "the account must be fully drained");
        assertEq(
            rescueRecipient.balance, recipientBalanceBefore + accountBalanceBefore, "the recipient must receive the entire prior balance"
        );
    }

    function test_cancelPendingGuardianRescueSweep_AllowsRepropose() public {
        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 1 ether, false);
        account.cancelPendingGuardianRescueSweep();
        (bool active,,,,) = account.pendingRescueSweep();
        assertFalse(active, "cancel must clear the pending sweep");

        address otherRecipient = makeAddr("otherRescueRecipient");
        vm.prank(guardian2);
        account.proposeGuardianRescueSweep(payable(otherRecipient), 1 ether, false);
        (, address payable to,,,) = account.pendingRescueSweep();
        assertEq(to, otherRecipient, "a fresh proposal after cancellation must succeed with a new target");
    }

    /// @notice THE definitive test: a rescue sweep succeeds and recovers funds even when the
    /// currently-installed kernel is permanently broken (reverts unconditionally in `preCheck`) --
    /// the exact scenario `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`
    /// proves has NO recovery path via the normal kernel-swap machinery. This is what "funds
    /// become stuck, not stolen, but irrecoverable" (§29's own framing) no longer means once this
    /// mechanism exists -- the account stays permanently unable to `execute()`, but its funds are
    /// not actually irrecoverable anymore.
    function test_guardianRescueSweep_RecoversFundsFromAPermanentlyBrickedAccount() public {
        AlwaysRevertingKernel brokenKernel = new AlwaysRevertingKernel();
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(brokenKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        kernel.refreshReputationSnapshot();
        vm.stopPrank();
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(brokenKernel));
        vm.prank(address(account));
        account.executeKernelSwap(address(brokenKernel));
        assertEq(account.hook(), address(brokenKernel), "sanity: the broken kernel is genuinely installed");

        // Confirm the account is genuinely bricked -- execute() reverts...
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        // ...and a normal rescue swap cannot save it either (the uninstall half must call the
        // broken preCheck first).
        IntegrityKernel normalRescueAttempt = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.prank(address(account));
        account.proposeKernelSwap(address(normalRescueAttempt));
        (, uint256 normalRescueReadyAt) = account.pendingKernelSwap();
        vm.warp(normalRescueReadyAt);
        _approveWithTwoGuardians(account.kernelSwapNonce(), address(normalRescueAttempt));
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.executeKernelSwap(address(normalRescueAttempt));

        // The rescue sweep, in contrast, never touches the broken kernel at all -- it succeeds.
        uint256 accountBalanceBefore = address(account).balance;
        assertGt(accountBalanceBefore, 0, "sanity: real funds are genuinely stuck in the bricked account");

        vm.prank(guardian1);
        account.proposeGuardianRescueSweep(payable(rescueRecipient), 0, true);
        uint256 sweepNonce = account.rescueSweepNonce();
        _approveRescueSweepUnanimously(sweepNonce);
        vm.warp(block.timestamp + RESCUE_TIMELOCK);
        account.executeGuardianRescueSweep();

        assertEq(address(account).balance, 0, "the funds must be fully recovered despite the account remaining bricked");
        assertEq(rescueRecipient.balance, accountBalanceBefore, "the recipient must receive everything that was stuck");

        // The account itself remains permanently bricked -- this mechanism recovers funds, it
        // does not repair the account.
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    // --- declared multi-asset value conservation (docs/plans/2026-08-24-phase1-declared-asset- -
    // --- conservation-proposal.md) -------------------------------------------------------------
    // Uses the `tokenAccount`/`tokenKernel`/`token` fixture deployed in `setUp` above (see that
    // deployment's own comment for why it lives in setUp rather than lazily per-test).

    function _tokenTransferCalldata(address token_, address to, uint256 amount)
        internal
        pure
        returns (bytes memory)
    {
        bytes memory data = abi.encodeWithSelector(IERC20.transfer.selector, to, amount);
        return abi.encodePacked(token_, uint256(0), data);
    }

    function test_constructorRevertsOnZeroTokenBudgetWithNonZeroTrackedToken() public {
        vm.expectRevert(IntegrityKernel.ZeroTokenBudget.selector);
        new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(token),
            0,
            TOKEN_CUMULATIVE_BUDGET
        );
    }

    function test_zeroTokenBudgetsAreAllowedWhenTrackedTokenIsDisabled() public {
        // The shared fixture's `kernel` already does exactly this (address(0), 0, 0) -- this
        // test pins that construction path as a deliberately supported, not accidental, case.
        assertEq(address(kernel.trackedToken()), address(0));
        assertEq(kernel.tokenPerOpBudgetWei(), 0);
        assertEq(kernel.tokenCumulativeBudgetWei(), 0);
    }

    function test_inBudgetTokenTransferSucceedsAndCommits() public {
        uint256 sendAmount = 4 ether;
        uint256 recipientBefore = token.balanceOf(recipient);

        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, sendAmount));

        assertEq(token.balanceOf(recipient), recipientBefore + sendAmount, "recipient must receive the token transfer");
    }

    function test_overTokenPerOpBudgetCallReverts() public {
        uint256 overBudgetAmount = TOKEN_PER_OP_BUDGET + 1;

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.TokenPerOperationBudgetExceeded.selector, overBudgetAmount, TOKEN_PER_OP_BUDGET
            )
        );
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, overBudgetAmount));
    }

    function test_overTokenCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget() public {
        // 3 x 9 ether = 27 ether > 25 ether cumulative budget, each individually under the
        // 10 ether per-op budget -- exact boundary discipline matching the native-ETH budget's
        // own equivalent test.
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, 9 ether));
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, 9 ether));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.TokenCumulativeBudgetExceeded.selector, 18 ether, 9 ether, TOKEN_CUMULATIVE_BUDGET
            )
        );
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, 9 ether));
    }

    function test_tokenAndNativeBudgetsAreIndependentlyEnforced() public {
        // Above the (shared-fixture-sized) native per-op budget, but the token budget is
        // untouched by a pure-native call -- must revert on the NATIVE check, proving the token
        // check does not somehow mask or substitute for it.
        uint256 overNativeBudget = PER_OP_BUDGET + 1;
        bytes memory nativeCalldata = abi.encodePacked(recipient, overNativeBudget, bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.PerOperationBudgetExceeded.selector, overNativeBudget, PER_OP_BUDGET)
        );
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), nativeCalldata);

        // A within-budget native call still succeeds on this same token-tracking kernel --
        // proves the token check's presence does not itself block ordinary native transfers.
        uint256 inBudgetNative = 0.5 ether;
        uint256 recipientNativeBefore = recipient.balance;
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), abi.encodePacked(recipient, inBudgetNative, bytes("")));
        assertEq(recipient.balance, recipientNativeBefore + inBudgetNative);

        // And an above-token-budget call on the SAME account still correctly reverts on the
        // TOKEN check, independent of the native counters just exercised above.
        uint256 overTokenBudget = TOKEN_PER_OP_BUDGET + 1;
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.TokenPerOperationBudgetExceeded.selector, overTokenBudget, TOKEN_PER_OP_BUDGET
            )
        );
        vm.prank(address(tokenAccount));
        tokenAccount.execute(_singleCallMode(), _tokenTransferCalldata(address(token), recipient, overTokenBudget));
    }

    /// @dev Live regression measurement, not estimated -- the gas checkpoint
    /// `docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md` named as a
    /// precondition before this feature could be considered complete. `preCheck` alone, with the
    /// token check ENABLED, measured with a genuinely COLD token-balance read (the setUp-deployed
    /// `tokenAccount`/`tokenKernel` fixture exists specifically so minting doesn't warm the slot
    /// within the same transaction as this test's own `preCheck` call -- see that fixture's own
    /// comment for why a warm measurement would understate the real, production-representative
    /// cost).
    ///
    /// **Real, disclosed finding, not silently absorbed: this measures OVER the whitepaper's own
    /// Table 4 `preCheck` ceiling (`<=40k`).** Exactly the risk
    /// `docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md`'s own dependency-
    /// inventory section named before any code existed -- value conservation is a hard invariant
    /// (whitepaper §4.7.1) and cannot use the epoch-snapshotting cache that rescued the
    /// reputation/assurance-tier checks from their own, earlier over-budget crossing, so this
    /// slice has no equivalent mitigation available within its own scope. Per that proposal's own
    /// process discipline ("if it doesn't fit... report that finding and stop"), this test is
    /// named and asserted to document the crossing honestly, not to hide it -- matching how
    /// `test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks` handled the earlier,
    /// since-resolved crossing before this one.
    function test_preCheckGasExceedsPaperTable4BudgetWithTrackedTokenLiveRead() public {
        vm.prank(address(tokenAccount));
        uint256 gasBefore = gasleft();
        tokenKernel.preCheck(address(tokenAccount), 0, "");
        uint256 gasUsed = gasBefore - gasleft();

        assertGt(
            gasUsed,
            40_000,
            "this test's OWN name asserts an over-budget finding -- if this assertion now fails, "
            "the crossing may have been resolved (e.g. by a future caching/mitigation slice) and "
            "this test should be replaced with an under-budget assertion, not left stale"
        );
        assertLt(
            gasUsed,
            45_000,
            "regression ceiling -- a further, unexplained rise could mean something other than the "
            "named, understood cost (one cold ERC-20 balanceOf read) is now driving this number"
        );

        // Clean up armed state, matching the equivalent native-only test's own discipline.
        vm.prank(address(tokenAccount));
        tokenKernel.postCheck(abi.encode(address(tokenAccount).balance, 100 ether));
    }
}
