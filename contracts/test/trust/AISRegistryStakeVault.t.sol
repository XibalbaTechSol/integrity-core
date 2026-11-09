// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AISRegistry} from "../../src/trust/AISRegistry.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {RewardRegistry} from "../../src/trust/RewardRegistry.sol";
import {IRewardModule} from "../../src/trust/IRewardModule.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";
import {XibalbaAgentRegistry} from "../../src/framework/XibalbaAgentRegistry.sol";

/// @dev Test-only recording fixture.
contract RecordingModule is IRewardModule {
    uint256 public calls;
    uint32 public lastOld;
    uint32 public lastNew;
    bytes32 public lastDomain;

    function onPositiveCheckpoint(address, uint32 o, uint32 n, bytes32 d) external {
        calls++;
        lastOld = o;
        lastNew = n;
        lastDomain = d;
    }
}

/// @dev Test-only module that always reverts (controller ruling R5).
contract RevertingModule is IRewardModule {
    function onPositiveCheckpoint(address, uint32, uint32, bytes32) external pure {
        revert("module boom");
    }
}

contract AISRegistryStakeVaultTest is Test {
    AISRegistry ais;
    StakeVault vault;
    ITK itk;
    RewardRegistry rewards;
    XibalbaAgentRegistry agents;

    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    address agent = makeAddr("agent");

    bytes32 constant DOMAIN = keccak256("domain-A");
    bytes32 constant ROOT = keccak256("evidence");
    uint256 constant STAKE = 1000 ether;

    function setUp() public {
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        rewards = new RewardRegistry(admin);
        agents = new XibalbaAgentRegistry(admin);

        ais.grantRole(ais.SCORER_ROLE(), scorer);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        rewards.grantRole(rewards.NOTIFIER_ROLE(), address(ais));
        vault.setFreezeThreshold(5000);
        itk.mint(agent, 10_000 ether);

        agents.grantRole(agents.REGISTRAR_ROLE(), admin);
        XibalbaAgentRegistry.PrimitiveSet memory ps;
        ps.sovereignAgent = agent;
        ps.stateAnchor = makeAddr("anchor");
        agents.registerPrimitives(keccak256("did:agent"), ps, makeAddr("controller"), DOMAIN);
        vm.stopPrank();

        vm.prank(agent);
        itk.approve(address(vault), type(uint256).max);
    }

    function _wireVault() internal {
        vm.prank(admin);
        ais.setStakeVault(address(vault));
    }

    function _wireReward(address module) internal {
        vm.startPrank(admin);
        ais.setRewardRegistry(address(rewards));
        ais.setAgentRegistry(address(agents));
        rewards.setModule(DOMAIN, module);
        vm.stopPrank();
    }

    function _post(uint32 score, uint256 releasable) internal {
        vm.prank(scorer);
        ais.postCheckpoint(agent, score, 1, ROOT, releasable);
    }

    // ---- setters ----

    function test_setters_adminOnly() public {
        bytes32 role = ais.DEFAULT_ADMIN_ROLE();
        bytes memory err = abi.encodeWithSelector(
            bytes4(keccak256("AccessControlUnauthorizedAccount(address,bytes32)")), scorer, role
        );
        vm.startPrank(scorer);
        vm.expectRevert(err);
        ais.setStakeVault(address(vault));
        vm.expectRevert(err);
        ais.setRewardRegistry(address(rewards));
        vm.expectRevert(err);
        ais.setAgentRegistry(address(agents));
        vm.stopPrank();
    }

    // ---- freeze ----

    function test_belowThreshold_freezesAtomically() public {
        _wireVault();
        _post(4999, 0);
        assertTrue(vault.stakeOf(agent).frozen);
        (uint32 score,,) = ais.latest(agent);
        assertEq(score, 4999);
    }

    function test_atOrAboveThreshold_doesNotFreeze() public {
        _wireVault();
        _post(5000, 0);
        assertFalse(vault.stakeOf(agent).frozen);
        _post(9000, 0);
        assertFalse(vault.stakeOf(agent).frozen);
    }

    // ---- release ----

    function test_releasable_decrementsLocked() public {
        _wireVault();
        vm.startPrank(agent);
        vault.stake(STAKE);
        vault.lockForAction(agent, 400 ether);
        vm.stopPrank();

        _post(9000, 150 ether);
        assertEq(vault.stakeOf(agent).locked, 250 ether);
    }

    // ---- unset vault ----

    function test_unsetVault_reverts() public {
        vm.prank(scorer);
        vm.expectRevert(AISRegistry.StakeVaultNotSet.selector);
        ais.postCheckpoint(agent, 9000, 1, ROOT, 0);
    }

    // ---- reward ----

    function test_positiveDelta_notifiesRecordingModule() public {
        _wireVault();
        RecordingModule rec = new RecordingModule();
        _wireReward(address(rec));

        _post(6000, 0); // 0 -> 6000
        assertEq(rec.calls(), 1);
        assertEq(rec.lastOld(), 0);
        assertEq(rec.lastNew(), 6000);
        assertEq(rec.lastDomain(), DOMAIN);

        _post(6000, 0); // flat: no notify
        _post(5500, 0); // negative: no notify
        assertEq(rec.calls(), 1);
    }

    function test_positiveDelta_raisesRealDiscount() public {
        _wireVault();
        DiscountRewardModule mod = new DiscountRewardModule(address(rewards));
        _wireReward(address(mod));

        _post(60, 0); // 0 -> 60 points * 50 bps = 3000
        assertEq(mod.trustDiscountBps(agent), 3000);
        _post(70, 0); // +10 * 50 = 500
        assertEq(mod.trustDiscountBps(agent), 3500);
    }

    function test_rewardSkipped_whenAgentRegistryUnset() public {
        _wireVault();
        RecordingModule rec = new RecordingModule();
        vm.startPrank(admin);
        ais.setRewardRegistry(address(rewards));
        rewards.setModule(DOMAIN, address(rec));
        vm.stopPrank();

        _post(6000, 0);
        assertEq(rec.calls(), 0);
    }

    // ---- R5 ----

    function test_revertingModule_doesNotBlockCheckpointOrFreeze() public {
        _wireVault();
        _wireReward(address(new RevertingModule()));
        vm.prank(admin);
        vault.setFreezeThreshold(8000);

        _post(6000, 0); // 0 -> 6000: positive delta, below threshold, module reverts
        assertTrue(vault.stakeOf(agent).frozen, "freeze must still apply");
        (uint32 score,,) = ais.latest(agent);
        assertEq(score, 6000, "score must still be stored");
    }

    function test_unregisteredAgent_doesNotBlockCheckpoint() public {
        _wireVault();
        _wireReward(address(new RecordingModule()));
        address ghost = makeAddr("ghost");
        vm.prank(scorer);
        ais.postCheckpoint(ghost, 6000, 1, ROOT, 0);
        (uint32 score,,) = ais.latest(ghost);
        assertEq(score, 6000);
    }
}
