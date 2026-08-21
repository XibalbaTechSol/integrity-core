// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IExecutionPolicy} from "./IExecutionPolicy.sol";

interface IAisReader {
    function ais() external view returns (uint256);
}

/// @title ConstraintExecutionPolicy
/// @notice Reference IExecutionPolicy: optional AIS floor, native-value cap, and target allowlist.
/// @dev AIS is read from the agent contract itself (`SovereignAgent.ais`). A zero `maxValue`
///      means no cap. `enforceTargetAllowlist == false` means any target is permitted.
contract ConstraintExecutionPolicy is AccessControl, IExecutionPolicy {
    uint256 public minAis;
    uint256 public maxValue;
    bool public enforceTargetAllowlist;
    mapping(address => bool) public allowedTarget;

    event ConstraintsUpdated(uint256 minAis, uint256 maxValue, bool enforceTargetAllowlist);
    event TargetAllowed(address indexed target, bool allowed);

    constructor(address admin, uint256 minAis_, uint256 maxValue_, bool enforceTargetAllowlist_) {
        require(admin != address(0), "ConstraintExecutionPolicy: zero admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        minAis = minAis_;
        maxValue = maxValue_;
        enforceTargetAllowlist = enforceTargetAllowlist_;
        emit ConstraintsUpdated(minAis_, maxValue_, enforceTargetAllowlist_);
    }

    function setConstraints(uint256 minAis_, uint256 maxValue_, bool enforceTargetAllowlist_)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        minAis = minAis_;
        maxValue = maxValue_;
        enforceTargetAllowlist = enforceTargetAllowlist_;
        emit ConstraintsUpdated(minAis_, maxValue_, enforceTargetAllowlist_);
    }

    function setTarget(address target, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE) {
        allowedTarget[target] = allowed;
        emit TargetAllowed(target, allowed);
    }

    function check(address agent, address target, uint256 value, bytes calldata /* data */)
        external
        view
        returns (bool)
    {
        if (IAisReader(agent).ais() < minAis) return false;
        if (maxValue != 0 && value > maxValue) return false;
        if (enforceTargetAllowlist && !allowedTarget[target]) return false;
        return true;
    }
}
