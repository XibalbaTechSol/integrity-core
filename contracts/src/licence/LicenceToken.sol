// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title LicenceToken
/// @notice The ERC-721 a `LicenceAccount` (Phase II tracer-bullet slice,
/// `docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`) attaches to.
/// @dev Deliberately minimal -- mint-by-owner only, no marketplace, no per-token metadata beyond
/// what ERC-721 itself requires. This slice is proving "IP as a live, metered asset held in a
/// token-bound account," not building a licensing marketplace; a real marketplace is explicitly
/// out of scope, matching the proposal's own deferral list.
contract LicenceToken is ERC721, Ownable {
    uint256 public nextTokenId = 1;

    constructor(address admin) ERC721("Integrity Licence", "ILIC") Ownable(admin) {}

    /// @notice Mints the next licence NFT to `to`. Owner-gated (the deployer/operator, not
    /// permissionless) -- this slice does not implement a public sale/mint mechanism, since that
    /// is marketplace logic explicitly out of scope.
    function mint(address to) external onlyOwner returns (uint256 tokenId) {
        tokenId = nextTokenId++;
        _mint(to, tokenId);
    }
}
