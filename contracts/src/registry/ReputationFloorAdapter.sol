// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ReputationRegistry} from "../oracle/ReputationRegistry.sol";
import {IAdapter} from "./IAdapter.sol";

/// @title ReputationFloorAdapter
/// @notice Reference `IAdapter` implementation: rejects a subject whose
/// `ReputationRegistry.effectiveScore` is below a declared floor. The registry-facing sibling of
/// `ReputationFloorLicenceHook.sol` (`ILicenceHook`, `PRODUCTION_GAPS.md` §51) -- same underlying
/// registry, same live (uncached) read, same rationale: this adapter is not subject to
/// `IntegrityKernel`'s own ERC-4337 validation-phase gas ceiling, so the simpler always-current
/// read is preferred over an epoch-snapshot cache. Deliberately a separate contract from
/// `ReputationFloorLicenceHook` rather than a shared base -- `IAdapter.check(address,uint256)` and
/// `ILicenceHook.preConsume(address,address,uint256,uint256)` are different interfaces by design
/// (see `docs/design/phase3-adapter-encoding-strategy-2026-08-25.md`'s own open question on
/// whether they should ever merge); this slice does not resolve that.
contract ReputationFloorAdapter is IAdapter {
    error ReputationBelowFloor(address subject, uint256 score, uint256 floor);

    ReputationRegistry public immutable reputationRegistry;
    uint256 public immutable minEffectiveScore;

    constructor(ReputationRegistry reputationRegistry_, uint256 minEffectiveScore_) {
        reputationRegistry = reputationRegistry_;
        minEffectiveScore = minEffectiveScore_;
    }

    /// @param subject The address whose reputation is checked.
    /// @dev Second `IAdapter.check` parameter (`amount`) is unused -- this adapter's decision does
    /// not depend on a numeric amount.
    function check(address subject, uint256) external view {
        uint256 score = reputationRegistry.effectiveScore(subject);
        if (score < minEffectiveScore) revert ReputationBelowFloor(subject, score, minEffectiveScore);
    }
}
