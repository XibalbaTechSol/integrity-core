// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {HalmosKernelFixture} from "./HalmosKernelFixture.sol";
import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";

/// @title Registry-ENABLED sibling of `KernelProperties.t.sol`
/// @notice Closes the gap `IntegrityKernel.sol`'s own top-level NatSpec discloses and
/// `IntegrityKernelRegistryHookTest` names explicitly: every property in `KernelProperties.t.sol`
/// is checked ONLY against a kernel built with `AdapterRegistry(address(0))` (disabled) --
/// proving the registry-hook feature doesn't regress anyone who leaves it off, but NOT proving
/// anything about the registry-ENABLED branch of `preCheck`, which was previously concrete-
/// Foundry-tested only (`test/kernel/IntegrityKernelRegistryHook.t.sol`).
/// @dev Reuses the same reference adapter (`ReputationFloorAdapter`) and the same isolating
/// score-threshold trick (`REGISTRY_MIN_SCORE` deliberately higher than the kernel's own
/// `MIN_EFFECTIVE_SCORE`) as that concrete test, via `HalmosKernelFixture._deployRealKernelWithRegistry`.
/// Does not re-run all 6 properties from `KernelProperties.t.sol` -- only those where the registry
/// hook plausibly interacts with the property (budget accounting, reentrancy) plus one new
/// property specific to the registry gate's own soundness (additive, not a bypass of either
/// check). The remaining three properties there (token-budget conjunction, native-budget-still-
/// enforced-on-token-kernel, cumulative containment) exercise the SAME `preCheck` code path with
/// the SAME registry branch structure; they are not re-verified separately here because none of
/// them touch the registry-adapter call itself any differently than the one property below
/// already does -- a scoping choice, not an oversight, made to keep this Halmos run's cost
/// bounded (matching `docs/plans/2026-08-24-phase1-formal-verification-proposal.md`'s own "too
/// large a unit to authorize as one block" discipline).
contract KernelPropertiesRegistryEnabledTest is HalmosKernelFixture {
    IntegrityKernel kernel;

    function setUp() public {
        _deployPlaceholderGenesisAccount();
        kernel = _deployRealKernelWithRegistry(address(0), 0, 0);
        _swapToKernel(address(kernel));

        vm.deal(address(account), 100 ether);
    }

    /// @dev Registry-enabled sibling of `KernelProperties.t.sol`'s `check_nativeBudgetContainment`.
    /// `ABOVE_FLOOR_SCORE` (800) clears both the kernel's own floor (500) and the registry
    /// adapter's floor (700), so the adapter always allows -- this property isolates whether
    /// simply having a passing registry hook installed disturbs budget accounting at all. It
    /// should not: the registry branch in `preCheck` runs strictly after budget accounting and
    /// cannot itself move funds or change balances.
    function check_nativeBudgetContainment(address recipient, uint256 sendAmount) public {
        vm.assume(recipient != address(account));
        vm.assume(recipient != address(kernel));
        vm.assume(recipient.code.length == 0);
        vm.assume(recipient != address(0));
        vm.assume(uint160(recipient) > 0xff);

        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        try account.execute(_singleCallMode(), executionCalldata) {
            assert(sendAmount <= PER_OP_BUDGET);
            assert(sendAmount <= CUMULATIVE_BUDGET);
            assert(address(account).balance == accountBalanceBefore - sendAmount);
            assert(recipient.balance == recipientBalanceBefore + sendAmount);
        } catch {
            assert(sendAmount > PER_OP_BUDGET || sendAmount > accountBalanceBefore);
        }
    }

    /// @dev New property, specific to this configuration: the registry adapter's own floor
    /// (`REGISTRY_MIN_SCORE` = 700) and the kernel's own cached floor (`MIN_EFFECTIVE_SCORE` =
    /// 500) are each independently, CONJUNCTIVELY enforced over every reachable score -- neither
    /// check can be satisfied by the other, and passing one never substitutes for passing both.
    /// This is the actual claim `IntegrityKernel.sol`'s own NatSpec makes about the registry
    /// branch ("a SECOND, independent additive precondition") and is exactly the part no
    /// existing coverage -- concrete or Halmos -- had verified over the FULL symbolic score
    /// range; the concrete test only ever picks one score (`MIN_EFFECTIVE_SCORE`, deliberately
    /// between the two floors) to demonstrate the gap exists for that one value.
    function check_registryAdapterGatesAdditively(uint256 baseScore) public {
        // Same bound as `KernelProperties.t.sol`'s own reputation-gating property, for the same
        // reason: keeps `baseScore * ZK_BOOST_BPS` inside `effectiveScore()`'s own checked-
        // arithmetic domain, matching real AIS's bounded scale.
        vm.assume(baseScore <= 1_000_000);

        reputation.updateScore(address(account), baseScore);
        kernel.refreshReputationSnapshot();

        // No `vm.warp` in this property -- the ZK boost set at deploy time (`block.timestamp +
        // 7 days`) and the fresh snapshot just taken are both still valid at the current
        // timestamp, so this property isolates the two SCORE floors from the staleness/boost-
        // expiry axis `KernelProperties.t.sol`'s own reputation-gating property already covers
        // separately -- two axes, two properties, not one conflated property proving less than
        // either claim on its own.
        uint256 effectiveScore = (baseScore * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        bool aboveKernelFloor = effectiveScore >= MIN_EFFECTIVE_SCORE;
        bool aboveRegistryFloor = effectiveScore >= REGISTRY_MIN_SCORE;

        // Trivial, always-budget-respecting call -- isolates this property from budget
        // accounting entirely, same technique `KernelProperties.t.sol`'s reputation-gating
        // property uses for the same reason.
        bytes memory executionCalldata = abi.encodePacked(address(0xBEEF), uint256(0), bytes(""));

        vm.prank(address(account));
        try account.execute(_singleCallMode(), executionCalldata) {
            assert(aboveKernelFloor);
            assert(aboveRegistryFloor);
        } catch {
            assert(!aboveKernelFloor || !aboveRegistryFloor);
        }
    }

    /// @dev Registry-enabled sibling of `KernelProperties.t.sol`'s `check_reentrancyGuardIsSound`.
    /// The registry branch adds a SECOND external call inside `preCheck` (to the adapter, via
    /// `try/catch`, same shape as the kernel's own budget/reputation logic) -- strictly more
    /// external-call surface than the disabled configuration, and therefore the configuration
    /// most worth re-checking for this specific property rather than assuming it transfers
    /// unchanged. `ABOVE_FLOOR_SCORE` clears the registry floor throughout, so the adapter always
    /// allows -- this isolates "does an extra allowed external call in the hook path open a
    /// reentrancy window," not "does the adapter's own rejection path."
    function check_reentrancyGuardIsSound(address recipient, uint256 outerAmount, uint256 nestedAmount) public {
        vm.assume(recipient != address(account));
        vm.assume(recipient != address(kernel));
        vm.assume(recipient.code.length == 0);
        vm.assume(uint160(recipient) > 0xff);
        vm.assume(recipient != address(0));
        vm.assume(outerAmount <= PER_OP_BUDGET);
        vm.assume(nestedAmount <= PER_OP_BUDGET);

        uint256 accountBalanceBefore = address(account).balance;
        uint256 recipientBalanceBefore = recipient.balance;

        bytes memory nestedCalldata = abi.encodePacked(recipient, nestedAmount, bytes(""));
        bytes memory nestedExecuteCall = abi.encodeCall(account.execute, (_singleCallMode(), nestedCalldata));
        bytes memory outerCalldata = abi.encodePacked(address(account), outerAmount, nestedExecuteCall);

        vm.prank(address(account));
        try account.execute(_singleCallMode(), outerCalldata) {
            assert(false);
        } catch {
            assert(address(account).balance == accountBalanceBefore);
            assert(recipient.balance == recipientBalanceBefore);
            assert(!kernel.armed());
        }
    }
}
