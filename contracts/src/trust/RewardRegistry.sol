// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IRewardModule} from "./IRewardModule.sol";

/// @title RewardRegistry
/// @notice Pluggable positive-reward path: per-domain reward modules notified on positive trust checkpoints.
contract RewardRegistry is AccessControl {
    bytes32 public constant NOTIFIER_ROLE = keccak256("NOTIFIER_ROLE");

    mapping(bytes32 => IRewardModule) public moduleOf;

    event ModuleSet(bytes32 indexed domainId, address indexed module);

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(NOTIFIER_ROLE, admin);
    }

    function setModule(bytes32 domainId, address module) external onlyRole(DEFAULT_ADMIN_ROLE) {
        moduleOf[domainId] = IRewardModule(module);
        emit ModuleSet(domainId, module);
    }

    /// @notice Forwards a positive checkpoint to the domain's reward module.
    /// @dev No-op when no module is configured for `domainId`.
    function notifyPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId)
        external
        onlyRole(NOTIFIER_ROLE)
    {
        IRewardModule module = moduleOf[domainId];
        if (address(module) == address(0)) return;
        module.onPositiveCheckpoint(agent, oldScore, newScore, domainId);
    }
}
