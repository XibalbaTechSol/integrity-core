// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice Typed licence-term context used by the full Phase II policy hook.
struct LicenceTermsContext {
    bytes32 purposeHash;
    bool derivative;
    bytes32 priorMemoryHead;
    bytes32 nextMemoryHead;
    uint256 memorySequence;
    bytes32 evidenceHash;
}

/// @notice Extended precondition interface for the six non-metered licence terms.
interface ILicenceTermsHook {
    function preConsumeWithTerms(
        address account,
        address consumer,
        uint256 units,
        uint256 royaltyPaid,
        LicenceTermsContext calldata context
    ) external;
}
