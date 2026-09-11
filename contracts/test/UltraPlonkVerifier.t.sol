// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.21;

import {Test} from "forge-std/Test.sol";
import {UltraPlonkVerifier} from "../src/oracle/UltraPlonkVerifier.sol";

contract UltraPlonkVerifierTest is Test {
    UltraPlonkVerifier private verifier;

    function setUp() public {
        verifier = new UltraPlonkVerifier();
    }

    function test_valid_fixture_is_accepted() public view {
        (bytes memory proof, bytes32[] memory publicInputs) = _fixture();
        assertTrue(verifier.verify(proof, publicInputs));
    }

    function test_tampered_proof_is_rejected() public view {
        (bytes memory proof, bytes32[] memory publicInputs) = _fixture();
        proof[0] = bytes1(uint8(proof[0]) ^ 1);
        assertFalse(_verifyNoRevert(proof, publicInputs));
    }

    function test_tampered_public_input_is_rejected() public view {
        (bytes memory proof, bytes32[] memory publicInputs) = _fixture();
        publicInputs[0] = bytes32(uint256(publicInputs[0]) ^ 1);
        assertFalse(_verifyNoRevert(proof, publicInputs));
    }

    function test_malformed_proof_is_rejected() public view {
        (bytes memory proof, bytes32[] memory publicInputs) = _fixture();
        bytes memory malformed = new bytes(proof.length - 1);
        for (uint256 i; i < malformed.length; ++i) {
            malformed[i] = proof[i];
        }
        assertFalse(_verifyNoRevert(malformed, publicInputs));
    }

    function _fixture() private view returns (bytes memory proof, bytes32[] memory publicInputs) {
        proof = vm.readFileBinary("test/fixtures/ultraplonk/proof.bin");
        assertEq(proof.length, 8000);
        assertEq(keccak256(proof), 0x2320b36152cce9c447862786371ec65151f986fd7a54903df01defd7be99798a);
        bytes memory rawInputs = vm.readFileBinary("test/fixtures/ultraplonk/public_inputs.bin");
        assertEq(rawInputs.length, 192);
        assertEq(keccak256(rawInputs), 0x5d12387962bcde4dcabad88c2606f8661e1f346465144fb06259cd9abdf163b7);
        publicInputs = new bytes32[](6);
        assembly ("memory-safe") {
            mstore(add(publicInputs, 0x20), mload(add(rawInputs, 0x20)))
            mstore(add(publicInputs, 0x40), mload(add(rawInputs, 0x40)))
            mstore(add(publicInputs, 0x60), mload(add(rawInputs, 0x60)))
            mstore(add(publicInputs, 0x80), mload(add(rawInputs, 0x80)))
            mstore(add(publicInputs, 0xa0), mload(add(rawInputs, 0xa0)))
            mstore(add(publicInputs, 0xc0), mload(add(rawInputs, 0xc0)))
        }
    }

    function _verifyNoRevert(bytes memory proof, bytes32[] memory publicInputs) private view returns (bool) {
        try verifier.verify(proof, publicInputs) returns (bool verified) {
            return verified;
        } catch {
            return false;
        }
    }
}
