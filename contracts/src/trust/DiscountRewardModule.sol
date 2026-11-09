// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IRewardModule} from "./IRewardModule.sol";

/// @title DiscountRewardModule
/// @notice Reward module that raises an agent's stake-lock trust discount on positive score deltas.
/// @dev Discount grows gradually with the agent's integrity score and is capped at
/// `MAX_DISCOUNT_BPS`. Non-positive deltas never decrease the discount.
///
/// Units. An AIS score is basis points of integrity, `0..10000` (see `AISRegistry.MAX_SCORE`); one
/// whole **AIS point** is therefore `SCORE_BPS_PER_POINT = 100` score-bps, so the score ranges over
/// 0..100 points. The discount grows by `discountBpsPerPoint` basis points of stake discount for
/// each whole AIS point of positive score gain:
///
///   gain = (newScore - oldScore) * discountBpsPerPoint / SCORE_BPS_PER_POINT
///
/// The rate is a constructor parameter so governance can tune the curve without redeploying the
/// gate. The DEFAULT of 50 maps the full score range to the full discount (100 points × 50 bps =
/// 5000 = `MAX_DISCOUNT_BPS`), so a FIRST real checkpoint — which lands in the thousands of
/// score-bps, i.e. tens of points — earns a proportional discount (e.g. 70 points → 3500 bps) and
/// does NOT saturate the 50% cap. (The previous fixed rate of 50 bps per score-BPS maxed the cap at
/// a 100-bps / 1-point gain, making the graduated discount a flat 50%-off switch — the Important
/// this fixes.)
contract DiscountRewardModule is IRewardModule {
    /// @notice Maximum trust discount, in basis points (50%).
    uint256 public constant MAX_DISCOUNT_BPS = 5000;
    /// @notice Score-bps per whole AIS point (AIS score is bps 0..10000; 100 bps = 1 point).
    uint256 public constant SCORE_BPS_PER_POINT = 100;

    /// @notice Basis points of stake discount granted per whole AIS point of positive score gain.
    /// Immutable; set once at deploy. Default deployments use 50 (see NatSpec rationale).
    uint256 public immutable discountBpsPerPoint;

    address public immutable registry;

    mapping(address => uint256) public trustDiscountBps;

    error NotRegistry();

    /// @param registry_ The `RewardRegistry` (or scorer) allowed to post checkpoints.
    /// @param discountBpsPerPoint_ Basis points of discount per whole AIS point gained (e.g. 50).
    constructor(address registry_, uint256 discountBpsPerPoint_) {
        registry = registry_;
        discountBpsPerPoint = discountBpsPerPoint_;
    }

    function onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32) external {
        if (msg.sender != registry) revert NotRegistry();
        if (newScore <= oldScore) return;

        uint256 gain = (uint256(newScore - oldScore) * discountBpsPerPoint) / SCORE_BPS_PER_POINT;
        uint256 next = trustDiscountBps[agent] + gain;
        trustDiscountBps[agent] = next > MAX_DISCOUNT_BPS ? MAX_DISCOUNT_BPS : next;
    }
}
