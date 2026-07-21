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

// Protocol-held signer that every agent grants StateAnchor ANCHOR_ROLE to (and the
// SovereignAgent `oracle_` constructor arg). Single-operator testnet setup.
export const ORACLE_SIGNER_ADDRESS = deployments.protocolAddresses.oracleSigner;
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

export const IS_PRODUCTION = false; // Set to false to route to the local backend for session telemetry

const envApiBase = import.meta.env.VITE_API_BASE;
export const API_BASE = (envApiBase && envApiBase.startsWith('http'))
  ? envApiBase
  : (IS_PRODUCTION
      ? "https://integrity-protocol-backend.onrender.com"
      : "http://127.0.0.1:9000");
