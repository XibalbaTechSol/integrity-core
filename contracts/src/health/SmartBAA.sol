// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title SmartBAA
/// @notice An on-chain Business Associate Agreement: a HIPAA Covered Entity and a
/// Sovereign Agent (acting as the Business Associate) post a hash of their off-chain
/// legal agreement, and the agent posts $ITK collateral that can be slashed to the
/// covered entity if an arbitrator finds a breach.
/// @dev One instance per (coveredEntity, businessAssociate) pair, deployed by
/// SmartBAAFactory — never constructed directly, so `entityRegistry`-gating of who may
/// even become a covered entity happens once, at the factory, rather than being
/// re-checked (or forgotten) in every instance.
///
/// Collateral model is intentionally simple (a single ITK balance held by this
/// contract), unlike the old prototype's ISOLATED/POOLED escrow split against a shared
/// staking vault — pooled collateral shared across many BAAs means a slash on one
/// agreement can be starved by withdrawals from an unrelated one. Isolated,
/// per-agreement collateral can't have that cross-contamination: what's locked here is
/// only ever this agreement's.
contract SmartBAA is ReentrancyGuard {
    using SafeERC20 for IERC20;

    enum Status {
        Proposed,
        Active,
        Disputed,
        Terminated
    }

    address public immutable coveredEntity;
    address public immutable businessAssociate;
    address public immutable arbitrator;
    bytes32 public immutable agreementHash;
    uint256 public immutable requiredCollateral;
    IERC20 public immutable itk;

    Status public status;

    event BAASigned(address indexed businessAssociate, uint256 collateral);
    event DisputeRaised(address indexed coveredEntity);
    event DisputeResolved(bool slashed);
    event BAARevoked(address indexed by);

    error NotCoveredEntity();
    error NotBusinessAssociate();
    error NotArbitrator();
    error WrongStatus(Status current);

    modifier onlyCE() {
        if (msg.sender != coveredEntity) revert NotCoveredEntity();
        _;
    }

    modifier onlyBA() {
        if (msg.sender != businessAssociate) revert NotBusinessAssociate();
        _;
    }

    modifier onlyArbitrator() {
        if (msg.sender != arbitrator) revert NotArbitrator();
        _;
    }

    constructor(
        address _coveredEntity,
        address _businessAssociate,
        address _arbitrator,
        bytes32 _agreementHash,
        uint256 _requiredCollateral,
        address _itk
    ) {
        coveredEntity = _coveredEntity;
        businessAssociate = _businessAssociate;
        arbitrator = _arbitrator;
        agreementHash = _agreementHash;
        requiredCollateral = _requiredCollateral;
        itk = IERC20(_itk);
        status = Status.Proposed;
    }

    /// @notice The business associate posts collateral and activates the agreement.
    function sign() external onlyBA nonReentrant {
        if (status != Status.Proposed) revert WrongStatus(status);
        status = Status.Active;
        itk.safeTransferFrom(msg.sender, address(this), requiredCollateral);
        emit BAASigned(msg.sender, requiredCollateral);
    }

    /// @notice The covered entity flags a suspected breach, freezing the agreement
    /// (collateral can no longer be returned via `revoke`) pending arbitration.
    function raiseDispute() external onlyCE {
        if (status != Status.Active) revert WrongStatus(status);
        status = Status.Disputed;
        emit DisputeRaised(msg.sender);
    }

    /// @notice The arbitrator (set once at deployment — see SmartBAAFactory, expected to
    /// be a neutral/governance address, not either party) resolves an open dispute.
    /// @param slash If true, all posted collateral is transferred to the covered entity
    /// as compensation and the agreement terminates. If false, the dispute is dismissed
    /// and the agreement returns to Active — a dismissed accusation shouldn't
    /// automatically end an otherwise-compliant business relationship.
    function arbitrate(bool slash) external onlyArbitrator nonReentrant {
        if (status != Status.Disputed) revert WrongStatus(status);

        if (slash) {
            status = Status.Terminated;
            uint256 balance = itk.balanceOf(address(this));
            if (balance > 0) {
                itk.safeTransfer(coveredEntity, balance);
            }
        } else {
            status = Status.Active;
        }

        emit DisputeResolved(slash);
    }

    /// @notice Either party can end the agreement by mutual absence of dispute —
    /// collateral returns to the business associate. Cannot be called while Disputed,
    /// so a party under active accusation can't dodge arbitration by unilaterally
    /// revoking.
    function revoke() external nonReentrant {
        if (msg.sender != coveredEntity && msg.sender != businessAssociate) revert NotCoveredEntity();
        if (status != Status.Active) revert WrongStatus(status);
        status = Status.Terminated;

        uint256 balance = itk.balanceOf(address(this));
        if (balance > 0) {
            itk.safeTransfer(businessAssociate, balance);
        }
        emit BAARevoked(msg.sender);
    }
}
