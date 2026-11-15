// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IEd25519Verifier
/// @notice Proof kind 2 of `AgentRegistry`: verifies an Ed25519 signature on chain. Governance sets
/// an audited implementation; until it does, kind 2 is disabled (agent registration v3, Part 3).
interface IEd25519Verifier {
    /// @param pubkey Raw 32-byte Ed25519 public key.
    /// @param digest The 32-byte EIP-712 digest the agent signed.
    /// @param signature The 64-byte Ed25519 signature.
    function verify(bytes32 pubkey, bytes32 digest, bytes calldata signature) external view returns (bool);
}
