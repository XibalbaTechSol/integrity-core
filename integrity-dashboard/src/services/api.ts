import axios from 'axios';
import { API_BASE } from '../constants';
import type { 
  Agent, ProtocolStats, OwnedContract,
  ReputationPoint,
  DIDDocument,
  MarketTask,
  CreditProfile,
  GovernanceProposal,
  ZKProof,
  ProvenanceEntry,
  TelemetryReport
} from '../types';

const BASE_URL = `${API_BASE}/v1`;

export interface RegisterAgentData {
  eth_address: string;
  alias: string;
  model_class: string;
}

export interface ClaimContractData {
  contract_address: string;
  claim_type: string;
}

export interface DeployContractData {
  contract_type: string;
  params: Record<string, unknown>;
}

export interface ListMarketContractData {
  contract_address: string;
  price_itk: number;
}

export interface BorrowData {
  amount: number;
  collateral_contracts: string[];
  term_days?: number;
}

export interface RepayData {
  loan_id: string;
  amount: number;
}

export interface FundTaskWithLoanData {
  creator_agent_id: string;
  task_id?: string;
  title: string;
  reward_itk: number;
  min_ais_required: number;
  description: string;
  auction_duration_sec: number;
}

export interface CreateProposalData {
  title: string;
  description: string;
  category: string;
}

export interface CreateMarketTaskData {
  creator_agent_id: string;
  title: string;
  description: string;
  reward_itk: number;
  min_ais_required: number;
  auction_duration_sec: number;
}

export interface BidOnTaskData {
  task_id: string;
  bidder_agent_address: string;
  bid_amount_itk: number;
}

export interface StabilityBenchmark {
  model_name: string;
  provider_name: string;
  simulated_ais: number;
  stability_metric: number;
  grounding_metric: number;
}

class ApiService {
  private async fetch<T>(endpoint: string): Promise<T> {
    const res = await axios.get(`${BASE_URL}${endpoint}`, {
      headers: { Authorization: 'Bearer master_agent_token' }
    });
    return res.data;
  }

  private async post<T, D>(endpoint: string, data: D): Promise<T> {
    const res = await axios.post(`${BASE_URL}${endpoint}`, data, {
      headers: { Authorization: 'Bearer master_agent_token' }
    });
    return res.data;
  }

  // --- Agents ---
  async getAgents(): Promise<Agent[]> {
    return this.fetch('/user/agents');
  }

  async getAgentIdentity(address: string): Promise<{ did_document: DIDDocument }> {
    return this.fetch(`/agent/${address}/identity`);
  }

  async generateClaimChallenge(address: string, claimAddress: string): Promise<string> {
    return this.post(`/agent/${address}/identity/challenge`, { claimAddress });
  }

  async claimOwnership(address: string, data: Record<string, unknown>): Promise<{ status: string }> {
    return this.post(`/agent/${address}/identity/claim`, data);
  }

  async registerAgent(data: RegisterAgentData): Promise<Agent> {
    return this.post('/agent/register', data);
  }

  async updateAgentMetadata(address: string, data: Record<string, unknown>): Promise<unknown> {
    const res = await axios.patch(`${BASE_URL}/agent/${address}/metadata`, data, {
      headers: { Authorization: 'Bearer master_agent_token' }
    });
    return res.data;
  }

  // --- Auth / Keys ---
  async getApiKeys(): Promise<unknown[]> {
    return this.fetch('/api-keys');
  }

  async generateApiKey(expirationDays?: number): Promise<{ api_key: string, expires_at: string }> {
    return this.post('/api-keys/generate', { expiration_days: expirationDays });
  }

  async deleteApiKey(key: string): Promise<{ status: string }> {
    return this.post(`/api-keys/delete`, { api_key: key });
  }

  // --- Protocol Stats ---
  async getProtocolStats(): Promise<ProtocolStats> {
    return this.fetch('/protocol/stats');
  }

