// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title TrustConfig
/// @notice The single governance-owned source of truth for the protocol trust singletons that
/// `SovereignAgent`'s gate reads at call time: the stake vault, the policy registry, and the
/// reward-discount module.
/// @dev Why a governance-owned pin rather than per-agent controller storage: a SovereignAgent is
/// self-deployed and is its own controller, so any reference it sets itself, it can also swap for
/// a benign fake to neutralize the freeze/policy/stake gate (the Critical this redesign fixes). By
/// pinning the three references here — behind `DEFAULT_ADMIN_ROLE` (governance), which no agent
/// controls — and resolving them through `XibalbaAgentRegistry.trustConfig()` at call time, a
/// registered agent can never redirect its own gate.
///
/// These are settable storage (not immutables) on purpose: governance must be able to repair a
/// buggy module or migrate the trust layer without redeploying every agent. A zero address leaves
/// that facet inert (same backward-compatible "unwired behaves as before" semantics as before the
/// redesign), which is also how governance disables a facet.
contract TrustConfig is AccessControl {
    /// @notice Stake vault the gate reads `frozen` from and locks action stake against.
    address public stakeVault;
    /// @notice Policy registry the gate consults for compliance and graph-edge proofs.
    address public policyRegistry;
    /// @notice Reward-discount module the gate reads an agent's stake discount from.
    address public rewardDiscountModule;

    event StakeVaultSet(address indexed stakeVault);
    event PolicyRegistrySet(address indexed policyRegistry);
    event RewardDiscountModuleSet(address indexed rewardDiscountModule);

    /// @param admin Receives `DEFAULT_ADMIN_ROLE` (protocol governance).
    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function setStakeVault(address v) external onlyRole(DEFAULT_ADMIN_ROLE) {
        stakeVault = v;
        emit StakeVaultSet(v);
    }

    function setPolicyRegistry(address p) external onlyRole(DEFAULT_ADMIN_ROLE) {
        policyRegistry = p;
        emit PolicyRegistrySet(p);
    }

    function setRewardDiscountModule(address m) external onlyRole(DEFAULT_ADMIN_ROLE) {
        rewardDiscountModule = m;
        emit RewardDiscountModuleSet(m);
    }
}
