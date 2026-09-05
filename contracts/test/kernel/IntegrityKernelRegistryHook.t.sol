// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StdStorage, stdStorage} from "forge-std/StdStorage.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {
    ERC7579Utils,
    Mode,
    CallType,
    ExecType,
    ModeSelector,
    ModePayload
} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";
import {IntegrityAccount} from "../../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {ReputationFloorAdapter} from "../../src/registry/ReputationFloorAdapter.sol";
import {IAdapter} from "../../src/registry/IAdapter.sol";

/// @notice Genuinely burns gas in a loop until it runs out -- mirrors `AdapterRegistry.t.sol`'s
/// own `GasBurnerAdapter`, needed again here because the kernel now calls the adapter directly
/// rather than through the registry (§55's mitigation), so the distinguishing logic under test
/// lives in `IntegrityKernel.preCheck` now, not only in `AdapterRegistry.evaluate`.
contract KernelGasBurnerAdapter is IAdapter {
    uint256 public counter;

    function check(address, uint256) external {
        while (true) {
            counter += 1;
        }
    }
}

/// @notice Rejects with a BARE revert (zero-length returndata) even with plenty of gas --
/// isolates the disclosed limitation: indistinguishable from true out-of-gas by the zero-length-
/// returndata heuristic `IntegrityKernel.preCheck` now also uses directly.
contract KernelBareRevertAdapter is IAdapter {
    function check(address, uint256) external pure {
        revert();
    }
}

