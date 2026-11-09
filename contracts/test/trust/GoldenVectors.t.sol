// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";

/// @notice Cross-repo golden vector: the Cortex/Python side must reproduce this exact bytes32.
contract GoldenVectorsTest is Test {
    function test_leafOf_matchesPinnedBytes() public {
        PolicyRegistry r = new PolicyRegistry(address(this));
        // fromNode=bytes32(1), relation=bytes32(2), toNode=bytes32(3), selector=0xa9059cbb, riskWeightBps=500
        bytes32 pinned = 0x75c5b80759eddce46001183197feef275527c521505740761d6b98693345cb5f;
        assertEq(
            r.leafOf(bytes32(uint256(1)), bytes32(uint256(2)), bytes32(uint256(3)), bytes4(0xa9059cbb), 500), pinned
        );
    }
}
