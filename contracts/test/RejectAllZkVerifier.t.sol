// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {RejectAllZkVerifier} from "../src/oracle/RejectAllZkVerifier.sol";

/// @notice The genesis verifier after ZK was retired must never accept anything: a proof that
/// verifies would re-open the ZK reputation boost with no circuit behind it.
contract RejectAllZkVerifierTest is Test {
    RejectAllZkVerifier verifier = new RejectAllZkVerifier();

    function test_rejectsEmptyProof() public view {
        assertFalse(verifier.verify("", new bytes32[](0)));
    }

    function testFuzz_rejectsEveryProof(bytes calldata proof, bytes32[] calldata publicInputs) public view {
        assertFalse(verifier.verify(proof, publicInputs));
    }
}
