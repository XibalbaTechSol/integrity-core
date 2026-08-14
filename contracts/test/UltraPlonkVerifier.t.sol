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
        for (uint256 i; i < malformed.length; ++i) malformed[i] = proof[i];
        assertFalse(_verifyNoRevert(malformed, publicInputs));
    }

    function _fixture() private view returns (bytes memory proof, bytes32[] memory publicInputs) {
        proof = vm.readFileBinary("test/fixtures/ultraplonk/proof.bin");
        assertEq(proof.length, 8000);
        assertEq(keccak256(proof), 0x8772b7d10a4d6ec27b8a8cc8f5c24c6893f73697a75b880a99916fb21029f04a);
        bytes memory rawInputs = vm.readFileBinary("test/fixtures/ultraplonk/public_inputs.bin");
        assertEq(rawInputs.length, 96);
        assertEq(keccak256(rawInputs), 0xc3657226c528dfdbcf724b2351c5293f26f30e66b67aa500a0faadecace51da1);
        publicInputs = new bytes32[](3);
        assembly {
            mstore(add(publicInputs, 0x20), mload(add(rawInputs, 0x20)))
            mstore(add(publicInputs, 0x40), mload(add(rawInputs, 0x40)))
            mstore(add(publicInputs, 0x60), mload(add(rawInputs, 0x60)))
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