/// @notice The Phase III `registryHook`/`registryAdapter` slot on `IntegrityKernel`
/// (`PRODUCTION_GAPS.md` §54) -- a SECOND, independent additive precondition in `preCheck`,
/// alongside the existing cached reputation/assurance-tier checks. Deliberately a standalone
/// test file, not folded into `IntegrityAccount.t.sol`, matching how `LicenceAccountHook.t.sol`
/// isolated its own registry-hook coverage.
/// @dev This file remains the concrete-Foundry coverage for this configuration, and stays the
/// place that demonstrates the exact score/floor setup (`REGISTRY_MIN_SCORE` deliberately higher
/// than the kernel's own `MIN_EFFECTIVE_SCORE`) a Halmos property later generalized. **As of
/// 2026-09-05, this configuration also has real, machine-checked coverage**:
/// `test/halmos/KernelPropertiesRegistryEnabled.t.sol`, via
/// `HalmosKernelFixture._deployRealKernelWithRegistry`, proves budget containment and the
/// reentrancy guard both hold with the registry ENABLED (not just added-but-disabled), and proves
/// -- over the FULL symbolic score range, not just the one value this file's own
/// `REGISTRY_MIN_SCORE`/`MIN_EFFECTIVE_SCORE` split demonstrates concretely -- that the registry
/// adapter's floor and the kernel's own cached floor are each independently, conjunctively
/// enforced. This file's own tests remain valuable as concrete, readable worked examples and stay
/// in place; they are no longer the ONLY evidence for this configuration.
contract IntegrityKernelRegistryHookTest is Test {
    using stdStorage for StdStorage;

    IntegrityAccount account;
    IntegrityKernel kernel;
    ReputationRegistry reputation;
    AdapterRegistry registry;
    ReputationFloorAdapter adapter;

    address signer;
    address guardian1;
    address guardian2;
    address guardian3;
    address[] guardianSet;
    address recipient;

    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;
    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days; // must be >= MODULE_ACTION_TIMELOCK
    uint256 constant REGISTRY_MIN_SCORE = 700; // deliberately a DIFFERENT, higher floor than the
    // kernel's own MIN_EFFECTIVE_SCORE, so a test can isolate which check actually fired.

    function setUp() public {
        signer = makeAddr("signer");
        guardian1 = makeAddr("guardian1");
        guardian2 = makeAddr("guardian2");
        guardian3 = makeAddr("guardian3");
        guardianSet = [guardian1, guardian2, guardian3];
        recipient = makeAddr("recipient");

        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        registry = new AdapterRegistry();
        adapter = new ReputationFloorAdapter(reputation, REGISTRY_MIN_SCORE);
        registry.register(address(adapter), 200_000, keccak256("reputation-floor-v1"));

        address predictedAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        reputation.updateScore(predictedAccount, MIN_EFFECTIVE_SCORE); // above the KERNEL's own
        // floor but BELOW the registry adapter's higher floor -- isolates the new check.
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
            0,
            registry,
            address(adapter)
        );
        account = new IntegrityAccount(
            signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        assertEq(address(account), predictedAccount, "CREATE address prediction must match actual deployment");
        vm.deal(address(account), 10 ether);
    }

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

    function test_constructorRevertsWhenRegistrySetButAdapterIsZero() public {
        vm.expectRevert(IntegrityKernel.ZeroRegistryAdapter.selector);
        new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(0)
        );
    }

    function test_constructorRevertsWhenAdapterWasNeverRegistered() public {
        address neverRegistered = makeAddr("neverRegistered");
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.RegistryAdapterNotRegistered.selector, address(registry), neverRegistered
            )
        );
        new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            neverRegistered
        );
    }

    function test_executeRevertsWhenAccountBelowRegistryFloorEvenThoughKernelsOwnFloorPasses() public {
        // setUp's score (MIN_EFFECTIVE_SCORE = 500) clears the kernel's OWN floor but not the
        // registry adapter's higher one (700) -- isolates that the NEW check is what fires.
        uint256 accountBalanceBefore = address(account).balance;
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));

        // effectiveScore applies the ZK boost this setUp granted -- 500 * 1.15 = 575, not the
        // raw 500 baseScore.
        uint256 boostedScore = (MIN_EFFECTIVE_SCORE * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        vm.expectRevert(
            abi.encodeWithSelector(
                ReputationFloorAdapter.ReputationBelowFloor.selector, address(account), boostedScore, REGISTRY_MIN_SCORE
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(address(account).balance, accountBalanceBefore, "a reverted execute must move zero funds");
    }

    function test_executeSucceedsWhenAccountMeetsBothFloors() public {
        reputation.updateScore(address(account), REGISTRY_MIN_SCORE);
        kernel.refreshReputationSnapshot();

        uint256 recipientBalanceBefore = recipient.balance;
        uint256 sendAmount = 0.1 ether;
        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(recipient.balance, recipientBalanceBefore + sendAmount);
    }

    /// @dev The gap the first mutation-testing pass against §55's direct-call distinguishing
    /// logic actually found: neither existing test above exercises the zero-length-returndata
    /// path at all (`ReputationFloorAdapter` always reverts with a real typed error, never a bare
    /// revert or a real out-of-gas) -- mutating `if (reason.length == 0)` to `if (false)` left
    /// every existing test green. This test and the two below close that gap directly, mirroring
    /// `AdapterRegistry.t.sol`'s own `GasBurnerAdapter`/`BareRevertAdapter` coverage.
    function test_executeReportsRegistryAdapterExceededGasBoundForARealOutOfGasAdapter() public {
        KernelGasBurnerAdapter burner = new KernelGasBurnerAdapter();
        registry.register(address(burner), 10_000, keccak256("burner-v1"));

        address predictedBurnerAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        reputation.updateScore(predictedBurnerAccount, REGISTRY_MIN_SCORE + 100);
        _setZkBoostExpiry(predictedBurnerAccount, block.timestamp + 7 days);
        IntegrityKernel burnerKernel = new IntegrityKernel(
            predictedBurnerAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(burner)
        );
        IntegrityAccount burnerAccount = new IntegrityAccount(
            signer, address(burnerKernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        vm.deal(address(burnerAccount), 10 ether);

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.RegistryAdapterExceededGasBound.selector, address(burner), 10_000)
        );
        vm.prank(address(burnerAccount));
        burnerAccount.execute(_singleCallMode(), executionCalldata);
    }

    /// @dev Proves the disclosed limitation directly, same discipline as `AdapterRegistry.t.sol`'s
    /// own `test_bareRevertIsIndistinguishableFromGasBoundExceeded`: a bare `revert()` with plenty
    /// of gas remaining is ALSO reported as `RegistryAdapterExceededGasBound`, not silently
    /// glossed over in prose only.
    function test_bareRevertFromRegistryAdapterIsIndistinguishableFromGasBoundExceeded() public {
        KernelBareRevertAdapter bare = new KernelBareRevertAdapter();
        registry.register(address(bare), 200_000, keccak256("bare-revert-v1"));

        address predictedBareAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        reputation.updateScore(predictedBareAccount, REGISTRY_MIN_SCORE + 100);
        _setZkBoostExpiry(predictedBareAccount, block.timestamp + 7 days);
        IntegrityKernel bareKernel = new IntegrityKernel(
            predictedBareAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(bare)
        );
        IntegrityAccount bareAccount = new IntegrityAccount(
            signer, address(bareKernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        vm.deal(address(bareAccount), 10 ether);

        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.RegistryAdapterExceededGasBound.selector, address(bare), 200_000)
        );
        vm.prank(address(bareAccount));
        bareAccount.execute(_singleCallMode(), executionCalldata);
    }
}

/// @notice End-to-end `preCheck` gas measurement with the registry ENABLED -- the follow-on
/// measurement `PRODUCTION_GAPS.md` §54 named as real, disclosed, not-yet-done work. Deliberately
/// a SEPARATE contract from `IntegrityKernelRegistryHookTest` above: the score that clears both
/// floors must be set in `setUp()`, not inline in the measured test function, or the same-slot
/// `updateScore` write would pre-warm exactly the storage `ReputationFloorAdapter.check`'s
/// `effectiveScore` read then touches -- the identical same-transaction-warm-read pitfall
/// `PRODUCTION_GAPS.md` §41's own dependency-inventory section named for `IntegrityKernel`'s
/// tracked-token check, and #48 named again for `LicenceAccount`'s `via_ir` timestamp caching.
/// `setUp()` runs as a separate top-level call from Foundry's perspective, so the measured test
/// function's very first `preCheck` call is a genuinely cold read, same discipline as
/// `test_preCheckGasExceedsPaperTable4BudgetWithTrackedTokenLiveRead` in `IntegrityAccount.t.sol`.
contract IntegrityKernelRegistryHookGasTest is Test {
    using stdStorage for StdStorage;

    IntegrityAccount account;
    IntegrityKernel kernel;
    ReputationRegistry reputation;
    AdapterRegistry registry;
    ReputationFloorAdapter adapter;

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
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;
    uint256 constant REGISTRY_MIN_SCORE = 700;

    function setUp() public {
        signer = makeAddr("signer");
        guardian1 = makeAddr("guardian1");
        guardian2 = makeAddr("guardian2");
        guardian3 = makeAddr("guardian3");
        guardianSet = [guardian1, guardian2, guardian3];

        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        registry = new AdapterRegistry();
        adapter = new ReputationFloorAdapter(reputation, REGISTRY_MIN_SCORE);
        registry.register(address(adapter), 200_000, keccak256("reputation-floor-v1"));

        address predictedAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        // Set the score high enough to clear BOTH the kernel's own floor and the registry
        // adapter's floor, in setUp -- NOT in the measured test function itself.
        reputation.updateScore(predictedAccount, REGISTRY_MIN_SCORE + 100);
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
            0,
            registry,
            address(adapter)
        );
        account = new IntegrityAccount(
            signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        assertEq(address(account), predictedAccount);
        vm.deal(address(account), 10 ether);
        // The atomic initial snapshot taken at kernel construction is already current -- no
        // refreshReputationSnapshot() call needed (and none is made here, so it cannot warm
        // anything the measured call would otherwise touch cold).
    }

    function _setZkBoostExpiry(address subject, uint256 expiry) internal {
        stdstore.target(address(reputation)).sig("scores(address)").with_key(subject).depth(2).checked_write(expiry);
    }

    /// @notice The measurement `PRODUCTION_GAPS.md` §54/§55 named: `preCheck`'s real, end-to-end,
    /// cold gas cost with the registry genuinely enabled (not the isolated `AdapterRegistry.
    /// evaluate` figure from §52, and not the disabled-branch figure already covered by the
    /// existing `test_preCheckGasIsUnderPaperTable4BudgetWithCachedReputation`).
    /// **Real, disclosed finding, MITIGATED but not eliminated (§55): originally measured at
    /// ~59.2k gas (a call routed through `AdapterRegistry.evaluate`); mitigated to ~49.3k gas by
    /// having the kernel call the registered adapter DIRECTLY, using a gas bound mirrored once at
    /// construction (see `registryAdapterGasBound`'s own NatSpec) -- a real ~9.9k-gas reduction,
    /// removing the registry hop's own external-call overhead. STILL over the whitepaper's Table 4
    /// `preCheck` ceiling (`<=40k`) by ~9.3k gas** -- a third crossing in this codebase's history,
    /// same category as `IntegrityKernel`'s tracked-token check (§41), now partially mitigated
    /// rather than fully accepted as-is. The remaining cost is the adapter's own live external
    /// read (`ReputationFloorAdapter` reading `ReputationRegistry.effectiveScore`, ~15.5k gas
    /// cold) -- unavoidable without caching the score itself, which this kernel deliberately does
    /// NOT do for a registry-installed adapter (would silently break any adapter, like
    /// `SpendBudgetAdapter`, whose correctness depends on genuinely live per-call state).
    function test_preCheckGasCostWithRegistryEnabled() public {
        vm.prank(address(account));
        uint256 gasBefore = gasleft();
        kernel.preCheck(address(account), 0, "");
        uint256 gasUsed = gasBefore - gasleft();

        assertGt(
            gasUsed,
            44_000,
            "this test's OWN name/doc asserts a mitigated-but-still-over-budget finding (~49.3k) "
            "-- if this now fails low, the remaining crossing may have been resolved (e.g. by "
            "caching the adapter's own read) and this test should be replaced with an "
            "under-budget assertion, not left stale"
        );
        assertLt(
            gasUsed,
            54_000,
            "regression ceiling -- a further, unexplained rise could mean something other than "
            "the named, understood cost (the adapter's own live cold read) is now driving this "
            "number, e.g. the direct-call mitigation silently regressed back toward the "
            "registry-hop cost"
        );

        vm.prank(address(account));
        kernel.postCheck(abi.encode(address(account).balance, uint256(0)));
    }
}
