// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title ITK (Integrity Token)
/// @notice Capped, role-minted ERC20 for the Integrity Protocol v2 trust layer.
/// @dev Plain singleton, not a clone or proxy. Mirrors the audited `IntegrityToken`
/// shape (src/oracle/IntegrityToken.sol) with no transfer fee and no transfer hooks.
/// `totalMinted` is a lifetime counter that burning never decrements, so the cap bounds
/// issuance rather than circulating supply.
contract ITK is ERC20, ERC20Burnable, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    uint256 public constant MAX_SUPPLY = 100_000_000 ether;

    /// @notice Cumulative amount ever minted. Tracked separately from `totalSupply()`
    /// so burning does not reopen mint headroom.
    uint256 public totalMinted;

    error ExceedsMaxSupply(uint256 requested, uint256 remaining);
    error ZeroAmount();

    constructor(address admin, uint256 initialMint) ERC20("Integrity Token", "ITK") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, admin);

        if (initialMint > 0) {
            if (initialMint > MAX_SUPPLY) revert ExceedsMaxSupply(initialMint, MAX_SUPPLY);
            totalMinted = initialMint;
            _mint(admin, initialMint);
        }
    }

    /// @notice Mints new ITK, capped at MAX_SUPPLY over lifetime issuance. Burning
    /// reduces circulating supply but does not restore mint headroom.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        if (amount == 0) revert ZeroAmount();
        if (totalMinted + amount > MAX_SUPPLY) {
            revert ExceedsMaxSupply(amount, MAX_SUPPLY - totalMinted);
        }
        totalMinted += amount;
        _mint(to, amount);
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override(AccessControl) returns (bool) {
        return super.supportsInterface(interfaceId);
    }
}
