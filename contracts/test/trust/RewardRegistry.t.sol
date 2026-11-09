// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {RewardRegistry} from "../../src/trust/RewardRegistry.sol";
import {IRewardModule} from "../../src/trust/IRewardModule.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";

/// @dev Test-only recording fixture; deliberately not in src/.
contract RecordingRewardModule is IRewardModule {
    uint256 public calls;
    address public lastAgent;
    uint32 public lastOld;
    uint32 public lastNew;
    bytes32 public lastDomain;

    function onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId) external {
        calls++;
        lastAgent = agent;
        lastOld = oldScore;
        lastNew = newScore;
        lastDomain = domainId;
    }
}

contract RewardRegistryTest is Test {
    RewardRegistry registry;
    DiscountRewardModule discountModule;
    RecordingRewardModule recorder;

    address admin = makeAddr("admin");
    address notifier = makeAddr("notifier");
    address stranger = makeAddr("stranger");
    address agent = makeAddr("agent");

    bytes32 constant DOMAIN = keccak256("domain-A");
    bytes32 constant OTHER_DOMAIN = keccak256("domain-B");

    function setUp() public {
        registry = new RewardRegistry(admin);
        discountModule = new DiscountRewardModule(address(registry));
        recorder = new RecordingRewardModule();

        vm.startPrank(admin);
        registry.grantRole(registry.NOTIFIER_ROLE(), notifier);
        vm.stopPrank();
    }

    // ---------- RewardRegistry ----------

    function test_notify_isNoOpWhenNoModuleSet() public {
        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 100, 200, DOMAIN);
        assertEq(address(registry.moduleOf(DOMAIN)), address(0));
    }

    function test_notify_forwardsToModuleWhenSet() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(recorder));

        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 100, 250, DOMAIN);

        assertEq(recorder.calls(), 1);
        assertEq(recorder.lastAgent(), agent);
        assertEq(recorder.lastOld(), 100);
        assertEq(recorder.lastNew(), 250);
        assertEq(recorder.lastDomain(), DOMAIN);
    }

    function test_notify_routesByDomain() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(recorder));

        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 1, 2, OTHER_DOMAIN);

        assertEq(recorder.calls(), 0, "unconfigured domain must not reach the module");
    }

    function test_notify_revertsForNonNotifier() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(recorder));

        vm.prank(stranger);
        vm.expectRevert();
        registry.notifyPositiveCheckpoint(agent, 1, 2, DOMAIN);
    }

    function test_setModule_revertsForNonAdmin() public {
        vm.prank(stranger);
        vm.expectRevert();
        registry.setModule(DOMAIN, address(recorder));
    }

    // ---------- DiscountRewardModule ----------

    function test_discount_startsAtZero() public view {
        assertEq(discountModule.trustDiscountBps(agent), 0);
    }

    function test_discount_risesOnPositiveDelta() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(discountModule));

        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 100, 110, DOMAIN);

        // 10 points * BPS_PER_POINT (50) = 500 bps
        assertEq(discountModule.trustDiscountBps(agent), 500);
    }

    function test_discount_accumulatesAcrossCheckpoints() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(discountModule));

        vm.startPrank(notifier);
        registry.notifyPositiveCheckpoint(agent, 100, 110, DOMAIN);
        registry.notifyPositiveCheckpoint(agent, 110, 120, DOMAIN);
        vm.stopPrank();

        assertEq(discountModule.trustDiscountBps(agent), 1000);
    }

    function test_discount_capsAtMaxDiscountBps() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(discountModule));

        assertEq(discountModule.MAX_DISCOUNT_BPS(), 5000);

        // 1000 points * 50 = 50_000 bps raw, must cap at 5000.
        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 0, 1000, DOMAIN);
        assertEq(discountModule.trustDiscountBps(agent), 5000);

        // Further gains stay capped.
        vm.prank(notifier);
        registry.notifyPositiveCheckpoint(agent, 1000, 2000, DOMAIN);
        assertEq(discountModule.trustDiscountBps(agent), 5000);
    }

    function test_discount_noDecreaseOnNonPositiveDelta() public {
        vm.prank(admin);
        registry.setModule(DOMAIN, address(discountModule));

        vm.startPrank(notifier);
        registry.notifyPositiveCheckpoint(agent, 100, 110, DOMAIN);
        assertEq(discountModule.trustDiscountBps(agent), 500);

        registry.notifyPositiveCheckpoint(agent, 110, 110, DOMAIN); // equal
        assertEq(discountModule.trustDiscountBps(agent), 500);

        registry.notifyPositiveCheckpoint(agent, 110, 50, DOMAIN); // decrease
        assertEq(discountModule.trustDiscountBps(agent), 500);
        vm.stopPrank();
    }

    function test_discount_onlyRegistryMayCallModule() public {
        vm.prank(stranger);
        vm.expectRevert(DiscountRewardModule.NotRegistry.selector);
        discountModule.onPositiveCheckpoint(agent, 0, 10, DOMAIN);
    }
}
