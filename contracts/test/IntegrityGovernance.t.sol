// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {IntegrityGovernance} from "../src/oracle/IntegrityGovernance.sol";
import {IntegrityToken} from "../src/oracle/IntegrityToken.sol";

/// @dev Minimal parameterized target the governance timelock executes against — stands in for
/// a real protocol-parameter contract without pulling one into the test.
contract ParamTarget {
    uint256 public value;
    address public lastCaller;

    function setValue(uint256 v) external {
        value = v;
        lastCaller = msg.sender;
    }

    function boom() external pure {
        revert("boom");
    }
}

contract IntegrityGovernanceTest is Test {
    IntegrityGovernance gov;
    IntegrityToken itk;
    ParamTarget param;

    address admin = makeAddr("admin"); // guardian
    address proposer = makeAddr("proposer");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    uint256 constant VOTING_PERIOD = 3 days;
    uint256 constant TIMELOCK = 2 days;
    uint256 constant THRESHOLD = 1_000 ether;
    uint256 constant QUORUM = 5_000 ether;

    function setUp() public {
        itk = new IntegrityToken(admin, 10_000_000 ether);
        gov = new IntegrityGovernance(admin, itk, VOTING_PERIOD, TIMELOCK, THRESHOLD, QUORUM);
        param = new ParamTarget();

        vm.startPrank(admin);
        itk.transfer(proposer, 100_000 ether);
        itk.transfer(alice, 100_000 ether);
        itk.transfer(bob, 100_000 ether);
        vm.stopPrank();

        vm.prank(proposer);
        itk.approve(address(gov), type(uint256).max);
        vm.prank(alice);
        itk.approve(address(gov), type(uint256).max);
        vm.prank(bob);
        itk.approve(address(gov), type(uint256).max);
    }

    // ---- helpers ---------------------------------------------------------------------------

    function _propose() internal returns (uint256 id) {
        bytes memory cd = abi.encodeCall(ParamTarget.setValue, (42));
        vm.prank(proposer);
        id = gov.propose(address(param), 0, cd, "Set param to 42");
    }

    // ---- happy path ------------------------------------------------------------------------

    function test_proposeLocksThresholdAsInitialForVote() public {
        uint256 id = _propose();
        IntegrityGovernance.Proposal memory p = gov.getProposal(id);
        assertEq(p.proposer, proposer);
        assertEq(p.forVotes, THRESHOLD);
        assertEq(p.againstVotes, 0);
        assertEq(itk.balanceOf(address(gov)), THRESHOLD);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Active));
    }

    function test_fullLifecycle_proposeVoteQueueExecute() public {
        uint256 id = _propose();

        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether); // for total now 7000 >= quorum 5000

        // Close the voting window.
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Succeeded));

        gov.queue(id);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Queued));

        // Before ETA: cannot execute.
        vm.expectRevert(IntegrityGovernance.TimelockNotElapsed.selector);
        gov.execute(id);

        vm.warp(block.timestamp + TIMELOCK + 1);
        gov.execute(id);

        assertEq(param.value(), 42);
        assertEq(param.lastCaller(), address(gov));
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Executed));
    }

    function test_withdrawAfterExecuteReturnsLockedItk() public {
        uint256 id = _propose();
        uint256 aliceBefore = itk.balanceOf(alice);

        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        gov.queue(id);
        vm.warp(block.timestamp + TIMELOCK + 1);
        gov.execute(id);

        vm.prank(alice);
        gov.withdraw(id);
        assertEq(itk.balanceOf(alice), aliceBefore);

        vm.prank(proposer);
        gov.withdraw(id);
        assertEq(itk.balanceOf(address(gov)), 0);
    }

    // ---- adversarial: voting -------------------------------------------------------------

    function test_cannotVoteBothSides() public {
        uint256 id = _propose();
        vm.startPrank(alice);
        gov.castVote(id, true, 1_000 ether);
        vm.expectRevert(IntegrityGovernance.VoteSideMismatch.selector);
        gov.castVote(id, false, 1_000 ether);
        vm.stopPrank();
    }

    function test_canTopUpSameSide() public {
        uint256 id = _propose();
        vm.startPrank(alice);
        gov.castVote(id, true, 1_000 ether);
        gov.castVote(id, true, 2_000 ether);
        vm.stopPrank();
        assertEq(gov.getReceipt(id, alice).votes, 3_000 ether);
    }

    function test_cannotVoteZero() public {
        uint256 id = _propose();
        vm.prank(alice);
        vm.expectRevert(IntegrityGovernance.ZeroAmount.selector);
        gov.castVote(id, true, 0);
    }

    function test_cannotVoteAfterWindowCloses() public {
        uint256 id = _propose();
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        vm.prank(alice);
        vm.expectRevert(IntegrityGovernance.NotActive.selector);
        gov.castVote(id, true, 1_000 ether);
    }

    // ---- adversarial: withdrawal locking -------------------------------------------------

    function test_cannotWithdrawWhileActive() public {
        uint256 id = _propose();
        vm.prank(proposer);
        vm.expectRevert(IntegrityGovernance.NotWithdrawable.selector);
        gov.withdraw(id);
    }

    function test_cannotWithdrawWhileQueued() public {
        uint256 id = _propose();
        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        gov.queue(id);
        vm.prank(alice);
        vm.expectRevert(IntegrityGovernance.NotWithdrawable.selector);
        gov.withdraw(id);
    }

    function test_cannotWithdrawTwice() public {
        uint256 id = _propose();
        vm.warp(block.timestamp + VOTING_PERIOD + 1); // defeated (quorum unmet)
        vm.prank(proposer);
        gov.withdraw(id);
        vm.prank(proposer);
        vm.expectRevert(IntegrityGovernance.NothingToWithdraw.selector);
        gov.withdraw(id);
    }

    // ---- adversarial: outcome/state ------------------------------------------------------

    function test_quorumNotMet_isDefeated() public {
        uint256 id = _propose();
        vm.prank(alice);
        gov.castVote(id, true, 1_000 ether); // total 2000 < quorum 5000
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Defeated));
    }

    function test_againstOutweighsFor_isDefeated() public {
        uint256 id = _propose(); // 1000 for
        vm.prank(alice);
        gov.castVote(id, false, 6_000 ether); // 6000 against; total 7000 >= quorum
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Defeated));
    }

    function test_tieIsDefeated() public {
        uint256 id = _propose(); // 1000 for
        vm.prank(alice);
        gov.castVote(id, false, 1_000 ether); // against 1000; but quorum 5000 unmet anyway
        // Bump both sides to exactly tie above quorum.
        vm.prank(bob);
        gov.castVote(id, true, 1_500 ether); // for 2500
        vm.prank(alice);
        gov.castVote(id, false, 1_500 ether); // against 2500; total 5000 == quorum, tie
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Defeated));
    }

    function test_cannotQueueDefeated() public {
        uint256 id = _propose();
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        vm.expectRevert(IntegrityGovernance.NotSucceeded.selector);
        gov.queue(id);
    }

    function test_cannotQueueWhileActive() public {
        uint256 id = _propose();
        vm.expectRevert(IntegrityGovernance.NotSucceeded.selector);
        gov.queue(id);
    }

    function test_cannotExecuteUnqueued() public {
        uint256 id = _propose();
        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        // Succeeded but not queued.
        vm.expectRevert(IntegrityGovernance.NotQueued.selector);
        gov.execute(id);
    }

    function test_expiresAfterGracePeriod() public {
        uint256 id = _propose();
        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        gov.queue(id);
        vm.warp(block.timestamp + TIMELOCK + gov.GRACE_PERIOD() + 1);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Expired));
        vm.expectRevert(IntegrityGovernance.NotQueued.selector);
        gov.execute(id);
        // Voters can reclaim after expiry.
        vm.prank(alice);
        gov.withdraw(id);
    }

    function test_failingActionReverts_andStaysExecutable() public {
        bytes memory cd = abi.encodeCall(ParamTarget.boom, ());
        vm.prank(proposer);
        uint256 id = gov.propose(address(param), 0, cd, "will revert");
        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        gov.queue(id);
        vm.warp(block.timestamp + TIMELOCK + 1);
        vm.expectRevert(IntegrityGovernance.ExecutionFailed.selector);
        gov.execute(id);
        // The revert rolled back p.executed = true, so it remains Queued and re-executable.
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Queued));
    }

    // ---- adversarial: cancellation -------------------------------------------------------

    function test_guardianCanCancel() public {
        uint256 id = _propose();
        vm.prank(admin);
        gov.cancel(id);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Canceled));
        vm.prank(proposer);
        gov.withdraw(id); // reclaim after cancel
    }

    function test_proposerCanCancel() public {
        uint256 id = _propose();
        vm.prank(proposer);
        gov.cancel(id);
        assertEq(uint256(gov.state(id)), uint256(IntegrityGovernance.ProposalState.Canceled));
    }

    function test_strangerCannotCancel() public {
        uint256 id = _propose();
        vm.prank(bob);
        vm.expectRevert(IntegrityGovernance.Unauthorized.selector);
        gov.cancel(id);
    }

    function test_cannotCancelExecuted() public {
        uint256 id = _propose();
        vm.prank(alice);
        gov.castVote(id, true, 6_000 ether);
        vm.warp(block.timestamp + VOTING_PERIOD + 1);
        gov.queue(id);
        vm.warp(block.timestamp + TIMELOCK + 1);
        gov.execute(id);
        vm.prank(admin);
        vm.expectRevert(IntegrityGovernance.InvalidProposal.selector);
        gov.cancel(id);
    }

    // ---- config / misc -------------------------------------------------------------------

    function test_unknownProposalReverts() public {
        vm.expectRevert(IntegrityGovernance.InvalidProposal.selector);
        gov.state(999);
    }

    function test_zeroTargetRejected() public {
        vm.prank(proposer);
        vm.expectRevert(IntegrityGovernance.InvalidProposal.selector);
        gov.propose(address(0), 0, "", "bad");
    }

    function test_badConfigRejected() public {
        vm.expectRevert(IntegrityGovernance.BadConfig.selector);
        new IntegrityGovernance(admin, itk, 0, TIMELOCK, THRESHOLD, QUORUM);
        vm.expectRevert(IntegrityGovernance.BadConfig.selector);
        new IntegrityGovernance(admin, IntegrityToken(address(0)), VOTING_PERIOD, TIMELOCK, THRESHOLD, QUORUM);
    }

    function test_proposalCountIncrements() public {
        assertEq(gov.proposalCount(), 0);
        _propose();
        _propose();
        assertEq(gov.proposalCount(), 2);
    }
}
