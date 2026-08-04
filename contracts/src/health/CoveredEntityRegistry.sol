// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title CoveredEntityRegistry
/// @notice Registry of HIPAA "Covered Entities" and "Business Associates" (the two party
/// types a Business Associate Agreement, see health/SmartBAA.sol, is signed between).
/// @dev Registration is admin/REGISTRAR_ROLE-gated rather than permissionless: unlike a
/// generic domain (framework/DomainRegistry.sol), being listed here is a claim of actual
/// legal HIPAA status, which isn't something a smart contract can verify on its own —
/// it has to be vetted off-chain (by Xibalba Solutions or a delegated auditor) before
/// being anchored here. Everything downstream (SmartBAAFactory, EHRGate,
/// HIPAAGuardrailRegistry) trusts this registry as the root of "is this actually a
/// covered entity/BA", so the registrar role should be held by a small, audited set of
/// keys, not left open.
contract CoveredEntityRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    enum EntityType {
        Unregistered,
        CoveredEntity,
        BusinessAssociate
    }

    struct Entity {
        EntityType entityType;
        string metadataURI; // off-chain profile (legal name, NPI, jurisdiction, etc.)
        bool active;
    }

    mapping(address => Entity) public entities;

    event EntityRegistered(address indexed entity, EntityType entityType, string metadataURI);
    event EntityRevoked(address indexed entity);

    error UnknownEntityType();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(REGISTRAR_ROLE, admin);
    }

    function registerEntity(address entity, EntityType entityType, string calldata metadataURI)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        if (entityType == EntityType.Unregistered) revert UnknownEntityType();
        entities[entity] = Entity({entityType: entityType, metadataURI: metadataURI, active: true});
        emit EntityRegistered(entity, entityType, metadataURI);
    }

    function revokeEntity(address entity) external onlyRole(REGISTRAR_ROLE) {
        entities[entity].active = false;
        emit EntityRevoked(entity);
    }

    function isActiveCoveredEntity(address entity) external view returns (bool) {
        Entity storage e = entities[entity];
        return e.active && e.entityType == EntityType.CoveredEntity;
    }

    function isActiveBusinessAssociate(address entity) external view returns (bool) {
        Entity storage e = entities[entity];
        return e.active && e.entityType == EntityType.BusinessAssociate;
    }
}
