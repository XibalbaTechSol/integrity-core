// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PredictionMarket
 * @dev A simple automated market maker (AMM) for binary outcome prediction markets.
 * This contract enables users to buy YES or NO shares for a specific event.
 * It is designed to be resolved by a sovereign AI agent acting as an oracle.
 */
contract PredictionMarket {
    address public admin;
    address public aiOracle;

    string public question;
    uint256 public endTime;
    
    bool public isResolved;
    bool public outcome; // true = YES, false = NO

    // Market liquidity pools
    uint256 public yesPool;
    uint256 public noPool;
    
    // User balances mapping: user => (YES shares, NO shares)
    mapping(address => uint256) public yesShares;
    mapping(address => uint256) public noShares;

    event SharesPurchased(address indexed buyer, bool isYes, uint256 amount);
    event MarketResolved(bool outcome);
    event WinningsClaimed(address indexed user, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can call this");
        _;
    }

    modifier onlyOracle() {
        require(msg.sender == aiOracle, "Only AI Oracle can call this");
        _;
    }

    constructor(string memory _question, uint256 _endTime, address _aiOracle) {
        admin = msg.sender;
        question = _question;
        endTime = _endTime;
        aiOracle = _aiOracle;
        
        // Initialize pool with some base liquidity
        yesPool = 1000 ether;
        noPool = 1000 ether;
    }

    /**
     * @dev Buy shares for a specific outcome.
     * Uses a simple constant product formula (xy = k) for pricing.
     * In a production environment, use LMSR (Logarithmic Market Scoring Rule) or CPMM.
     */
    function buyShares(bool _isYes) external payable {
        require(block.timestamp < endTime, "Market has ended");
        require(!isResolved, "Market already resolved");
        require(msg.value > 0, "Must send ETH to buy shares");

        uint256 sharesToMint;

        if (_isYes) {
            // How many YES shares does msg.value buy?
            uint256 newYesPool = yesPool + msg.value;
            sharesToMint = (msg.value * noPool) / newYesPool;
            yesPool = newYesPool;
            yesShares[msg.sender] += sharesToMint;
        } else {
            // How many NO shares does msg.value buy?
            uint256 newNoPool = noPool + msg.value;
            sharesToMint = (msg.value * yesPool) / newNoPool;
            noPool = newNoPool;
            noShares[msg.sender] += sharesToMint;
        }

        emit SharesPurchased(msg.sender, _isYes, sharesToMint);
    }

    /**
     * @dev Resolves the market. Only callable by the AI Oracle.
     */
    function resolveMarket(bool _outcome) external onlyOracle {
        require(block.timestamp >= endTime, "Market has not ended yet");
        require(!isResolved, "Market already resolved");
        
        isResolved = true;
        outcome = _outcome;
        
        emit MarketResolved(_outcome);
    }

    /**
     * @dev Claim winnings if you held shares of the winning outcome.
     */
    function claimWinnings() external {
        require(isResolved, "Market not resolved yet");
        
        uint256 payout = 0;
        
        if (outcome == true) {
            uint256 shares = yesShares[msg.sender];
            require(shares > 0, "No winning shares");
            yesShares[msg.sender] = 0; // Prevent re-entrancy
            // Simple payout calculation (for demonstration)
            payout = shares; 
        } else {
            uint256 shares = noShares[msg.sender];
            require(shares > 0, "No winning shares");
            noShares[msg.sender] = 0; // Prevent re-entrancy
            // Simple payout calculation (for demonstration)
            payout = shares;
        }

        // Transfer funds
        (bool success, ) = payable(msg.sender).call{value: payout}("");
        require(success, "Transfer failed");
        
        emit WinningsClaimed(msg.sender, payout);
    }
}
