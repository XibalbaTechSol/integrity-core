// On-chain addresses are sourced from the committed mirror of the repo-root
// deployments.baseSepolia.json (src/deployments.baseSepolia.json) — NOT hand-copied
// here, which is how the previous values went stale (they were legacy addresses from
// the old INTEGRITY repo and pointed at the wrong/nonexistent contracts on this
// network). Per-agent primitive addresses (Slasher, StateAnchor, ...) are never
// hardcoded; they resolve live from XibalbaAgentRegistry via oracle.getAgent().primitives.
import deployments from './deployments.baseSepolia.json';

const S = deployments.singletons;

// The real deployed IntegrityToken ($ITK) on Base Sepolia.
export const ITK_TOKEN_ADDRESS = S.IntegrityToken;
// The canonical DID -> primitive-set index every downstream contract resolves through.
export const XIBALBA_AGENT_REGISTRY_ADDRESS = S.XibalbaAgentRegistry;
// EIP-1167 factory that clones + registers an agent's 7-primitive set.
export const AGENT_PRIMITIVES_FACTORY_ADDRESS = S.AgentPrimitivesFactory;
export const MARKET_FACTORY_ADDRESS = S.MarketFactory;
export const A2A_CAPITAL_POOL_ADDRESS = S.A2ACapitalPool;
export const SMART_BAA_FACTORY_ADDRESS = S.SmartBAAFactory;
export const COVERED_ENTITY_REGISTRY_ADDRESS = S.CoveredEntityRegistry;
export const XNS_ADDRESS = (S as Record<string, string>).XibalbaNameService;
export const GOVERNANCE_ADDRESS = (S as Record<string, string>).IntegrityGovernance;
// undefined until DeployEHRGate.s.sol runs against Base Sepolia (only ever run
// locally so far — see PRODUCTION_GAPS.md). Consumers must check for this before use.
export const EHR_GATE_ADDRESS = (S as Record<string, string>).EHRGate;

// Protocol-held signer that every agent grants StateAnchor ANCHOR_ROLE to (and the
// SovereignAgent `oracle_` constructor arg). Single-operator testnet setup.
export const ORACLE_SIGNER_ADDRESS = deployments.protocolAddresses.oracleSigner;
// Neutral SmartBAA arbitrator (single-operator testnet; == the other protocol roles).
export const ARBITRATOR_ADDRESS = deployments.protocolAddresses.arbitrator;
// domainId (bytes32) an agent registers its primitive set under. Both are Open-join
// on Base Sepolia (DomainRegistry.JoinMode.Open) — any wallet can self-register.
export const DOMAINS = deployments.domains;

// Back-compat aliases for legacy import sites (old names, real addresses). Prefer the
// canonical names above in new code.
export const XIBALBA_AGENT_ADDRESS = XIBALBA_AGENT_REGISTRY_ADDRESS;
export const NO_CODE_FACTORY_ADDRESS = AGENT_PRIMITIVES_FACTORY_ADDRESS;

export const BASE_SEPOLIA_CHAIN_ID = deployments.chainId;
export const RPC_URL = deployments.rpcUrl;
export const EXPLORER_URL = deployments.explorerUrl;

// Phase I's guardian-governed IntegrityAccount + its bound IntegrityKernel (the three
// reference adapters -- budget, reputation-floor, assurance-tier -- live inside the
// kernel). Real bytecode on Base Sepolia, unlike LicenceAccount -- but explicitly marked
// experimental at the deploy record itself; KERNEL_REFERENCE.disclosure is that exact
// string, surfaced verbatim by KernelPage rather than paraphrased.
export const KERNEL_REFERENCE = (
  deployments as unknown as {
    experimentalPhase1Reference?: {
      IntegrityAccount: string;
      IntegrityKernel: string;
      ReputationRegistry: string;
      deployedFromCommit: string;
      disclosure: string;
    };
  }
).experimentalPhase1Reference;

export const LICENCE_REFERENCE = (
  deployments as unknown as {
    experimentalPhase2LicenceReference?: {
      LicenceAccountImplementation: string;
      LicenceToken: string;
      deployedFromCommit: string;
      disclosure: string;
      licenceEndTime: number;
      licenceStartTime: number;
      owner: string;
      protocolFeeBps: number;
      protocolFeeRecipient: string;
      royaltyPricePerUnitWei: number;
      salt: string;
      tokenBoundAccount: string;
      tokenId: number;
      volumeCapTotal: number;
    };
  }
).experimentalPhase2LicenceReference;
