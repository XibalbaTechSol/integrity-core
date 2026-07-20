// ─── Contract Types ─────────────────────────────────────────────────
export type ContractType =
  | 'SLA'
  | 'Escrow'
  | 'RevenueShare'
  | 'ReputationBond'
  | 'InsurancePool'
  | 'LoanAgreement'
  | 'DIDRegistry'
  | 'Custom';

export type ClaimType = 'deployed' | 'auditor' | 'collaborator';
export type LoanStatus = 'active' | 'repaid' | 'defaulted' | 'liquidated';
export type ProposalStatus = 'active' | 'passed' | 'failed' | 'expired' | 'executed';
export type TierGrade = 'AAA' | 'AA' | 'A' | 'B' | 'C';

export function getTier(ais: number): TierGrade {
  if (ais >= 900) return 'AAA';
  if (ais >= 750) return 'AA';
  if (ais >= 500) return 'A';
  if (ais >= 250) return 'B';
  return 'C';
}

// ─── DID (W3C Spec) ─────────────────────────────────────────────────
export interface VerificationMethod {
  id: string;
  type: string;
  controller: string;
  publicKeyMultibase?: string;
  blockchainAccountId?: string;
}

export interface ServiceEndpoint {
  id: string;
  type: string;
  serviceEndpoint: string;
}

export interface DIDDocument {
  '@context': string[];
  id: string;
  controller: string;
  verificationMethod: VerificationMethod[];
  authentication: string[];
  assertionMethod: string[];
  service: ServiceEndpoint[];
  created: string;
  updated: string;
}

// ─── Contracts ──────────────────────────────────────────────────────
export interface OwnedContract {
  contract_address: string;
  contract_type: ContractType;
  deployed_at: string;
  chain: string;
  revenue_generated: number;
  collateral_value: number;
  is_collateralized: boolean;
  claim_type: ClaimType;
  status: 'active' | 'paused' | 'terminated';
}

// ─── Loans ──────────────────────────────────────────────────────────
export interface Loan {
  loan_id: string;
  borrower: string;
  lender: string;
  principal: number;
  interest_rate: number;
  collateral_contracts: string[];
  collateral_ais: number;
  status: LoanStatus;
  created_at: string;
  due_date: string;
  repaid_amount: number;
  term_days: number;
}

// ─── Credit ─────────────────────────────────────────────────────────
export interface CreditProfile {
  credit_score: number;
  max_borrow_limit: number;
  active_loans: Loan[];
  total_borrowed: number;
  total_repaid: number;
  default_count: number;
}

// ─── Agent ──────────────────────────────────────────────────────────
export interface Agent {
  agent_id?: string; // UUID from backend
  eth_address: string;
  alias: string;
  model_class: string;
  current_ais: number;
  verification_tier: number;
  compliance_score: number;
  entropy_score: number;
  grounding_score: number;
  sacrifice_score: number;
  tee_verified: boolean;
  tee_type?: string;
  tee_measurement?: string;
  xns_handle?: string;
  did_document?: DIDDocument;
  owned_contracts?: OwnedContract[];
  credit_profile?: CreditProfile;
  equity?: EquityHolding[];
  staked_itk: number;
  registered_at: string;
  last_active: string;
}

// ─── Protocol Stats ─────────────────────────────────────────────────
export interface ProtocolStats {
  active_nodes: number;
  aggregate_ais: number;
  protocol_staked_itk: number;
  active_disputes: number;
  total_contracts: number;
  total_loans_volume: number;
  total_marketplace_volume: number;
  tvl: number;
}

// ─── Telemetry ──────────────────────────────────────────────────────
export interface TelemetryReport {
  agent_address: string;
  deal_id: string;
  contract_value_intg: number;
  latency_ms: number;
  accuracy_score: number;
  tokens_processed: number;
  model_class: string;
  timestamp: string;
}

export interface ReputationPoint {
  date: string;
  ais: number;
  entropy: number;
  grounding: number;
  sacrifice: number;
}

// ─── Governance ─────────────────────────────────────────────────────
export interface GovernanceProposal {
  id: string;
  title: string;
  description: string;
  proposer: string;
  category: 'protocol' | 'economic' | 'governance' | 'security';
  votes_for: number;
  votes_against: number;
  quorum: number;
  status: ProposalStatus;
  created_at: string;
  expires_at: string;
}

// ─── Marketplace ────────────────────────────────────────────────────
export interface MarketplaceOffer {
  offer_id: string;
  provider: string;
  provider_alias: string;
  service_type: string;
  description: string;
  price_itk: number;
  min_ais_required: number;
  sla_terms?: string;
  created_at: string;
  purchases: number;
  rating: number;
}

export interface MarketTask {
  task_id: string;
  creator_agent_id: string;
  title: string;
  description: string;
  reward_itk: number;
  min_ais_required: number;
  status: 'OPEN' | 'AUCTION' | 'SETTLED' | 'CLOSED';
  created_at: string;
}

export interface MarketBid {
  bid_id: string;
  task_id: string;
  bidder_agent_id: string;
  bid_amount_itk: number;
  status: 'PENDING' | 'ACCEPTED' | 'REJECTED';
  created_at: string;
}

// ─── Equity ─────────────────────────────────────────────────────────
export interface EquityHolding {
  agent_address: string;
  holder_address: string;
  shares: number;
  total_shares: number;
  percentage: number;
  dividends_earned: number;
}

// ─── ZK Proofs ──────────────────────────────────────────────────────
export interface ZKProof {
  proof_id: string;
  agent_address: string;
  proof_type: string;
  threshold?: number;
  verified: boolean;
  proof_hash: string;
  proof_data: string;
  created_at: string;
}

// ─── Compliance ─────────────────────────────────────────────────────
export interface ComplianceScore {
  overall: number;
  kya: number;
  contract_compliance: number;
  telemetry_integrity: number;
  governance_participation: number;
}

export interface ComplianceEvent {
  id: string;
  type: 'registration' | 'verification' | 'violation' | 'resolution';
  severity: 'info' | 'warning' | 'critical';
  description: string;
  agent_address: string;
  timestamp: string;
}

// ─── Provenance ─────────────────────────────────────────────────────
export interface ProvenanceEntry {
  id: string;
  agent_address: string;
  action: string;
  input_hash: string;
  output_hash: string;
  model_used: string;
  timestamp: string;
  parent_id?: string;
}

export interface StabilityBenchmark {
  model_name: string;
  provider_name: string;
  simulated_ais: number;
  stability_metric: number;
  grounding_metric: number;
}

// ─── Tab types ──────────────────────────────────────────────────────
export type TabId =
  | 'telemetry'
  | 'identity'
  | 'ledger'
  | 'zk'
  | 'factory'
  | 'compliance'
  | 'shield'
  | 'oracle'
  | 'credit'
  | 'governance'
  | 'markets'
  | 'staking'
  | 'stability'
  | 'wallet'
  | 'cognition'
  | 'reasoning'
  | 'diagnostics'
  | 'apikeys';
