// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IOperationContext } from "../../../src/wallet/IOperationContext.sol";

contract MockOperationContext is IOperationContext {
    mapping(address => Role) public roles;
    mapping(address => bytes) public coSignatures;

    function setRole(address account, Role role) external {
        roles[account] = role;
    }

    function setCoSignature(address account, bytes calldata sig) external {
        coSignatures[account] = sig;
    }

    function roleOf(address account) external view override returns (Role) {
        return roles[account];
    }

    function coSignatureOf(address account) external view override returns (bytes memory) {
        return coSignatures[account];
    }
}