  subscribeToMetrics(callback: (data: any) => void): () => void {
    const eventSource = new EventSource(`${BASE_URL}/metrics/stream`);
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        callback(data);
      } catch (err) {
        console.error('Failed to parse SSE data', err);
      }
    };
    eventSource.onerror = (err) => {
      console.error('SSE Error', err);
    };
    return () => eventSource.close();
  }

  // --- Contracts ---
  async getAgentContracts(address: string): Promise<OwnedContract[]> {
    return this.fetch(`/agent/${address}/contracts`);
  }

  async getAllContracts(): Promise<OwnedContract[]> {
    return this.fetch('/contracts/ledger');
  }

  async claimContract(address: string, data: ClaimContractData): Promise<{ status: string }> {
    return this.post(`/agent/${address}/contracts/claim`, data);
  }

  async deployContract(data: DeployContractData): Promise<{ contract_address: string, status: string }> {
    return this.post('/contracts/factory/deploy', data);
  }

  async getDeployedContracts(): Promise<any[]> {
    return this.fetch('/contracts/deployed');
  }

  getContractTelemetryStreamUrl(): string {
    return `${BASE_URL}/contracts/telemetry/stream`;
  }

  async listMarketContract(data: ListMarketContractData): Promise<{ status: string }> {
    return this.post('/contracts/list-market', data);
  }

  // --- Loans ---
  async getCreditProfile(address: string): Promise<CreditProfile> {
    return this.fetch(`/agent/${address}/credit/profile`);
  }

  async borrow(address: string, data: BorrowData): Promise<{ loan_id: string, status: string }> {
    return this.post(`/agent/${address}/credit/borrow`, data);
  }

  async repay(address: string, data: RepayData): Promise<{ status: string }> {
    return this.post(`/agent/${address}/credit/repay`, data);
  }

  async fundTaskWithLoan(data: FundTaskWithLoanData): Promise<{ status: string, task_id: string }> {
    return this.post('/market/task/fund-with-loan', data);
  }

  // --- Reputation ---
  async getReputationHistory(address: string): Promise<ReputationPoint[]> {
    return this.fetch(`/agent/${address}/reputation/history`);
  }

  // --- ZK Proofs ---
  async generateZKProof(address: string, data: Record<string, unknown>): Promise<ZKProof> {
    return this.post(`/agent/${address}/zk/generate-proof`, data);
  }

  // --- Governance ---
  async getProposals(): Promise<GovernanceProposal[]> {
    return this.fetch('/governance/proposals');
  }

  async createProposal(data: CreateProposalData): Promise<GovernanceProposal> {
    return this.post('/governance/proposals', data);
  }

  async voteProposal(id: string, vote: string): Promise<{ status: string }> {
    return this.post(`/governance/proposals/${id}/vote`, { vote });
  }

  // --- Staking ---
  async stake(address: string, amount_itk: number): Promise<{ status: string, staked_amount: number }> {
    return this.post(`/agent/${address}/stake`, { amount_itk });
  }

  // --- Marketplace ---
  async getMarketTasks(): Promise<MarketTask[]> {
    return this.fetch('/market/tasks');
  }

  async createMarketTask(data: CreateMarketTaskData): Promise<MarketTask> {
    return this.post('/market/task/create', data);
  }

  async bidOnTask(data: BidOnTaskData): Promise<{ status: string }> {
    return this.post('/market/task/bid', data);
  }

  async settleAuction(taskId: string): Promise<{ status: string }> {
    return this.post('/market/task/settle', { task_id: taskId });
  }

  // --- Advanced / Provenance ---
  async getProvenance(address: string): Promise<ProvenanceEntry[]> {
    return this.fetch(`/agent/${address}/provenance`);
  }

  // --- Stability Benchmarks ---
  async getBenchmarks(): Promise<StabilityBenchmark[]> {
    return this.fetch(`/stability/benchmarks`);
  }

  async requestAudit(address: string, type: string): Promise<{ status: string, audit_id: string }> {
    return this.post('/audit/request', { agent_address: address, audit_type: type });
  }

  // --- Wallet & Tokens ---
  async getWalletBalance(address: string): Promise<{ balance_itk: number }> {
    return this.fetch(`/wallet/${address}/balance`);
  }

  async transferTokens(from: string, to: string, amount: number): Promise<{ status: string, tx_hash: string }> {
    return this.post('/wallet/transfer', { from_address: from, to_address: to, amount_itk: amount });
  }

  // --- Shield / Smart BAA ---
  async getBAAs(): Promise<unknown[]> {
    return this.fetch('/shield/baas');
  }

  async proposeBAA(data: unknown): Promise<unknown> {
    return this.post('/shield/baa/propose', data);
  }

  async signBAA(baaId: string, signature: string): Promise<unknown> {
    return this.post(`/shield/baa/${baaId}/sign`, { signature });
  }

  async getShieldInteractions(): Promise<unknown[]> {
    return this.fetch('/shield/interactions');
  }

  async getComplianceReviewQueue(): Promise<unknown[]> {
    return this.fetch('/shield/compliance/review-queue');
  }

  async resolveComplianceViolation(id: string, action: 'finalize_slash' | 'dismiss'): Promise<unknown> {
    return this.post(`/shield/compliance/resolve`, { violation_id: id, action });
  }

  // --- Telemetry ---
  async reportTelemetry(data: TelemetryReport): Promise<{ status: string }> {
    return this.post('/transactions/report', data);
  }

  // --- Disputes ---
  async disputeTransaction(dealId: string, initiator: string, reason: string): Promise<{ dispute_id: string, deal_id: string, status: string, created_at: string }> {
    return this.post('/disputes/raise', {
      deal_id: dealId,
      initiator: initiator,
      reason: reason
    });
  }
}

export const api = new ApiService();
