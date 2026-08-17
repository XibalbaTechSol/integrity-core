// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StdStorage, stdStorage} from "forge-std/StdStorage.sol";
import {IntegrityAccountV1Experimental} from "../src/kernel/IntegrityAccountV1Experimental.sol";
import {IntegrityKernelV1Experimental} from "../src/kernel/IntegrityKernelV1Experimental.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
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

/// @dev Adversarial fixture for the constant-drift finding a Devil's Advocate review surfaced:
/// exposes the same `scores`/`ZK_BOOST_BPS`/`BPS_DENOMINATOR` shape as the real
/// `ReputationRegistry`, but with DIFFERENT boost constants, to prove
/// `IntegrityKernelV1Experimental`'s constructor-time cross-check genuinely rejects a mismatch
/// rather than silently trusting its own local mirror.
contract MismatchedBoostRegistry {
    uint256 public constant ZK_BOOST_BPS = 20_000;
    uint256 public constant BPS_DENOMINATOR = 10_000;

    function scores(address) external pure returns (uint256 baseScore, uint256 lastUpdate, uint256 zkBoostExpiry) {
        return (0, 0, 0);
    }
}

/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md),
/// extended with a second reference adapter
/// (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md). NOT the full Phase I kernel.
/// Non-deployable, non-upgradeable, single CALL mode only, two conjunctive conditions (a
/// native-value spend budget and a reputation floor). See both proposal docs for full scope
/// boundaries -- this test file only proves what those documents claim, nothing more.
contract IntegrityAccountV1ExperimentalTest is Test {
    using stdStorage for StdStorage;

    address signer;
    uint256 signerKey;
    address recipient = makeAddr("recipient");

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant ABOVE_FLOOR_SCORE = 800;
    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant REPUTATION_EPOCH_LENGTH = 1 days;

    IntegrityKernelV1Experimental kernel;
    IntegrityAccountV1Experimental account;
    ReputationRegistry reputation;

    function setUp() public {
        (signer, signerKey) = makeAddrAndKey("signer");

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
        kernel = new IntegrityKernelV1Experimental(
            predictedAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH
        );
        account = new IntegrityAccountV1Experimental(signer, address(kernel), MODULE_ACTION_TIMELOCK);
        assertEq(address(account), predictedAccount, "CREATE address prediction must match actual deployment");
        vm.deal(address(account), 10 ether);
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
                IntegrityKernelV1Experimental.PerOperationBudgetExceeded.selector, overBudgetAmount, PER_OP_BUDGET
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
                IntegrityKernelV1Experimental.CumulativeBudgetExceeded.selector,
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
                IntegrityAccountV1Experimental.UnsupportedExecutionMode.selector,
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
                IntegrityAccountV1Experimental.UnsupportedExecutionMode.selector,
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
                IntegrityAccountV1Experimental.UnsupportedExecutionMode.selector,
                ERC7579Utils.CALLTYPE_SINGLE,
                ERC7579Utils.EXECTYPE_TRY
            )
        );
        vm.prank(address(account));
        account.execute(Mode.unwrap(tryMode), "");
    }

    function test_moduleInstallIsUnconditionallyDisabled() public {
        vm.expectRevert(IntegrityAccountV1Experimental.ModuleMutationDisabled.selector);
        vm.prank(address(account));
        account.installModule(4, address(0xBEEF), "");
    }

    function test_moduleUninstallIsUnconditionallyDisabled() public {
        // Even an attempt to uninstall the ALREADY-installed real kernel must be rejected --
        // this is what makes the kernel binding permanent, not just "nobody happens to call it".
        vm.expectRevert(IntegrityAccountV1Experimental.ModuleMutationDisabled.selector);
        vm.prank(address(account));
        account.uninstallModule(4, address(kernel), "");
    }

    // --- (d): the hook frame's armed guard actually does its job ------------------------------

    function test_postCheckCannotBeCalledDirectlyWithoutAPrecedingPreCheck() public {
        vm.expectRevert(IntegrityKernelV1Experimental.NotArmed.selector);
        vm.prank(address(account));
        kernel.postCheck(abi.encode(address(account).balance));
    }

    function test_preCheckAndPostCheckRejectCallersOtherThanTheBoundAccount() public {
        address stranger = makeAddr("stranger");
        vm.expectRevert(abi.encodeWithSelector(IntegrityKernelV1Experimental.Unauthorized.selector, stranger));
        vm.prank(stranger);
        kernel.preCheck(stranger, 0, "");

        vm.expectRevert(abi.encodeWithSelector(IntegrityKernelV1Experimental.Unauthorized.selector, stranger));
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
        vm.expectRevert(IntegrityKernelV1Experimental.AlreadyArmed.selector);
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
                IntegrityKernelV1Experimental.ReputationBelowFloor.selector, boostedScore, MIN_EFFECTIVE_SCORE
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
                IntegrityKernelV1Experimental.PerOperationBudgetExceeded.selector, overBudgetAmount, PER_OP_BUDGET
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
            abi.encodeWithSelector(IntegrityKernelV1Experimental.AssuranceTierNotMet.selector, address(account))
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
            abi.encodeWithSelector(IntegrityKernelV1Experimental.AssuranceTierNotMet.selector, address(account))
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
        kernel.postCheck(abi.encode(address(account).balance));
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
                IntegrityKernelV1Experimental.SnapshotStale.selector, 1, block.timestamp, REPUTATION_EPOCH_LENGTH
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
        vm.expectRevert(IntegrityKernelV1Experimental.ZeroEpochLength.selector);
        new IntegrityKernelV1Experimental(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, 0
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
                IntegrityKernelV1Experimental.BoostConstantsMismatch.selector,
                11_500,
                mismatched.ZK_BOOST_BPS(),
                10_000,
                mismatched.BPS_DENOMINATOR()
            )
        );
        new IntegrityKernelV1Experimental(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(mismatched),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH
        );
    }

    function test_constructorRevertsOnEpochLengthTooLong() public {
        uint256 tooLong = kernel.MAX_EPOCH_LENGTH_SECONDS() + 1;
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernelV1Experimental.EpochLengthTooLong.selector, tooLong, kernel.MAX_EPOCH_LENGTH_SECONDS()
            )
        );
        new IntegrityKernelV1Experimental(
            address(account), PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE, tooLong
        );
    }

    function test_refreshReputationSnapshotEmitsEvent() public {
        vm.expectEmit(address(kernel));
        emit IntegrityKernelV1Experimental.ReputationSnapshotRefreshed(
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

    function _deployKernel(uint256 minEffectiveScore) internal returns (IntegrityKernelV1Experimental) {
        return new IntegrityKernelV1Experimental(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            minEffectiveScore,
            REPUTATION_EPOCH_LENGTH
        );
    }

    function test_proposeKernelSwapRevertsOnZeroKernel() public {
        vm.expectRevert(IntegrityAccountV1Experimental.ZeroKernel.selector);
        vm.prank(address(account));
        account.proposeKernelSwap(address(0));
    }

    function test_proposeKernelSwapRevertsIfAlreadyPending() public {
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.expectRevert(IntegrityAccountV1Experimental.SwapAlreadyPending.selector);
        account.proposeKernelSwap(address(newKernel));
        vm.stopPrank();
    }

    function test_cancelKernelSwapRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccountV1Experimental.NoSwapPending.selector);
        vm.prank(address(account));
        account.cancelKernelSwap();
    }

    function test_executeKernelSwapRevertsWhenNothingPending() public {
        vm.expectRevert(IntegrityAccountV1Experimental.NoSwapPending.selector);
        vm.prank(address(account));
        account.executeKernelSwap(address(0xBEEF));
    }

    function test_executeKernelSwapRevertsOnParameterMismatch() public {
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        address otherKernel = address(0xBEEF);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityAccountV1Experimental.SwapMismatch.selector, address(newKernel), otherKernel
            )
        );
        account.executeKernelSwap(otherKernel);
        vm.stopPrank();
    }

    function test_executeKernelSwapRevertsBeforeTimelockElapses() public {
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        (, uint256 readyAt) = account.pendingKernelSwap();
        vm.warp(readyAt - 1);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccountV1Experimental.TimelockNotElapsed.selector, readyAt, readyAt - 1)
        );
        account.executeKernelSwap(address(newKernel));
        vm.stopPrank();
    }

    function test_cancelKernelSwapThenReproposeSucceeds() public {
        IntegrityKernelV1Experimental firstProposed = _deployKernel(MIN_EFFECTIVE_SCORE);
        IntegrityKernelV1Experimental secondProposed = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(firstProposed));
        account.cancelKernelSwap();
        // A second propose immediately after cancel must succeed -- cancel must fully clear the
        // pending slot, not just mark it cancelled.
        account.proposeKernelSwap(address(secondProposed));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // MODULE_ACTION_TIMELOCK (3 days) outlives REPUTATION_EPOCH_LENGTH (1 day), so the
        // currently-installed kernel's snapshot -- which mediates the swap's uninstall half --
        // would otherwise be stale by the time the timelock clears. A real operator would need
        // the same refresh; this is a genuine, disclosed interaction between the two mechanisms,
        // not a test artifact.
        kernel.refreshReputationSnapshot();
        account.executeKernelSwap(address(secondProposed));
        vm.stopPrank();
        assertEq(account.hook(), address(secondProposed), "the cancelled proposal must not be the one that lands");
    }

    function test_kernelSwapSucceedsAfterTimelockElapsesAndInstallsTheNewKernel() public {
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
        vm.startPrank(address(account));
        account.proposeKernelSwap(address(newKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // See test_cancelKernelSwapThenReproposeSucceeds -- the outgoing kernel's snapshot must
        // be refreshed before it can mediate the swap after a timelock longer than its own epoch.
        kernel.refreshReputationSnapshot();
        account.executeKernelSwap(address(newKernel));
        vm.stopPrank();

        assertEq(account.hook(), address(newKernel), "hook() must reflect the new kernel after a completed swap");
        // The pending slot must be cleared, not left with a stale (already-executed) entry.
        (address stalePending, uint256 staleReadyAt) = account.pendingKernelSwap();
        assertEq(stalePending, address(0));
        assertEq(staleReadyAt, 0);

        // The NEW kernel's own snapshot was also taken at ITS construction time, before the warp
        // above -- also needs a refresh before it can mediate the post-swap execute() call below.
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
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
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
        // This refresh does double duty: it pulls the new low score into the cache (without it,
        // preCheck would still see setUp()'s stale ABOVE_FLOOR_SCORE) AND resets the staleness
        // clock the 3-day warp above already exhausted against the 1-day epoch -- so the revert
        // below is genuinely ReputationBelowFloor, not a SnapshotStale masking it.
        kernel.refreshReputationSnapshot();

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernelV1Experimental.ReputationBelowFloor.selector, boostedScore, MIN_EFFECTIVE_SCORE
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
        IntegrityKernelV1Experimental strictKernel = _deployKernel(unreachableFloor);

        vm.prank(address(account));
        account.proposeKernelSwap(address(strictKernel));
        vm.warp(block.timestamp + MODULE_ACTION_TIMELOCK);
        // Outgoing kernel's snapshot must be fresh to mediate the uninstall half at all -- see
        // test_cancelKernelSwapThenReproposeSucceeds for why.
        kernel.refreshReputationSnapshot();

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
        // was taken at ITS construction (before the warp above) and needs its own refresh so this
        // reverts with the intended ReputationBelowFloor, not SnapshotStale.
        strictKernel.refreshReputationSnapshot();
        uint256 boostedAboveFloorScore = (ABOVE_FLOOR_SCORE * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernelV1Experimental.ReputationBelowFloor.selector, boostedAboveFloorScore, unreachableFloor
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);
    }

    // --- Devil's Advocate review findings (2026-08-17): code-level fixes and their regressions ---

    function test_constructorRevertsOnZeroTimelock() public {
        vm.expectRevert(IntegrityAccountV1Experimental.ZeroTimelock.selector);
        new IntegrityAccountV1Experimental(signer, address(kernel), 0);
    }

    function test_proposeKernelSwapRevertsOnNonConformingKernel() public {
        NonHookModule notAHook = new NonHookModule();
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityAccountV1Experimental.NewKernelNotAHookModule.selector, address(notAHook))
        );
        vm.prank(address(account));
        account.proposeKernelSwap(address(notAHook));
    }

    function test_governanceFunctionsRevertForNonSelfNonEntryPointCaller() public {
        address stranger = makeAddr("stranger");
        IntegrityKernelV1Experimental newKernel = _deployKernel(MIN_EFFECTIVE_SCORE);

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
        account.executeKernelSwap(address(brokenKernel));
        vm.stopPrank();
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
        IntegrityKernelV1Experimental rescueKernel = _deployKernel(MIN_EFFECTIVE_SCORE);
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
        vm.expectRevert(AlwaysRevertingKernel.AlwaysReverts.selector);
        vm.prank(address(account));
        account.executeKernelSwap(address(rescueKernel));
    }
}
