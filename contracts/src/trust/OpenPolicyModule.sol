// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IPolicyModule} from "./IPolicyModule.sol";

/// @title OpenPolicyModule
/// @notice The explicit "this domain has no call-level policy yet" module: allows every call at
/// zero risk weight.
/// @dev Exists because `PolicyRegistry.checkCompliance` fail-closes (`NoModuleConfigured`) for a
/// domain with neither a module nor a graph root, which bricks every registered agent in it. An
/// Open domain bootstrapped at genesis therefore needs SOME module. Pointing it here states the
/// permissiveness on-chain, where it is visible and replaceable, instead of leaving the policy
/// facet unwired. The freeze and stake-lock facets of the gate still apply in full.
///
/// Governance tightens a domain by replacing this with a real module (`PolicyRegistry.setModule`)
/// or by anchoring a graph root (`setGraphRoot`), after which plain `execute` reverts
/// `EdgeClaimRequired` and every call must prove an edge.
contract OpenPolicyModule is IPolicyModule {
    function checkCompliance(address, bytes32, address, bytes calldata) external pure returns (bool, uint16) {
        return (true, 0);
    }
}
