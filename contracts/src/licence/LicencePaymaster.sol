// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IEntryPoint, IPaymaster, PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";

/// @title LicencePaymaster
/// @notice An owner-funded, allowlisted ERC-4337 paymaster for experimental licence accounts.
/// @dev Sponsorship is deliberately constrained to explicitly approved senders and a maximum
/// per-UserOperation cost. Validation is stateless; the EntryPoint deposit is the only funded
/// sponsorship balance. This contract does not decide whether a licence action is authorized --
/// `LicenceAccount.validateUserOp()` remains authoritative for the account signature and call
/// surface.
contract LicencePaymaster is IPaymaster, Ownable2Step {
    error NotEntryPoint(address caller);
    error SenderNotSponsored(address sender);
    error MaxCostExceeded(uint256 maxCost, uint256 configuredMax);

    IEntryPoint public immutable entryPoint;
    uint256 public immutable maxSponsoredCost;
    mapping(address sender => bool approved) public sponsoredAccount;

    event SponsoredAccountUpdated(address indexed sender, bool approved);

    constructor(IEntryPoint entryPoint_, address owner_, uint256 maxSponsoredCost_)
        Ownable(owner_)
    {
        require(address(entryPoint_) != address(0), "zero entry point");
        require(maxSponsoredCost_ > 0, "zero max sponsored cost");
        entryPoint = entryPoint_;
        maxSponsoredCost = maxSponsoredCost_;
    }

    /// @notice Adds or removes a licence account from the sponsorship allowlist.
    function setSponsoredAccount(address sender, bool approved) external onlyOwner {
        sponsoredAccount[sender] = approved;
        emit SponsoredAccountUpdated(sender, approved);
    }

    /// @inheritdoc IPaymaster
    /// @dev Returns empty context because this policy has no post-operation accounting. The
    /// EntryPoint's actual gas charge is paid from this contract's deposit.
    function validatePaymasterUserOp(PackedUserOperation calldata userOp, bytes32, uint256 maxCost)
        external
        returns (bytes memory context, uint256 validationData)
    {
        _requireEntryPoint();
        if (!sponsoredAccount[userOp.sender]) revert SenderNotSponsored(userOp.sender);
        if (maxCost > maxSponsoredCost) revert MaxCostExceeded(maxCost, maxSponsoredCost);
        return (bytes(""), 0);
    }

    /// @inheritdoc IPaymaster
    function postOp(
        PostOpMode,
        bytes calldata,
        uint256,
        uint256
    ) external {
        _requireEntryPoint();
    }

    /// @notice Funds this paymaster's EntryPoint deposit.
    function deposit() external payable {
        entryPoint.depositTo{value: msg.value}(address(this));
    }

    /// @notice Withdraws unused sponsorship funds from the EntryPoint.
    function withdrawTo(address payable recipient, uint256 amount) external onlyOwner {
        entryPoint.withdrawTo(recipient, amount);
    }

    function getDeposit() external view returns (uint256) {
        return entryPoint.balanceOf(address(this));
    }

    function _requireEntryPoint() internal view {
        if (msg.sender != address(entryPoint)) revert NotEntryPoint(msg.sender);
    }
}
