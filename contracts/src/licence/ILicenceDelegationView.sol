// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice Stable read model for a licence's delegated-use terms and consumer state.
/// @dev This is deliberately separate from the consuming hook: clients can inspect the
/// effective policy without being able to mutate or bypass enforcement.
struct LicenceDelegationView {
    bytes32 fieldOfUseHash;
    address requiredLicensee;
    bool exclusive;
    bool derivativeRights;
    uint256 minimumAssuranceTier;
    uint256 observedAssuranceTier;
    uint256 maximumActiveLicensees;
    uint256 activeLicenseeCount;
    address exclusiveLicensee;
    address consumer;
    bool allowedLicensee;
    bool activeLicensee;
    bytes32 initialMemoryHead;
    bytes32 memoryHead;
    uint256 memorySequence;
}

interface ILicenceDelegationView {
    function delegationView(address consumer) external view returns (LicenceDelegationView memory);
}
