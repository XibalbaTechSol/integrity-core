// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AISRegistry} from "../../src/trust/AISRegistry.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {RewardRegistry} from "../../src/trust/RewardRegistry.sol";
import {IRewardModule} from "../../src/trust/IRewardModule.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {GateRegistryFixture} from "./GateRegistryFixture.sol";

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

/// @dev Test-only module that burns all forwarded gas.
contract GasBurnerModule is IRewardModule {
    uint256 public sink;

    function onPositiveCheckpoint(address, uint32, uint32, bytes32) external {
        while (true) {
            sink++;
        }
    }
}

/// @dev Test-only module that always reverts (controller ruling R5).
contract RevertingModule is IRewardModule {
    function onPositiveCheckpoint(address, uint32, uint32, bytes32) external pure {
        revert("module boom");
    }
}

contract AISRegistryStakeVaultTest is GateRegistryFixture {
    AISRegistry ais;
    StakeVault vault;
    ITK itk;
    RewardRegistry rewards;
    AgentRegistry agents;

    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    address agent;

    bytes32 constant DOMAIN = keccak256("domain-A");
    bytes32 constant ROOT = keccak256("evidence");
    uint256 constant STAKE = 1000 ether;

    function setUp() public {
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        rewards = new RewardRegistry(admin);
        vm.stopPrank();

        // v3: the agent is a canonical SovereignAgent bound as the actor of a record in DOMAIN
        // (binding needs the domain to have a live policy, so a minimal TrustConfig is wired).
        _deployRegistry(admin);
        agents = agentRegistry;
        _ensureDomain("domain-A");
        TrustConfig cfg = new TrustConfig(admin);
        PolicyRegistry policy = new PolicyRegistry(admin);
        (address ctl, uint256 ctlPk) = makeAddrAndKey("controller");
        SovereignAgent sa = _newAgent("did:agent", ctl);
        agent = address(sa);
        vm.startPrank(admin);
        policy.setGraphRoot(DOMAIN, keccak256("pack-root"));
        cfg.setPolicyRegistry(address(policy));
        agents.setTrustConfig(address(cfg));
        vm.stopPrank();
        _bind(sa, ctlPk, DOMAIN, ctl);

        vm.startPrank(admin);

        ais.grantRole(ais.SCORER_ROLE(), scorer);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        rewards.grantRole(rewards.NOTIFIER_ROLE(), address(ais));
        vault.setFreezeThreshold(5000);
        itk.mint(agent, 10_000 ether);

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
        DiscountRewardModule mod = new DiscountRewardModule(address(rewards), 50);
        _wireReward(address(mod));

        _post(60, 0); // 0 -> 60 bps = 60 * 50 / 100 = 30 bps discount
        assertEq(mod.trustDiscountBps(agent), 30);
        _post(70, 0); // +10 bps * 50 / 100 = 5 -> 35
        assertEq(mod.trustDiscountBps(agent), 35);
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

    event RewardNotifyFailed(address indexed agent, bytes reason);

    function test_revertingModule_emitsRewardNotifyFailed() public {
        _wireVault();
        _wireReward(address(new RevertingModule()));
        // reason is the bubbled revert data: Error("module boom")
        bytes memory reason = abi.encodeWithSignature("Error(string)", "module boom");
        vm.expectEmit(true, false, false, true, address(ais));
        emit RewardNotifyFailed(agent, reason);
        _post(6000, 0);
    }

    function test_settersRejectCodelessTargets() public {
        address eoa = makeAddr("eoa");
        bytes memory err = abi.encodeWithSelector(AISRegistry.NotAContract.selector, eoa);
        vm.startPrank(admin);
        vm.expectRevert(err);
        ais.setStakeVault(eoa);
        vm.expectRevert(err);
        ais.setRewardRegistry(eoa);
        vm.expectRevert(err);
        ais.setAgentRegistry(eoa);
        // zero still allowed (unset)
        ais.setRewardRegistry(address(0));
        vm.stopPrank();
    }

    function test_gasBurningModule_doesNotBlockCheckpointOrFreeze() public {
        _wireVault();
        _wireReward(address(new GasBurnerModule()));
        vm.prank(admin);
        vault.setFreezeThreshold(8000);

        vm.prank(scorer);
        uint256 g0 = gasleft();
        ais.postCheckpoint{gas: 3_000_000}(agent, 6000, 1, ROOT, 0);
        assertLt(g0 - gasleft(), 1_000_000, "reward path gas must be capped");
        assertTrue(vault.stakeOf(agent).frozen, "freeze must survive a gas-burning module");
        (uint32 score,,) = ais.latest(agent);
        assertEq(score, 6000);
    }

    function test_missingVaultRole_revertsAndLeavesScoreUnchanged() public {
        _wireVault();
        _post(7000, 0);
        vm.startPrank(admin);
        vault.revokeRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        vm.stopPrank();

        vm.prank(scorer);
        vm.expectRevert();
        ais.postCheckpoint(agent, 100, 2, ROOT, 0);
        (uint32 score,,) = ais.latest(agent);
        assertEq(score, 7000, "critical-path revert must not be swallowed");
        assertFalse(vault.stakeOf(agent).frozen);
    }

    /// Registration v3: with an AgentRegistry wired, an address that is not a bound actor gets
    /// no checkpoint (AIS checkpoints are only for agents with an actor).
    /// MUTATION: delete the `isRegisteredAgent` check in `postCheckpoint` -> the ghost is scored,
    /// test FAILS.
    function test_unregisteredAgent_rejectedWhenRegistryWired() public {
        _wireVault();
        _wireReward(address(new RecordingModule()));
        address ghost = makeAddr("ghost");
        vm.prank(scorer);
        vm.expectRevert(abi.encodeWithSelector(AISRegistry.NotRegisteredAgent.selector, ghost));
        ais.postCheckpoint(ghost, 6000, 1, ROOT, 0);
        (uint32 score,,) = ais.latest(ghost);
        assertEq(score, 0);
    }

    /// Without a registry wired (bootstrap), checkpoints are not registration-checked.
    function test_unregisteredAgent_acceptedWhenRegistryUnset() public {
        _wireVault();
        address ghost = makeAddr("ghost");
        vm.prank(scorer);
        ais.postCheckpoint(ghost, 6000, 1, ROOT, 0);
        (uint32 score,,) = ais.latest(ghost);
        assertEq(score, 6000);
    }
}
