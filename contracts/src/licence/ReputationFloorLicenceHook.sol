// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ReputationRegistry} from "../oracle/ReputationRegistry.sol";
import {ILicenceHook} from "./ILicenceHook.sol";

/// @title ReputationFloorLicenceHook
/// @notice Reference `ILicenceHook` implementation: rejects consumption from a consumer whose
/// `ReputationRegistry.effectiveScore` is below a declared floor. The licence-account analogue of
/// `IntegrityKernel`'s reputation-floor precondition -- same underlying registry, same
/// `effectiveScore` read, deliberately NOT the same caching strategy.
/// @dev **Reads `effectiveScore` LIVE on every call, no epoch-snapshot cache.**
/// `IntegrityKernel.preCheck` caches (see that contract's own doc comment) specifically to bring
/// its gas cost back under the whitepaper's Table 4 ceiling for ERC-4337 bundler simulation.
/// `LicenceAccount.consume()` is not subject to that same ceiling -- it is not an ERC-4337
/// validation-phase call -- so this hook takes the simpler, always-current-data path instead.
/// This is a disclosed design choice, not an oversight: if a future deployment needs this hook's
/// gas cost bounded for some other reason, that is separately-scoped follow-on work.
/// @dev One hook instance may serve multiple `LicenceAccount`s (the `account` parameter is
/// accepted but unused by this particular hook's logic -- reputation is checked against the
/// `consumer`, not the licence account itself; kept in the signature only because `ILicenceHook`
/// requires it for hooks that DO need per-account context).
contract ReputationFloorLicenceHook is ILicenceHook {
    error ReputationBelowFloor(address consumer, uint256 score, uint256 floor);

    ReputationRegistry public immutable reputationRegistry;
    uint256 public immutable minEffectiveScore;

    constructor(ReputationRegistry reputationRegistry_, uint256 minEffectiveScore_) {
        reputationRegistry = reputationRegistry_;
        minEffectiveScore = minEffectiveScore_;
    }

    function preConsume(address, address consumer, uint256, uint256) external view {
        uint256 score = reputationRegistry.effectiveScore(consumer);
        if (score < minEffectiveScore) revert ReputationBelowFloor(consumer, score, minEffectiveScore);
    }
}
