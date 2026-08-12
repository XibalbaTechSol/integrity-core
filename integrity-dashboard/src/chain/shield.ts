// Minimal ABIs for the Shield (HIPAA) vertical writes. Signatures from
// contracts/src/shield/{SmartBAAFactory,SmartBAA,CoveredEntityRegistry}.sol.

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

// Real on-chain consent (contracts/src/health/EHRGate.sol) — grantAccess/revokeAccess
// are patient-wallet-signed; checkAccess/verifyAndLogAccess are called by the
// requesting agent contract itself. Written against the real ABI ahead of the actual
// deploy: EHRGate has only ever been deployed to local anvil (chain id 31337), never
// to Base Sepolia — see PRODUCTION_GAPS.md. EHR_GATE_ADDRESS in constants.ts is
// undefined until that deploy runs and merges an address into
// deployments.baseSepolia.json.
export const EHR_GATE_ABI = [
  'function grantAccess(bytes32 recordHash, address agent, address coveredEntity)',
  'function revokeAccess(bytes32 recordHash, address agent)',
  'function checkAccess(address patient, bytes32 recordHash) view returns (bool)',
  'function verifyAndLogAccess(address patient, bytes32 recordHash, address agent) returns (bool)',
  'function accessGates(address patient, bytes32 recordHash, address agent) view returns (address coveredEntity, bool isUnlocked, uint256 grantedAt)',
  'event AccessLogged(address indexed patient, bytes32 indexed recordHash, address indexed agent, bool granted)',
] as const;
