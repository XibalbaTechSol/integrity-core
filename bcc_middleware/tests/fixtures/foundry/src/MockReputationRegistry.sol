// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal stand-in for the real `contracts/` ReputationRegistry.sol.
/// TEST FIXTURE ONLY -- proves bcc_middleware's `app/reputation.py` real
/// eth_sendTransaction code path (updateScore) end-to-end against a local
/// anvil chain. Permissionless (no ORACLE_ROLE check), same convention as
/// the sibling MockStateAnchor/MockBAARegistry fixtures -- role-gating is
/// the real contract's job; this fixture only proves the ABI/call shape.
contract MockReputationRegistry {
    mapping(address => uint256) public baseScoreOf;
    mapping(address => uint256) public lastUpdateOf;
    mapping(address => uint256) public zkVerifiedEventRatioBps;

    event ScoreUpdated(address indexed agent, uint256 oldBaseScore, uint256 newBaseScore, address indexed updatedBy);

    function updateScore(address agent, uint256 baseScore) external {
        uint256 old = baseScoreOf[agent];
        baseScoreOf[agent] = baseScore;
        lastUpdateOf[agent] = block.timestamp;
        emit ScoreUpdated(agent, old, baseScore, msg.sender);
    }

    function updateScoreWithCoverage(address agent, uint256 baseScore, uint256 ratioBps) external {
        require(ratioBps <= 10_000, "ratio");
        uint256 old = baseScoreOf[agent];
        baseScoreOf[agent] = baseScore;
        lastUpdateOf[agent] = block.timestamp;
        emit ScoreUpdated(agent, old, baseScore, msg.sender);
        zkVerifiedEventRatioBps[agent] = ratioBps;
    }
}
