// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAnchorPolicy} from "../../src/core/IAnchorPolicy.sol";
import {IExecutionPolicy} from "../../src/core/IExecutionPolicy.sol";

/// @dev Test doubles for SPEC.md §5.3 policy chokepoints.
contract AllowAnchorPolicy is IAnchorPolicy {
    function checkAnchor(address, bytes32, uint256) external pure returns (bool) {
        return true;
    }
}

contract DenyAnchorPolicy is IAnchorPolicy {
    function checkAnchor(address, bytes32, uint256) external pure returns (bool) {
        return false;
    }
}

contract RevertAnchorPolicy is IAnchorPolicy {
    error AnchorPolicyReverted();

    function checkAnchor(address, bytes32, uint256) external pure returns (bool) {
        revert AnchorPolicyReverted();
    }
}

contract AllowExecutionPolicy is IExecutionPolicy {
    function checkExecution(address, address, address, uint256, bytes calldata, uint256)
        external
        pure
        returns (bool)
    {
        return true;
    }
}

contract DenyExecutionPolicy is IExecutionPolicy {
    function checkExecution(address, address, address, uint256, bytes calldata, uint256)
        external
        pure
        returns (bool)
    {
        return false;
    }
}

contract RevertExecutionPolicy is IExecutionPolicy {
    error ExecutionPolicyReverted();

    function checkExecution(address, address, address, uint256, bytes calldata, uint256)
        external
        pure
        returns (bool)
    {
        revert ExecutionPolicyReverted();
    }
}

contract Sink {
    uint256 public hits;

    function ping() external payable {
        hits += 1;
    }
}
