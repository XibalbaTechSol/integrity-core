// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title IntegrityToken ($ITK)
/// @notice The staking/collateral asset for the Integrity Protocol: agents stake it in
/// `Slasher` to back their reputation, and lock it in `health/SmartBAA` as HIPAA
/// business-associate collateral.
/// @dev Plain capped-supply ERC20 with role-gated minting — no transfer fee, no
/// rebasing. The old prototype's ITK charged a fee-on-transfer (burn + treasury cut) on
/// every transfer; that silently breaks any contract that does
/// `transferFrom(x, address(this), amount)` and then trusts its own balance increased
/// by exactly `amount` (Slasher, SmartBAA and ReputationRegistry all do exactly that).
/// Rather than carry that accounting bug forward, fee-on-transfer is left out entirely;
/// if a protocol fee is wanted later it belongs in the contracts that move value
/// (Slasher/SmartBAA), where the accounting can account for it explicitly.
contract IntegrityToken is ERC20, ERC20Burnable, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    uint256 public constant MAX_SUPPLY = 100_000_000 ether;

    /// @notice Cumulative amount ever minted. Tracked separately from `totalSupply()`
    /// so the issuance cap is on lifetime minting, not circulating supply — otherwise
    /// burning tokens (e.g. a Slasher penalty) would silently reopen mint headroom,
    /// letting the protocol re-inflate supply it had deliberately destroyed.
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

    /// @notice Mints new ITK, capped at MAX_SUPPLY total ever minted (mint does not
    /// "un-cap" itself as tokens are burned — burning reduces circulating supply, not
    /// the lifetime issuance ceiling, which is what actually bounds dilution).
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
