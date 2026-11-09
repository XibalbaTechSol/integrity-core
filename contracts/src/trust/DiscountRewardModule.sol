// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IRewardModule} from "./IRewardModule.sol";

/// @title DiscountRewardModule
/// @notice Reward module that raises an agent's trust discount on positive score deltas.
/// @dev Discount grows by `BPS_PER_POINT` basis points per score point gained, capped at
/// `MAX_DISCOUNT_BPS`. Non-positive deltas never decrease the discount.
contract DiscountRewardModule is IRewardModule {
    uint256 public constant MAX_DISCOUNT_BPS = 5000;
    uint256 public constant BPS_PER_POINT = 50;

    address public immutable registry;

    mapping(address => uint256) public trustDiscountBps;

    error NotRegistry();

    constructor(address registry_) {
        registry = registry_;
    }

    function onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32) external {
        if (msg.sender != registry) revert NotRegistry();
        if (newScore <= oldScore) return;

        uint256 gain = uint256(newScore - oldScore) * BPS_PER_POINT;
        uint256 next = trustDiscountBps[agent] + gain;
        trustDiscountBps[agent] = next > MAX_DISCOUNT_BPS ? MAX_DISCOUNT_BPS : next;
    }
}
