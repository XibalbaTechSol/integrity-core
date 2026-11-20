// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title SessionPolicyLib
/// @notice Validation rules for Integrity agent Smart Sessions.
/// Enforces Invariant I4 / F4: session keys must NEVER be granted ERC-7739 / ERC-1271 signing capabilities,
/// preventing ephemeral keys from validating arbitrary off-chain digests or authorizations.
library SessionPolicyLib {
    error Erc7739PoliciesForbidden();

    struct PolicyData {
        address policy;
        bytes initData;
    }

    struct ActionData {
        bytes4 actionTargetSelector;
        address actionTarget;
        PolicyData[] actionPolicies;
    }

    struct ERC7739Context {
        bytes32 appDomainSeparator;
        string[] contentNames;
    }

    struct ERC7739Data {
        ERC7739Context[] allowedERC7739Content;
        PolicyData[] erc1271Policies;
    }

    struct Session {
        address sessionValidator;
        bytes sessionValidatorInitData;
        bytes32 salt;
        PolicyData[] userOpPolicies;
        ERC7739Data erc7739Policies;
        ActionData[] actions;
    }

    /// @notice Validates that a proposed session configuration conforms to Integrity safety invariants.
    function validateSession(Session memory session) internal pure {
        if (
            session.erc7739Policies.allowedERC7739Content.length != 0
                || session.erc7739Policies.erc1271Policies.length != 0
        ) {
            revert Erc7739PoliciesForbidden();
        }
    }
}
