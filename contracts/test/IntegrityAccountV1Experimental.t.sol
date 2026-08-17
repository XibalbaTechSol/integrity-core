// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {IntegrityAccountV1Experimental} from "../src/kernel/IntegrityAccountV1Experimental.sol";
import {IntegrityKernelV1Experimental} from "../src/kernel/IntegrityKernelV1Experimental.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {ERC7579Utils, Mode, CallType, ExecType, ModeSelector, ModePayload} from
    "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md),
/// extended with a second reference adapter
/// (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md). NOT the full Phase I kernel.
/// Non-deployable, non-upgradeable, single CALL mode only, two conjunctive conditions (a
/// native-value spend budget and a reputation floor). See both proposal docs for full scope
/// boundaries -- this test file only proves what those documents claim, nothing more.
contract IntegrityAccountV1ExperimentalTest is Test {
    address signer;
    uint256 signerKey;
    address recipient = makeAddr("recipient");

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant ABOVE_FLOOR_SCORE = 800;

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
        kernel = new IntegrityKernelV1Experimental(
            predictedAccount, PER_OP_BUDGET, CUMULATIVE_BUDGET, address(reputation), MIN_EFFECTIVE_SCORE
        );
        account = new IntegrityAccountV1Experimental(signer, address(kernel));
        assertEq(address(account), predictedAccount, "CREATE address prediction must match actual deployment");
        vm.deal(address(account), 10 ether);
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

        assertEq(recipient.balance, recipientBalanceBefore + sendAmount, "recipient must receive the in-budget transfer");
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

        assertEq(address(account).balance, accountBalanceBefore, "account balance must be unchanged after a reverted call");
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
        assertEq(kernel.cumulativeSpentWei(), CUMULATIVE_BUDGET, "test setup must land exactly at the cumulative boundary");

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

        assertEq(recipient.balance, recipientBalanceBeforeFourthCall, "the over-cumulative-budget fourth call must not move any funds");
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

        assertEq(address(account).balance, accountBalanceBefore, "no funds may move when the reentrant attempt fails the whole call");
        assertEq(recipient.balance, recipientBalanceBefore);
        assertFalse(kernel.armed(), "armed must be false again once the whole transaction has unwound");
    }

    // --- reputation-floor adapter (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md)

    function test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget() public {
        reputation.updateScore(address(account), MIN_EFFECTIVE_SCORE - 1);
        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernelV1Experimental.ReputationBelowFloor.selector, MIN_EFFECTIVE_SCORE - 1, MIN_EFFECTIVE_SCORE
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(address(account).balance, accountBalanceBefore, "a below-floor call must move no funds, even a well-within-budget amount");
        assertEq(recipient.balance, recipientBalanceBefore);
    }

    function test_scoreExactlyAtTheFloorSucceeds() public {
        reputation.updateScore(address(account), MIN_EFFECTIVE_SCORE);
        uint256 recipientBalanceBefore = recipient.balance;
        uint256 sendAmount = 0.1 ether;

        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(recipient.balance, recipientBalanceBefore + sendAmount, "a score exactly at the floor must succeed, the boundary itself is not a violation");
    }

    /// @dev Confirms the two checks are genuinely independent -- an above-floor account is
    /// still bound by the budget check, reputation passing does not somehow short-circuit it.
    function test_aboveFloorButOverBudgetCallStillRevertsOnBudget() public {
        // setUp already leaves the account above the reputation floor (ABOVE_FLOOR_SCORE).
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

    // --- gas assertions (whitepaper Table 4: preCheck <= 40k total) ---------------------------

    /// @dev Regression test, not a one-off measurement -- CI catches it if this ever regresses
    /// past the paper's own budget, per this slice's process-discipline commitment.
    function test_preCheckGasIsWithinPaperTable4Budget() public {
        vm.prank(address(account));
        uint256 gasBefore = gasleft();
        kernel.preCheck(address(account), 0, "");
        uint256 gasUsed = gasBefore - gasleft();

        assertLt(gasUsed, 40_000, "preCheck must stay within the paper's Table 4 preCheck budget (<=40k total)");

        // Clean up the armed state this direct call left behind, so it doesn't leak into any
        // test that happens to run after this one in the same suite (Foundry gives each test
        // function a fresh contract deployment via setUp, so this is defensive, not required).
        vm.prank(address(account));
        kernel.postCheck(abi.encode(address(account).balance));
    }
}
