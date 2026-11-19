// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IOperationContext } from "./IOperationContext.sol";

/// @title SafeOperationContext
/// @notice Implements IOperationContext for Safe v1.4.1 accounts under Safe7579.
/// Dispatches roles path-based:
/// - When IntegrityGuard is active (direct Safe execTransaction): Role.Owner
/// - When marked for maintenance: Role.Maintenance
/// - Otherwise during standard 4337 execution: Role.Session
contract SafeOperationContext is IOperationContext {
    error Unauthorized();
    error GuardAlreadySet();

    address public immutable admin;
    address public integrityGuard;

    mapping(address => bool) public isDirectExecution;
    mapping(address => bool) public isMaintenanceExecution;
    mapping(address => bytes) internal _coSignatures;

    modifier onlyGuardOrAdmin() {
        if (msg.sender != integrityGuard && msg.sender != admin) revert Unauthorized();
        _;
    }

    constructor(address admin_) {
        admin = admin_;
    }

    function setIntegrityGuard(address guard_) external {
        if (msg.sender != admin) revert Unauthorized();
        if (integrityGuard != address(0)) revert GuardAlreadySet();
        integrityGuard = guard_;
    }

    function setDirectExecution(address account, bool active) external onlyGuardOrAdmin {
        isDirectExecution[account] = active;
    }

    function setMaintenanceExecution(address account, bool active) external onlyGuardOrAdmin {
        isMaintenanceExecution[account] = active;
    }

    function setCoSignature(address account, bytes calldata coSig) external onlyGuardOrAdmin {
        _coSignatures[account] = coSig;
    }

    function clearCoSignature(address account) external onlyGuardOrAdmin {
        delete _coSignatures[account];
    }

    /// @inheritdoc IOperationContext
    function roleOf(address account) external view override returns (Role) {
        if (account == address(0)) {
            return Role.None;
        }
        if (isMaintenanceExecution[account]) {
            return Role.Maintenance;
        }
        if (isDirectExecution[account]) {
            return Role.Owner;
        }
        return Role.Session;
    }

    /// @inheritdoc IOperationContext
    function coSignatureOf(address account) external view override returns (bytes memory) {
        return _coSignatures[account];
    }
}
