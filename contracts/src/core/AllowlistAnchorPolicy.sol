// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAnchorPolicy} from "./IAnchorPolicy.sol";

/// @title AllowlistAnchorPolicy
/// @notice Reference IAnchorPolicy: only pre-approved oracle/controller callers may anchor,
///         and the empty root is never allowed (defense in depth vs StateAnchor.EmptyRoot).
contract AllowlistAnchorPolicy is AccessControl, IAnchorPolicy {
    mapping(address => bool) public allowedCaller;

    event CallerAllowed(address indexed caller, bool allowed);

    constructor(address admin, address[] memory initialCallers) {
        require(admin != address(0), "AllowlistAnchorPolicy: zero admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        for (uint256 i = 0; i < initialCallers.length; i++) {
            allowedCaller[initialCallers[i]] = true;
            emit CallerAllowed(initialCallers[i], true);
        }
    }

    function setCaller(address caller, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE) {
        allowedCaller[caller] = allowed;
        emit CallerAllowed(caller, allowed);
    }

    function check(address caller, bytes32 root, uint256 /* nextEpoch */) external view returns (bool) {
        if (root == bytes32(0)) return false;
        return allowedCaller[caller];
    }
}
