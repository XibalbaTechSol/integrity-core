export const ITK_TOKEN_ADDRESS = "0xcc3fa26e4C792f253b72D7D4b885c1fa7116A99c";
export const REPUTATION_REGISTRY_ADDRESS = "0x160481db97eb483d2Dd5Da060b8cCfEaeA7096cC";
export const INTEGRITY_PROTOCOL_ADDRESS = "0xb6B9E48d6262957672fef367Bd7641159CD1e560";
export const XIBALBA_AGENT_ADDRESS = "0x67ba5d723e1f5517aff7eb980e2f73a9e17ad556";
export const NO_CODE_FACTORY_ADDRESS = "0x6afe85f7B3EfA26D2848555fC657a6EC070DFD48";

export const BASE_SEPOLIA_CHAIN_ID = 84532;
export const RPC_URL = "https://sepolia.base.org";

export const IS_PRODUCTION = false; // Set to false to route to the local backend for session telemetry

const envApiBase = import.meta.env.VITE_API_BASE;
export const API_BASE = (envApiBase && envApiBase.startsWith('http'))
  ? envApiBase
  : (IS_PRODUCTION 
      ? "https://integrity-protocol-backend.onrender.com"
      : "http://127.0.0.1:9000");


