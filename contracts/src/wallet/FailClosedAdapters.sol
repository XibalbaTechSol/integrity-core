// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IOperationContext } from "./IOperationContext.sol";
import { IAccountVerifier } from "./IAccountVerifier.sol";

/// @title FailClosedOperationContext
/// @notice Initial placeholder adapter for IntegrityHook.
/// Rejects all callers by returning Role.None and empty co-signature.
contract FailClosedOperationContext is IOperationContext {
    function roleOf(address) external pure override returns (Role) {
        return Role.None;
    }

    function coSignatureOf(address) external pure override returns (bytes memory) {
        return "";
    }
}

/// @title FailClosedAccountVerifier
/// @notice Initial placeholder verifier for AgentRegistry v3.
/// Rejects all accounts by returning genuine = false.
contract FailClosedAccountVerifier is IAccountVerifier {
    function verify(address) external pure override returns (bool genuine, address owner) {
        return (false, address(0));
    }
}
