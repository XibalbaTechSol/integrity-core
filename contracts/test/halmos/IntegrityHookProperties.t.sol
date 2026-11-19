// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {
    IntegrityHook,
    IAgentRegistryView,
    IAISRegistryView,
    IStakeVaultView
} from "../../src/wallet/IntegrityHook.sol";
import {IOperationContext} from "../../src/wallet/IOperationContext.sol";
import {MockOperationContext} from "../wallet/mocks/MockOperationContext.sol";
import {MockAccountVerifier} from "../wallet/mocks/MockAccountVerifier.sol";
import {MockGovernedAccount} from "../wallet/mocks/MockGovernedAccount.sol";
import {
    MockAgentRegistry,
    MockAISRegistry,
    MockStakeVault
} from "../wallet/mocks/MockTrustLayer.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract ReenteringTarget {
    MockGovernedAccount public account;
    address public recipient;
    uint256 public nestedAmount;

    constructor(MockGovernedAccount _account, address _recipient) {
        account = _account;
        recipient = _recipient;
    }

    function setNestedAmount(uint256 _nested) external {
        nestedAmount = _nested;
    }

    function attack() external payable {
        bytes memory call = abi.encodePacked(recipient, nestedAmount, bytes(""));
        account.execute(bytes32(0), call);
    }
}

