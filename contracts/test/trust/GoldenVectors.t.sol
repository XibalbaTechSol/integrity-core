// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";

/// @notice Cross-repo golden vector: the Cortex/Python side must reproduce this exact bytes32.
/// @dev Leaf is the 6-field (192-byte) preimage after the target-binding redesign:
/// `keccak256(abi.encode(fromNode, relation, toNode, target, targetSelector, riskWeightBps))`.
/// The pinned value is independently reproduced with:
///   cast abi-encode 'x(bytes32,bytes32,bytes32,address,bytes4,uint16)' \
///     0x..01 0x..02 0x..03 0x00000000000000000000000000000000000000CA 0xa9059cbb 500 | cast keccak
/// => 0x58febd532cdbee740056933391a0fc3ca82d1d90cef567a211dc4e049ea138d0
contract GoldenVectorsTest is Test {
    /// @dev Fixed, documented target constant for the pinned vector.
    address constant GOLDEN_TARGET = address(0xCA);

    function test_leafOf_matchesPinnedBytes() public {
        PolicyRegistry r = new PolicyRegistry(address(this));
        // fromNode=bytes32(1), relation=bytes32(2), toNode=bytes32(3),
        // target=0x..CA, selector=0xa9059cbb, riskWeightBps=500
        bytes32 pinned = 0x58febd532cdbee740056933391a0fc3ca82d1d90cef567a211dc4e049ea138d0;
        assertEq(
            r.leafOf(
                bytes32(uint256(1)),
                bytes32(uint256(2)),
                bytes32(uint256(3)),
                GOLDEN_TARGET,
                bytes4(0xa9059cbb),
                500
            ),
            pinned
        );
    }
}
