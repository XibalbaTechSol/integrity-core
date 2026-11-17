// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAccount
/// @notice Minimal interface every SovereignAgent-style on-chain account must implement.
/// @dev Deliberately NOT an ERC-4337 `IAccount` (no `validateUserOp`/EntryPoint dependency).
///      The interface contract (docs/INTERFACE_CONTRACT.md) does not specify an EntryPoint
///      deployment or bundler infra anywhere, and pulling in ERC-4337 here would add an
///      entire subsystem (EntryPoint, paymasters, bundler assumptions) that no other
///      package in this monorepo talks to. Off-chain identity (the Ed25519 DID keypair,
///      see §4.1) is managed by integrity-sdk; this on-chain account is controlled by a
///      plain secp256k1 EOA/multisig "controller" address, and links to the off-chain DID
///      only by storing its string form for indexers. If ERC-4337 support is wanted later,
///      it can be layered on as an additional entrypoint without changing this interface.
interface IAccount {
    /// @notice Executes an arbitrary call on behalf of the agent. Restricted to the
    /// current controller (see SovereignAgent.onlyController).
    function execute(address target, uint256 value, bytes calldata data) external returns (bytes memory);

    /// @notice The off-chain DID string (`did:integrity:<fingerprint>`) this account is
    /// linked to. Returned as a string rather than reconstructed on-chain because DID
    /// fingerprints are derived from an Ed25519 public key (see §4.1), and Ed25519 point
    /// encoding/hashing is not something we redundantly re-derive in Solidity — the
    /// binding is asserted once at registration time and trusted from there.
    function agentDID() external view returns (string memory);
}
