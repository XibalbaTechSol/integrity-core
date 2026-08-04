// Minimal ABIs for the Integrity Health (HIPAA) vertical writes. Signatures from
// contracts/src/health/{SmartBAAFactory,SmartBAA,CoveredEntityRegistry}.sol.

export const SMART_BAA_FACTORY_ABI = [
  'function createBAA(address businessAssociate, bytes32 agreementHash, uint256 requiredCollateral) returns (address baa)',
  'function isBAAActive(address coveredEntity, address businessAssociate) view returns (bool)',
  'event BAACreated(address indexed coveredEntity, address indexed businessAssociate, address baa, bytes32 agreementHash)',
] as const;

export const SMART_BAA_ABI = [
  'function sign()',
  'function raiseDispute()',
  'function arbitrate(bool slash)',
  'function revoke()',
  'function status() view returns (uint8)',
  'function coveredEntity() view returns (address)',
  'function businessAssociate() view returns (address)',
  'function requiredCollateral() view returns (uint256)',
] as const;

export const COVERED_ENTITY_REGISTRY_ABI = [
  'function isActiveCoveredEntity(address) view returns (bool)',
  'function registerEntity(address entity, uint8 entityType, string metadataURI)',
  'function REGISTRAR_ROLE() view returns (bytes32)',
  'function hasRole(bytes32 role, address account) view returns (bool)',
] as const;

// CoveredEntityRegistry.EntityType: 0 Unregistered, 1 CoveredEntity, 2 BusinessAssociate.
export const ENTITY_TYPE_COVERED_ENTITY = 1;
