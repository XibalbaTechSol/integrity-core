export type DataSource = 'on-chain' | 'backend-indexed' | 'local' | 'externally-verified' | 'unknown';
export type VerificationState =
  | 'verified' | 'failed' | 'pending' | 'unverifiable' | 'expired' | 'revoked'
  | 'missing-input' | 'unsupported' | 'unavailable';

export interface ProtocolMetadata {
  source: DataSource;
  network: string;
  chainId: number | null;
  blockNumber?: number | null;
  blockHash?: string | null;
  transactionHash?: string | null;
  fetchedAt: string;
  freshness: 'current' | 'stale' | 'pending' | 'unknown';
  verification: VerificationState;
  agentId?: string;
  permission: 'allowed' | 'denied' | 'unknown';
}

export interface ScopedResource<T> {
  value: T | null;
  metadata: ProtocolMetadata;
  error?: string;
}

export const unavailableMetadata = (agentId?: string): ProtocolMetadata => ({
  source: 'unknown',
  network: 'Base Sepolia',
  chainId: null,
  fetchedAt: new Date().toISOString(),
  freshness: 'unknown',
  verification: 'unavailable',
  agentId,
  permission: 'unknown',
});
