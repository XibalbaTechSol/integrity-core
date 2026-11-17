// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IExecutionPolicy} from "./IExecutionPolicy.sol";

/// @dev The `AISRegistry.latest(agent)` getter: (score bps 0..10000, windowEnd, evidenceRoot).
interface IAisCheckpoints {
    function latest(address agent) external view returns (uint32 score, uint64 windowEnd, bytes32 evidenceRoot);
}

/// @title ConstraintExecutionPolicy
/// @notice Reference IExecutionPolicy: AIS floor, native-value cap, target allowlist, ERC-20/721 caps (M1).
/// @dev The AIS floor reads the agent's latest `AISRegistry` checkpoint score, in basis points
/// (0..10000), so `minAis` is in basis points too. `minAis == 0` disables the floor and never reads
/// the registry. With `minAis > 0` and no registry set, `check` denies (fail closed).
contract ConstraintExecutionPolicy is AccessControl, IExecutionPolicy {
    bytes4 private constant SEL_TRANSFER = 0xa9059cbb;
    bytes4 private constant SEL_APPROVE = 0x095ea7b3;
    bytes4 private constant SEL_TRANSFER_FROM = 0x23b872dd;
    bytes4 private constant SEL_SAFE_TRANSFER_FROM = 0x42842e0e;
    bytes4 private constant SEL_SAFE_TRANSFER_FROM_DATA = 0xb88d4fde;

    uint256 public minAis;
    /// @notice `AISRegistry` the floor reads. Admin-set after deploy (it is deployed later in genesis).
    IAisCheckpoints public aisRegistry;
    uint256 public maxValue;
    bool public enforceTargetAllowlist;
    bool public enforceTokenCaps;
    mapping(address => bool) public allowedTarget;
    mapping(address => uint256) public tokenOutCap;
    mapping(address => bool) public tokenKnown;

    event ConstraintsUpdated(uint256 minAis, uint256 maxValue, bool enforceTargetAllowlist);
    event TargetAllowed(address indexed target, bool allowed);
    event TokenCapSet(address indexed token, uint256 cap);
    event EnforceTokenCaps(bool enabled);
    event AisRegistrySet(address indexed aisRegistry);

    /// @dev A registry pin must be a contract (or zero to unset); a codeless pin would make `check`
    /// revert on the caller-side extcodesize check instead of returning a verdict.
    error NotAContract(address target);

    constructor(address admin, uint256 minAis_, uint256 maxValue_, bool enforceTargetAllowlist_) {
        require(admin != address(0), "ConstraintExecutionPolicy: zero admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        minAis = minAis_;
        maxValue = maxValue_;
        enforceTargetAllowlist = enforceTargetAllowlist_;
        emit ConstraintsUpdated(minAis_, maxValue_, enforceTargetAllowlist_);
    }

    function setConstraints(uint256 minAis_, uint256 maxValue_, bool enforceTargetAllowlist_)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        minAis = minAis_;
        maxValue = maxValue_;
        enforceTargetAllowlist = enforceTargetAllowlist_;
        emit ConstraintsUpdated(minAis_, maxValue_, enforceTargetAllowlist_);
    }

    function setAisRegistry(address r) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (r != address(0) && r.code.length == 0) revert NotAContract(r);
        aisRegistry = IAisCheckpoints(r);
        emit AisRegistrySet(r);
    }

    function setTarget(address target, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE) {
        allowedTarget[target] = allowed;
        emit TargetAllowed(target, allowed);
    }

    function setEnforceTokenCaps(bool enabled) external onlyRole(DEFAULT_ADMIN_ROLE) {
        enforceTokenCaps = enabled;
        emit EnforceTokenCaps(enabled);
    }

    function setTokenCap(address token, uint256 cap) external onlyRole(DEFAULT_ADMIN_ROLE) {
        tokenKnown[token] = true;
        tokenOutCap[token] = cap;
        emit TokenCapSet(token, cap);
    }

    function check(address agent, address target, uint256 value, bytes calldata data) external view returns (bool) {
        if (minAis != 0) {
            if (address(aisRegistry) == address(0)) return false;
            (uint32 score,,) = aisRegistry.latest(agent);
            if (score < minAis) return false;
        }
        if (maxValue != 0 && value > maxValue) return false;
        if (enforceTargetAllowlist && !allowedTarget[target]) return false;
        if (enforceTokenCaps && data.length >= 4) {
            (bool isTokenMove, uint256 amount) = _tokenAmount(data);
            if (isTokenMove) {
                if (!tokenKnown[target]) return false;
                if (amount > tokenOutCap[target]) return false;
            }
        }
        return true;
    }

    function _tokenAmount(bytes calldata data) private pure returns (bool isTokenMove, uint256 amount) {
        bytes4 sel = bytes4(data);
        if (sel == SEL_TRANSFER || sel == SEL_APPROVE) {
            if (data.length < 68) return (true, type(uint256).max);
            (, amount) = abi.decode(data[4:], (address, uint256));
            return (true, amount);
        }
        if (sel == SEL_TRANSFER_FROM || sel == SEL_SAFE_TRANSFER_FROM || sel == SEL_SAFE_TRANSFER_FROM_DATA) {
            if (data.length < 100) return (true, type(uint256).max);
            (,, amount) = abi.decode(data[4:100], (address, address, uint256));
            return (true, amount);
        }
        return (false, 0);
    }
}