/// @title Formal Verification of IntegrityHook Properties
/// @notice Machine-checked using Halmos. Proves budget containment, multi-asset conjunction,
/// AIS gating, and reentrancy protection.
contract IntegrityHookProperties is Test {
    address public governance;
    address public owner;
    address public recipient;

    MockOperationContext public ctx;
    MockAccountVerifier public verifier;
    MockAgentRegistry public registry;
    MockAISRegistry public ais;
    MockStakeVault public vault;

    IntegrityHook public hook;
    MockGovernedAccount public account;
    IntegrityToken public token;
    ReenteringTarget public reenteringTarget;

    uint256 public constant PER_CALL_CAP = 10 ether;
    uint256 public constant WINDOW_CAP = 100 ether;

    function setUp() public {
        vm.warp(1_800_000_000);
        governance = address(this);
        owner = address(0xAAAA);
        recipient = address(0xC0FFEE);

        ctx = new MockOperationContext();
        verifier = new MockAccountVerifier();
        registry = new MockAgentRegistry();
        ais = new MockAISRegistry();
        vault = new MockStakeVault();

        hook = new IntegrityHook(
            governance,
            IAgentRegistryView(address(registry)),
            IAISRegistryView(address(ais)),
            IStakeVaultView(address(vault)),
            IOperationContext(address(ctx)),
            0,
            1 days
        );

        account = new MockGovernedAccount();
        verifier.setAccount(address(account), true, owner);
        registry.setRegistered(address(account), true);

        // Baseline valid checkpoint (score 8000, fresh)
        ais.setCheckpoint(
            address(account),
            8000,
            100,
            bytes32(0),
            uint64(block.timestamp)
        );

        // Install hook on account (window: 1 day, ownerFloor: 0)
        account.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));

        // Setup tracked token
        token = new IntegrityToken(address(this), 0);
        hook.setKnownToken(address(token), true);
        token.mint(address(account), 1_000_000 ether);

        // Fund native balance
        vm.deal(address(account), 1_000_000 ether);

        // Account owner configuration on IntegrityHook
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));
        hook.setAllowlistEnabled(false);
        hook.setTokenLimit(address(token), uint128(PER_CALL_CAP), uint128(WINDOW_CAP));
        hook.setNativeLimit(uint128(PER_CALL_CAP), uint128(WINDOW_CAP));
        vm.stopPrank();

        // Deploy reentrancy helper
        reenteringTarget = new ReenteringTarget(account, recipient);
    }

    function _singleCall(address target, uint256 val, bytes memory data)
        internal
        pure
        returns (bytes memory)
    {
        return abi.encodePacked(target, val, data);
    }

    /// @dev Property 1: Per-call token containment.
    /// An execute call by a session key either reverts or stays within the per-call cap.
    function check_perCallTokenContainment(uint256 amount) public {
        vm.assume(amount <= 500 ether);

        ctx.setRole(address(account), IOperationContext.Role.Session);

        bytes memory callData = abi.encodeWithSelector(IERC20.transfer.selector, recipient, amount);
        bytes memory execData = _singleCall(address(token), 0, callData);

        uint256 recipientBefore = token.balanceOf(recipient);

        try account.execute(bytes32(0), execData) {
            assert(amount <= PER_CALL_CAP);
            assert(token.balanceOf(recipient) == recipientBefore + amount);
        } catch {
            assert(amount > PER_CALL_CAP);
        }
    }

    /// @dev Property 2: Window containment across two sequential calls.
    /// Cumulative spending across two individually within-cap calls cannot exceed window cap.
    function check_windowContainmentAcrossTwoCalls(uint256 a, uint256 b) public {
        uint256 tightWindow = 15 ether;
        vm.assume(a <= PER_CALL_CAP);
        vm.assume(b <= PER_CALL_CAP);
        vm.assume(a <= 50 ether && b <= 50 ether);

        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setTokenLimit(address(token), uint128(PER_CALL_CAP), uint128(tightWindow));

        ctx.setRole(address(account), IOperationContext.Role.Session);

        // First call within per-call cap (and <= window cap)
        bytes memory exec1 = _singleCall(
            address(token),
            0,
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, a)
        );
        account.execute(bytes32(0), exec1);

        // Second call
        bytes memory exec2 = _singleCall(
            address(token),
            0,
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, b)
        );

        try account.execute(bytes32(0), exec2) {
            assert(a + b <= tightWindow);
        } catch {
            assert(a + b > tightWindow);
        }
    }

    /// @dev Property 3: Token and native limits conjunction.
    /// On an account with both limits configured, neither check masks or bypasses the other.
    function check_tokenAndNativeConjunction(uint256 t, uint256 n) public {
        uint256 nativePerCall = 5 ether;
        uint256 nativeWindow = 50 ether;
        vm.assume(t <= 50 ether);
        vm.assume(n <= 50 ether);

        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));
        hook.setTokenLimit(address(token), uint128(PER_CALL_CAP), uint128(WINDOW_CAP));
        hook.setNativeLimit(uint128(nativePerCall), uint128(nativeWindow));
        vm.stopPrank();

        ctx.setRole(address(account), IOperationContext.Role.Session);

        // Token call check
        bytes memory tokenExec = _singleCall(
            address(token),
            0,
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, t)
        );
        try account.execute(bytes32(0), tokenExec) {
            assert(t <= PER_CALL_CAP);
        } catch {
            assert(t > PER_CALL_CAP);
        }

        // Native call check on the SAME hook/account
        bytes memory nativeExec = _singleCall(recipient, n, "");
        try account.execute(bytes32(0), nativeExec) {
            assert(n <= nativePerCall);
        } catch {
            assert(n > nativePerCall);
        }
    }

    /// @dev Property 4: AIS reputation and freshness gating.
    /// Value-moving calls succeed only if checkpoint is fresh and score meets the floor.
    function check_aisGating(uint32 score, uint64 age) public {
        vm.assume(age <= 30 days);

        uint64 postedAt = uint64(block.timestamp - age);
        if (postedAt == 0) postedAt = 1;

        // Set checkpoint with symbolic score and age
        ais.setCheckpoint(address(account), score, 100, bytes32(0), postedAt);

        // Configure protocol floor = 5000, owner floor = 6000
        hook.setProtocolFloor(5000);
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setOwnerFloor(6000);

        ctx.setRole(address(account), IOperationContext.Role.Session);

        bool stale = (age > 1 days);
        bool belowFloor = (score < 6000);

        bytes memory exec = _singleCall(recipient, 1 ether, "");
        try account.execute(bytes32(0), exec) {
            assert(!stale);
            assert(!belowFloor);
        } catch {
            assert(stale || belowFloor);
        }
    }

    /// @dev Property 5: Reentrancy protection.
    /// Reentrant execution through an external target is rejected by the armed guard.
    function check_reentrancyCannotExceedWindow(uint256 outer, uint256 nested) public {
        vm.assume(outer <= PER_CALL_CAP);
        vm.assume(nested <= PER_CALL_CAP);
        vm.assume(outer <= 50 ether && nested <= 50 ether);

        ctx.setRole(address(account), IOperationContext.Role.Session);

        reenteringTarget.setNestedAmount(nested);

        bytes memory outerExec = _singleCall(
            address(reenteringTarget),
            outer,
            abi.encodeWithSelector(ReenteringTarget.attack.selector)
        );

        try account.execute(bytes32(0), outerExec) {
            // Reentrant call must never succeed
            assert(false);
        } catch {
            // Reverted as expected; armed state cleared
            assert(!hook.armed(address(account)));
        }
    }
}
