// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IZkVerifier} from "./IZkVerifier.sol";

/// @title RejectAllZkVerifier
/// @notice The genesis ZK verifier after ZK proving was retired (docs/EXECUTION_PLAN.md, A1).
/// @dev `ReputationRegistry.submitZkAttestation` and the per-agent `VerifierRegistry` clones still
/// exist, because every agent registered so far depends on those templates until the Phase C
/// cutover. They need *some* verifier address, and a missing or zero verifier must never read as
/// "verified". This contract answers every proof with `false`, so the ZK reputation boost is
/// unreachable by construction, not by configuration. The generated `UltraPlonkVerifier` and its
/// Noir circuit moved to integrity-lab with the rest of the ZK tooling. Kernels deployed after A4
/// set `requireAssuranceTier = false` so they do not demand a boost that can no longer be earned.
contract RejectAllZkVerifier is IZkVerifier {
    function verify(bytes calldata, bytes32[] calldata) external pure returns (bool) {
        return false;
    }
}
