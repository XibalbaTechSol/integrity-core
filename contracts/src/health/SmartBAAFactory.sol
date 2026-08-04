// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {CoveredEntityRegistry} from "./CoveredEntityRegistry.sol";
import {SmartBAA} from "./SmartBAA.sol";

/// @title SmartBAAFactory
/// @notice Deploys one SmartBAA escrow per (covered entity, business associate) pair,
/// and is the canonical lookup other Integrity Health contracts (EHRGate, HIPAAGuardrailRegistry)
/// use to answer "is there an active BAA between this hospital and this agent".
/// @dev Enforces the entity-registry check exactly once, here, rather than inside
/// SmartBAA itself — SmartBAA has no idea CoveredEntityRegistry exists, which keeps it
/// a small, easily audited escrow rather than a contract that also has to reason about
/// registry trust.
contract SmartBAAFactory is AccessControl {
    CoveredEntityRegistry public immutable entityRegistry;
    address public immutable itk;
    address public arbitrator;

    /// @dev coveredEntity => businessAssociate => deployed SmartBAA address.
    mapping(address => mapping(address => address)) public baaOf;

    event BAACreated(address indexed coveredEntity, address indexed businessAssociate, address baa, bytes32 agreementHash);
    event ArbitratorUpdated(address indexed newArbitrator);

    error NotActiveCoveredEntity();
    error BAAAlreadyExists();

    constructor(address _entityRegistry, address _itk, address _arbitrator, address admin) {
        entityRegistry = CoveredEntityRegistry(_entityRegistry);
        itk = _itk;
        arbitrator = _arbitrator;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function setArbitrator(address newArbitrator) external onlyRole(DEFAULT_ADMIN_ROLE) {
        arbitrator = newArbitrator;
        emit ArbitratorUpdated(newArbitrator);
    }

    /// @notice Creates a new BAA escrow between `msg.sender` (must be a registered,
    /// active Covered Entity) and `businessAssociate` (any Sovereign Agent address —
    /// deliberately not required to be pre-registered anywhere, since "being a business
    /// associate" is exactly the status this agreement itself establishes).
    /// @dev Allows re-forming a BAA for the same pair once the prior one has reached
    /// `Terminated` (via `SmartBAA.revoke()` or a slashing `arbitrate(true)`) — BAAs are
    /// routinely renewed in practice, and `baaOf` previously never cleared, permanently
    /// blocking `createBAA` for that pair after the first termination with no recovery
    /// path. Still blocks a duplicate while the existing agreement is `Proposed`,
    /// `Active`, or `Disputed` (i.e. genuinely still in force or being arbitrated).
    function createBAA(address businessAssociate, bytes32 agreementHash, uint256 requiredCollateral)
        external
        returns (address baa)
    {
        if (!entityRegistry.isActiveCoveredEntity(msg.sender)) revert NotActiveCoveredEntity();
        address existing = baaOf[msg.sender][businessAssociate];
        if (existing != address(0) && SmartBAA(existing).status() != SmartBAA.Status.Terminated) {
            revert BAAAlreadyExists();
        }

        baa = address(
            new SmartBAA(msg.sender, businessAssociate, arbitrator, agreementHash, requiredCollateral, itk)
        );
        baaOf[msg.sender][businessAssociate] = baa;

        emit BAACreated(msg.sender, businessAssociate, baa, agreementHash);
    }

    /// @notice True only if a BAA exists between the pair AND it is currently Active —
    /// the single check EHRGate/HIPAAGuardrailRegistry need before permitting PHI access.
    function isBAAActive(address coveredEntity, address businessAssociate) external view returns (bool) {
        address baa = baaOf[coveredEntity][businessAssociate];
        if (baa == address(0)) return false;
        return SmartBAA(baa).status() == SmartBAA.Status.Active;
    }
}
