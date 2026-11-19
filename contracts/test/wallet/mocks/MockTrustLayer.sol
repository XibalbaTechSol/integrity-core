// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {
    IAgentRegistryView,
    IAISRegistryView,
    IStakeVaultView
} from "../../../src/wallet/IntegrityHook.sol";

contract MockAgentRegistry is IAgentRegistryView {
    mapping(address => bool) public registered;

    function setRegistered(address agent, bool reg) external {
        registered[agent] = reg;
    }

    function isRegisteredAgent(address agent) external view override returns (bool) {
        return registered[agent];
    }
}

contract MockAISRegistry is IAISRegistryView {
    struct CheckpointData {
        uint32 score;
        uint64 windowEnd;
        bytes32 evidenceRoot;
    }

    mapping(address => CheckpointData) public checkpoints;
    mapping(address => uint64) public postedAtTimes;

    function setCheckpoint(
        address agent,
        uint32 score,
        uint64 windowEnd,
        bytes32 evidenceRoot,
        uint64 postedAtTime
    ) external {
        checkpoints[agent] = CheckpointData({
            score: score,
            windowEnd: windowEnd,
            evidenceRoot: evidenceRoot
        });
        postedAtTimes[agent] = postedAtTime;
    }

    function latest(address agent)
        external
        view
        override
        returns (uint32 score, uint64 windowEnd, bytes32 evidenceRoot)
    {
        CheckpointData memory c = checkpoints[agent];
        return (c.score, c.windowEnd, c.evidenceRoot);
    }

    function postedAt(address agent) external view override returns (uint64) {
        return postedAtTimes[agent];
    }
}

contract MockStakeVault is IStakeVaultView {
    mapping(address => Stake) public stakes;

    function setStake(
        address agent,
        uint256 amount,
        uint256 locked,
        bool frozen,
        uint64 cooldownEnd
    ) external {
        stakes[agent] = Stake({
            amount: amount,
            locked: locked,
            frozen: frozen,
            cooldownEnd: cooldownEnd
        });
    }

    function setFrozen(address agent, bool frozen) external {
        stakes[agent].frozen = frozen;
    }

    function stakeOf(address agent) external view override returns (Stake memory) {
        return stakes[agent];
    }
}
