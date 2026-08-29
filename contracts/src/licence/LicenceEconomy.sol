// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IntegrityToken} from "../oracle/IntegrityToken.sol";

/// @title LicenceEconomy
/// @notice Native-fee router for metered licence settlement.
/// @dev A `LicenceAccount` can use this contract as its `protocolFeeRecipient` without
/// changing its existing zero-data native transfer. The sender (the account) is mapped to
/// an adapter by governance, allowing the router to attribute the adapter-author share.
/// Fee shares are delayed before activation; stake rewards are paid in the native fee asset.
/// Buyback execution is an explicit, bounded external call and burns only ITK received by
/// this contract in that call. This contract does not pretend to be a price oracle or DEX.
contract LicenceEconomy is Ownable2Step, ReentrancyGuard {
    using SafeERC20 for IERC20;
    uint256 public constant BPS = 10_000;
    uint256 public constant PRECISION = 1e18;
    uint256 public constant FEE_SHARE_DELAY = 2 days;

    IERC20 public immutable itk;

    uint256 public adapterAuthorBps;
    uint256 public stakerBps;
    uint256 public buybackBps;
    uint256 public treasuryBps;

    uint256 public pendingAdapterAuthorBps;
    uint256 public pendingStakerBps;
    uint256 public pendingBuybackBps;
    uint256 public pendingTreasuryBps;
    uint256 public pendingFeeSharesEta;

    mapping(address account => address adapter) public licenceAdapter;
    mapping(address adapter => address author) public adapterAuthor;
    mapping(address author => uint256 amount) public authorRewards;
    uint256 public treasuryReserve;
    uint256 public buybackReserve;

    mapping(address staker => uint256 amount) public staked;
    mapping(address staker => uint256 rewardDebt) public rewardDebt;
    uint256 public totalStaked;
    uint256 public accNativeRewardPerShare;

    event LicenceAdapterBound(address indexed account, address indexed adapter);
    event AdapterAuthorSet(address indexed adapter, address indexed author);
    event FeeReceived(address indexed source, uint256 amount, uint256 authorAmount, uint256 stakerAmount, uint256 buybackAmount, uint256 treasuryAmount);
    event FeeSharesProposed(uint256 adapterAuthorBps, uint256 stakerBps, uint256 buybackBps, uint256 treasuryBps, uint256 eta);
    event FeeSharesActivated(uint256 adapterAuthorBps, uint256 stakerBps, uint256 buybackBps, uint256 treasuryBps);
    event Staked(address indexed staker, uint256 amount);
    event Unstaked(address indexed staker, uint256 amount);
    event StakerRewardClaimed(address indexed staker, uint256 amount);
    event AuthorRewardClaimed(address indexed author, uint256 amount);
    event TreasuryWithdrawn(address indexed to, uint256 amount);
    event BuybackAndBurn(address indexed executor, uint256 nativeAmount, uint256 itkBurned);

    error InvalidFeeShares();
    error FeeSharesNotReady(uint256 eta);
    error ZeroAddress();
    error ZeroAmount();
    error InsufficientStake();
    error InsufficientReward();
    error BuybackSlippage(uint256 received, uint256 minimum);
    error BuybackFailed(bytes returndata);
    error NoAuthorForAdapter(address adapter);
    error PayoutFailed();

    constructor(address owner_, address itk_, uint256 authorBps_, uint256 stakerBps_, uint256 buybackBps_, uint256 treasuryBps_)
        Ownable(owner_)
    {
        if (itk_ == address(0)) revert ZeroAddress();
        itk = IERC20(itk_);
        _validateShares(authorBps_, stakerBps_, buybackBps_, treasuryBps_);
        adapterAuthorBps = authorBps_;
        stakerBps = stakerBps_;
        buybackBps = buybackBps_;
        treasuryBps = treasuryBps_;
    }

    receive() external payable {
        _routeFee(msg.sender, msg.value);
    }

    function setAdapterAuthor(address adapter, address author) external onlyOwner {
        if (adapter == address(0) || author == address(0)) revert ZeroAddress();
        adapterAuthor[adapter] = author;
        emit AdapterAuthorSet(adapter, author);
    }

    function bindLicenceAdapter(address account, address adapter) external onlyOwner {
        if (account == address(0) || adapter == address(0)) revert ZeroAddress();
        if (adapterAuthor[adapter] == address(0)) revert NoAuthorForAdapter(adapter);
        licenceAdapter[account] = adapter;
        emit LicenceAdapterBound(account, adapter);
    }

    /// @notice Delayed governance change to the economic allocation, preserving a review window.
    function proposeFeeShares(uint256 authorBps_, uint256 stakerBps_, uint256 buybackBps_, uint256 treasuryBps_)
        external
        onlyOwner
    {
        _validateShares(authorBps_, stakerBps_, buybackBps_, treasuryBps_);
        pendingAdapterAuthorBps = authorBps_;
        pendingStakerBps = stakerBps_;
        pendingBuybackBps = buybackBps_;
        pendingTreasuryBps = treasuryBps_;
        pendingFeeSharesEta = block.timestamp + FEE_SHARE_DELAY;
        emit FeeSharesProposed(authorBps_, stakerBps_, buybackBps_, treasuryBps_, pendingFeeSharesEta);
    }

    function activateFeeShares() external {
        uint256 eta = pendingFeeSharesEta;
        if (eta == 0 || block.timestamp < eta) revert FeeSharesNotReady(eta);
        adapterAuthorBps = pendingAdapterAuthorBps;
        stakerBps = pendingStakerBps;
        buybackBps = pendingBuybackBps;
        treasuryBps = pendingTreasuryBps;
        delete pendingFeeSharesEta;
        emit FeeSharesActivated(adapterAuthorBps, stakerBps, buybackBps, treasuryBps);
    }

    function stake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        _claimStaker(msg.sender);
        itk.safeTransferFrom(msg.sender, address(this), amount);
        staked[msg.sender] += amount;
        totalStaked += amount;
        rewardDebt[msg.sender] = (staked[msg.sender] * accNativeRewardPerShare) / PRECISION;
        emit Staked(msg.sender, amount);
    }

    function unstake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        if (staked[msg.sender] < amount) revert InsufficientStake();
        _claimStaker(msg.sender);
        staked[msg.sender] -= amount;
        totalStaked -= amount;
        rewardDebt[msg.sender] = (staked[msg.sender] * accNativeRewardPerShare) / PRECISION;
        itk.safeTransfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    function claimStakerReward() external nonReentrant returns (uint256 amount) {
        amount = _claimStaker(msg.sender);
    }

    function claimAuthorReward() external nonReentrant returns (uint256 amount) {
        amount = authorRewards[msg.sender];
        if (amount == 0) revert InsufficientReward();
        authorRewards[msg.sender] = 0;
        (bool success,) = payable(msg.sender).call{value: amount}("");
        if (!success) revert PayoutFailed();
        emit AuthorRewardClaimed(msg.sender, amount);
    }

    function withdrawTreasury(address payable to, uint256 amount) external onlyOwner nonReentrant {
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (treasuryReserve < amount) revert InsufficientReward();
        treasuryReserve -= amount;
        (bool success,) = to.call{value: amount}("");
        if (!success) revert PayoutFailed();
        emit TreasuryWithdrawn(to, amount);
    }

    /// @notice Executes a governance-selected buyback call and burns only ITK received by this
    /// router. The minimum output protects the reserve from an underfilled execution; the executor
    /// and calldata are intentionally external because no DEX/oracle is protocol-owned here.
    function buybackAndBurn(address payable executor, uint256 nativeAmount, uint256 minimumItkOut, bytes calldata data)
        external
        onlyOwner
        nonReentrant
        returns (uint256 itkBurned)
    {
        if (executor == address(0)) revert ZeroAddress();
        if (nativeAmount == 0) revert ZeroAmount();
        if (buybackReserve < nativeAmount) revert InsufficientReward();
        buybackReserve -= nativeAmount;
        uint256 beforeBalance = itk.balanceOf(address(this));
        (bool success, bytes memory returndata) = executor.call{value: nativeAmount}(data);
        if (!success) revert BuybackFailed(returndata);
        itkBurned = itk.balanceOf(address(this)) - beforeBalance;
        if (itkBurned < minimumItkOut) revert BuybackSlippage(itkBurned, minimumItkOut);
        IntegrityToken(address(itk)).burn(itkBurned);
        emit BuybackAndBurn(executor, nativeAmount, itkBurned);
    }

    function _routeFee(address source, uint256 amount) internal {
        if (amount == 0) return;
        address author = adapterAuthor[licenceAdapter[source]];
        uint256 authorAmount = (amount * adapterAuthorBps) / BPS;
        if (author == address(0)) {
            authorAmount = 0;
        } else {
            authorRewards[author] += authorAmount;
        }
        uint256 stakerAmount = (amount * stakerBps) / BPS;
        uint256 buybackAmount = (amount * buybackBps) / BPS;
        uint256 treasuryAmount = amount - authorAmount - stakerAmount - buybackAmount;
        if (totalStaked > 0 && stakerAmount > 0) {
            accNativeRewardPerShare += (stakerAmount * PRECISION) / totalStaked;
        } else {
            treasuryAmount += stakerAmount;
            stakerAmount = 0;
        }
        buybackReserve += buybackAmount;
        treasuryReserve += treasuryAmount;
        emit FeeReceived(source, amount, authorAmount, stakerAmount, buybackAmount, treasuryAmount);
    }

    function _claimStaker(address staker) internal returns (uint256 amount) {
        uint256 accrued = (staked[staker] * accNativeRewardPerShare) / PRECISION;
        amount = accrued - rewardDebt[staker];
        rewardDebt[staker] = accrued;
        if (amount > 0) {
            (bool success,) = payable(staker).call{value: amount}("");
            if (!success) revert PayoutFailed();
            emit StakerRewardClaimed(staker, amount);
        }
    }

    function _validateShares(uint256 authorBps_, uint256 stakerBps_, uint256 buybackBps_, uint256 treasuryBps_)
        internal
        pure
    {
        if (authorBps_ + stakerBps_ + buybackBps_ + treasuryBps_ != BPS) revert InvalidFeeShares();
    }
}
