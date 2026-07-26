import { ORACLE_URL } from '../config';

// Mirrors integrity-oracle/backend/src/handlers.rs's response DTOs exactly —
// keep in sync with spec/ais-api/v1/openapi.yaml if that surface changes.

export interface PrimitiveSetDto {
    sovereign_agent: string;
    state_anchor: string;
    reputation_registry: string;
    slasher: string;
    verifier_registry: string;
    compliance_gate: string;
    agent_profile: string;
}

export interface AgentResponse {
    id: string;
    verification_tier: number;
    last_nonce: number;
    created_at: string;
    has_ed25519_key: boolean;
    has_eth_address: boolean;
    primitives: PrimitiveSetDto | null;
    primitives_source: string;
    did_document: Record<string, unknown> | null;
}

export interface AgentSummary {
    id: string;
    name?: string | null;
    verification_tier: number;
    created_at: string;
}

export interface AisComponents {
    entropy: number;
    grounding: number;
    sacrifice: number;
    compliance: number;
}

export interface AisResponse {
    agent_id: string;
    ais: number;
    components: AisComponents;
    weights: Record<string, number>;
    zk_boost: number;
    zk_proof_verified: boolean;
    period_start: string;
    period_end: string;
    event_count: number;
    onchain_zk_boost_consistent: boolean | null;
}

export interface ComplianceResponse {
    agent_id: string;
    vertical: string;
    is_compliant: boolean;
    covered_entity: string | null;
}

export interface WalletPositionDto {
    market_address: string;
    question: string;
    outcome_index: number;
    amount: string;
    market_resolved: boolean;
    won: boolean | null;
}

export interface TransactionDto {
    id: string;
    type: string;
    asset: string;
    amount: string;
    usd: string | null;
    agent: string;
    status: string;
    time: string;
}

export interface AllowanceDto {
    agent: string;
    limit: string;
    spent: number;
    status: string;
}

export interface WalletResponse {
    agent_id: string;
    sovereign_agent: string;
    itk_balance: string;
    open_positions: WalletPositionDto[];
    transaction_history: TransactionDto[] | null;
    allowances: AllowanceDto[] | null;
}

export interface MarketSummaryDto {
    address: string;
    creator: string;
    question: string;
    outcome_count: number;
    min_ais_to_enter: string;
    resolve_deadline: string;
    resolved: boolean;
    winning_outcome: number | null;
    total_staked: string;
    outcome_staked: string[];
}

export interface PositionDto {
    amount: string;
    outcome_index: number;
    bcc_commitment_hash: string;
    claimed: boolean;
}

export interface MarketDetailDto extends MarketSummaryDto {
    your_position: PositionDto | null;
    positions_note: string;
}

export interface LeaderboardEntryDto {
    agent_id: string;
    sovereign_agent: string;
    effective_score: string;
    realized_pnl: string | null;
}

export interface TelemetryEventDetailDto {
    id: string;
    agent_id: string;
    nonce: number;
    performance_variance: number;
    hgi_raw: number;
    gpu_hours_verified: number;
    flagged: boolean;
    zk_verified: boolean;
    leaf_hash: string;
    payload: unknown;
    merkle_root_id: string | null;
    leaf_index: number | null;
    created_at: string;
}

export interface AgentJudgeEvaluationDto {
    id: string;
    agent_id: string;
    run_id: string;
    judge_model: string;
    verdict: string;
    score: number | null;
    rationale_summary: string | null;
    telemetry_event_id: string | null;
    created_at: string;
}

export interface AisHistoryPoint {
    bucket_start: string;
    ais: number;
    entropy: number;
    grounding: number;
    sacrifice: number;
    compliance: number;
    zk_boost: number;
    event_count: number;
}

export interface VolumeBucket {
    bucket_start: string;
    count: number;
    flagged_count: number;
}

export interface OtelVolumeBucket {
    bucket_start: string;
    span_count: number;
}

export interface RecentTraceDto {
    trace_id: string;
    name: string;
    start_time: string;
}

// Bucket granularity accepted by the oracle's history endpoints — see
// backend::handlers::parse_bucket_interval's allowlist.
export type HistoryBucket = '5m' | '15m' | '1h' | '6h' | '1d' | '1w';

export interface SpanTreeNode {
    id: string;
    agent_id: string;
    span_id: string;
    name: string;
    kind: string;
    status_code: string;
    start_time: string;
    end_time: string;
    duration_ms: number;
    attributes: Record<string, unknown>;
    children: SpanTreeNode[];
}

export interface TraceTreeResponse {
    trace_id: string;
    span_count: number;
    truncated: boolean;
    roots: SpanTreeNode[];
}

export interface StakeDto {
    agent_id: string;
    total_stake: string;
    locked_stake: string;
    available_stake: string;
    open_disputes: number;
}

export interface StatsDto {
    market_count: number;
    total_marketplace_volume: string;
    escrowed_credit: string;
    released_credit: string;
    allocation_count: number;
}

// backend::handlers::BaaDto — one SmartBAA agreement's live on-chain state.
export interface BaaDto {
    address: string;
    covered_entity: string;
    business_associate: string;
    agreement_hash: string;
    required_collateral: string; // decimal-string wei of $ITK
    status: 'Proposed' | 'Active' | 'Disputed' | 'Terminated' | 'Unknown';
}

// backend::handlers::BenchmarkDto — network-wide model/provider stability benchmark.
export interface BenchmarkDto {
    model_name: string;
    provider_name: string;
    simulated_ais: number;
    stability_metric: number; // 0-1
    grounding_metric: number; // 0-1
    sample_count: number;
}

// IntegrityGovernance proposal — backend::handlers::get_governance_proposals.
export interface ProposalDto {
    id: number;
    proposer: string;
    target: string;
    value: string;
    start_time: number;
    end_time: number;
    eta: number;
    for_votes: string;
    against_votes: string;
    state: 'Active' | 'Defeated' | 'Succeeded' | 'Queued' | 'Executed' | 'Expired' | 'Canceled' | 'Unknown';
    description: string;
}

// XNS (XibalbaNameService) resolution — backend::handlers::{get_xns_resolve,get_agent_handle}.
export interface XnsResolveDto {
    handle: string;
    sovereign_agent: string | null;
    did: string | null;
}

export interface AgentHandleDto {
    did: string;
    handle: string | null;
}

export interface CreditDto {
    agent_id: string;
    total_allocated: string;
    escrowed: string;
    released: string;
    clawed_back: string;
    breached: string;
    allocation_count: number;
}

export interface ProvenanceEntryDto {
    id: string;
    agent_id: string;
    intent_type: string | null;
    leaf: string;
    root: string;
    tx_hash: string;
    decision: string | null;
    anchored_at: string;
    created_at: string | null;
}

export interface AuditLogEntryDto {
    id: string;
    agent_id: string | null;
    source: string;
    event_type: string;
    decision: string;
    reason_code: string | null;
    detail: string | null;
    created_at: string;
}

// Server-Sent Event frames pushed over /v1/stream and /v1/agent/{id}/stream — mirrors
// backend::stream::StreamEvent's #[serde(tag = "type")] shape exactly.
export type StreamEvent =
    | { type: 'TelemetryEvent'; agent_id: string; event_id: string; flagged: boolean; created_at: string }
    | { type: 'OtelSpan'; agent_id: string; trace_id: string; span_id: string; name: string }
    | ({ type: 'AisUpdate' } & AisResponse);

class OracleError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

async function get<T>(path: string): Promise<T> {
    const res = await fetch(`${ORACLE_URL}${path}`);
    if (!res.ok) {
        throw new OracleError(res.status, `Oracle request failed: ${res.status} ${path}`);
    }
    return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${ORACLE_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        // Surface the backend's message (e.g. the on-chain primitive-mismatch reason)
        // so a failed registration explains itself rather than just a status code.
        const detail = await res.text().catch(() => '');
        throw new OracleError(res.status, detail || `Oracle request failed: ${res.status} ${path}`);
    }
    return res.json();
}

// POST /v1/agent/register — mirrors backend::handlers::RegisterAgentRequest. The
// oracle independently re-verifies `primitives` against XibalbaAgentRegistry on-chain
// and rejects a mismatch, so these MUST be the real addresses the factory registered.
export interface RegisterAgentRequest {
    did: string;
    did_document: Record<string, unknown>;
    primitives: PrimitiveSetDto;
    ed25519_pubkey_hex?: string;
    eth_address_hex?: string;
}

export interface RegisterAgentResponse {
    id: string;
    verification_tier: number;
    primitives: PrimitiveSetDto;
    controller: string;
    domain_id: string;
}

function historyQuery(bucket?: HistoryBucket, since?: string): string {
    const params = new URLSearchParams();
    if (bucket) params.set('bucket', bucket);
    if (since) params.set('since', since);
    const qs = params.toString();
    return qs ? `?${qs}` : '';
}

export const oracle = {
    getAgent: (id: string) => get<AgentResponse>(`/v1/agent/${encodeURIComponent(id)}`),
    // Resolve an agent's real on-chain SovereignAgent contract address from its DID. The
    // dashboard keys agents by DID (Agent.eth_address actually holds the DID), so any on-chain
    // write that needs the real address must resolve it here rather than using that field.
    resolveSovereignAgent: async (id: string): Promise<string> => {
        const detail = await get<AgentResponse>(`/v1/agent/${encodeURIComponent(id)}`);
        const sa = detail.primitives?.sovereign_agent;
        if (!sa || /^0x0+$/i.test(sa)) throw new Error('Agent has no on-chain SovereignAgent yet (not fully registered).');
        return sa;
    },
    // Records an agent in the oracle DB AFTER its primitives are registered on-chain.
    register: (req: RegisterAgentRequest) => post<RegisterAgentResponse>('/v1/agent/register', req),
    // Every real agent the oracle knows about — no client-side mock filter. Mock/seeded
    // agents are gated server-side via the /v1/protocol/settings mock_mode flag instead.
    listAgents: () => get<AgentSummary[]>('/v1/agents'),
    getAis: (id: string) => get<AisResponse>(`/v1/agent/${encodeURIComponent(id)}/ais`),
    getCompliance: (id: string, coveredEntity?: string) =>
        get<ComplianceResponse>(
            `/v1/agent/${encodeURIComponent(id)}/compliance${coveredEntity ? `?covered_entity=${coveredEntity}` : ''}`,
        ),
    getWallet: (id: string) => get<WalletResponse>(`/v1/agent/${encodeURIComponent(id)}/wallet`),
    listMarkets: () => get<MarketSummaryDto[]>('/v1/markets'),
    // Real "contracts an agent owns": the IntegrityMarket clones it deployed via
    // MarketFactory, read live on-chain (backend::handlers::get_agent_contracts).
    getAgentContracts: (id: string) => get<MarketSummaryDto[]>(`/v1/agent/${encodeURIComponent(id)}/contracts`),
    // Real SmartBAA agreements where this agent is the business associate, enumerated
    // from SmartBAAFactory.BAACreated logs (backend::handlers::get_agent_baas).
    getAgentBaas: (id: string) => get<BaaDto[]>(`/v1/agent/${encodeURIComponent(id)}/baas`),
    // Real signed W3C AgentIntegrityCredential (backend::handlers::get_agent_vc).
    getAgentVc: (id: string) => get<Record<string, unknown>>(`/v1/agent/${encodeURIComponent(id)}/vc`),
    getMarket: (address: string, agent?: string) =>
        get<MarketDetailDto>(`/v1/markets/${address}${agent ? `?agent=${agent}` : ''}`),
    getLeaderboard: () => get<LeaderboardEntryDto[]>('/v1/leaderboard'),
    getTelemetry: (id: string) => get<TelemetryEventDetailDto[]>(`/v1/agent/${encodeURIComponent(id)}/telemetry`),
    getTraces: (id: string) => get<AgentJudgeEvaluationDto[]>(`/v1/agent/${encodeURIComponent(id)}/traces`),

    getAisHistory: (id: string, bucket?: HistoryBucket, since?: string) =>
        get<AisHistoryPoint[]>(`/v1/agent/${encodeURIComponent(id)}/ais/history${historyQuery(bucket, since)}`),
    getTelemetryVolume: (id: string, bucket?: HistoryBucket, since?: string) =>
        get<VolumeBucket[]>(`/v1/agent/${encodeURIComponent(id)}/telemetry/volume${historyQuery(bucket, since)}`),
    getOtelVolume: (id: string, bucket?: HistoryBucket, since?: string) =>
        get<OtelVolumeBucket[]>(`/v1/agent/${encodeURIComponent(id)}/otel/volume${historyQuery(bucket, since)}`),
    // Historical trace discovery — previously the only way to find a trace_id was to
    // watch the live SSE stream while a tab was open, so any trace generated earlier
    // was invisible even though it's real, queryable data. See backend::handlers::get_recent_traces.
    getRecentTraces: (id: string, limit?: number) =>
        get<RecentTraceDto[]>(`/v1/agent/${encodeURIComponent(id)}/otel/traces${limit ? `?limit=${limit}` : ''}`),
    getTraceTree: (traceId: string) => get<TraceTreeResponse>(`/v1/traces/${encodeURIComponent(traceId)}`),

    // Real, durable audit trail backed by bcc_middleware's ALLOW/DENY reporting
    // (POST /v1/audit/ingest) merged with flagged telemetry — see
    // backend::handlers::get_audit_log. Omit agentId for the global feed.
    getAuditLog: (agentId?: string, limit?: number) => {
        const params = new URLSearchParams();
        if (agentId) params.set('agent_id', agentId);
        if (limit) params.set('limit', String(limit));
        const qs = params.toString();
        return get<AuditLogEntryDto[]>(`/v1/audit-log${qs ? `?${qs}` : ''}`);
    },

    // The agent's real on-chain-anchored provenance chain (backend::handlers::
    // get_provenance) — each committed Merkle leaf + the StateAnchor root/tx that
    // anchored it + the policy decision that produced it.
    getProvenance: (id: string) =>
        get<ProvenanceEntryDto[]>(`/v1/agent/${encodeURIComponent(id)}/provenance`),

    // Real on-chain stake accounting from the agent's Slasher clone
    // (backend::handlers::get_stake). Values are decimal-string wei of $ITK.
    getStake: (id: string) =>
        get<StakeDto>(`/v1/agent/${encodeURIComponent(id)}/stake`),

    // Real capital position aggregated from the A2ACapitalPool
    // (backend::handlers::get_credit). Amounts are decimal-string wei of $ITK.
    getCredit: (id: string) =>
        get<CreditDto>(`/v1/agent/${encodeURIComponent(id)}/credit`),

    // Protocol-wide singleton aggregates (backend::handlers::get_stats): marketplace
    // volume + A2ACapitalPool totals. The minimal supplement to the fields the
    // dashboard already derives from its per-agent loop — `tvl` is composed
    // client-side (stake + escrowed + market volume) for a single source of truth.
    getStats: () => get<StatsDto>('/v1/stats'),
    // Network-wide model/provider stability benchmarks (backend::handlers::get_benchmarks).
    getBenchmarks: () => get<BenchmarkDto[]>('/v1/benchmarks'),

    // XNS handle→SovereignAgent resolution, read live from the XibalbaNameService singleton
    // (backend::handlers::get_xns_resolve). Returns 503 until the contract is deployed.
    resolveXns: (handle: string) =>
        get<XnsResolveDto>(`/v1/xns/resolve?handle=${encodeURIComponent(handle.replace(/^@/, ''))}`),
    // Reverse: the agent's primary XNS handle (backend::handlers::get_agent_handle).
    getAgentHandle: (id: string) => get<AgentHandleDto>(`/v1/agent/${encodeURIComponent(id)}/handle`),

    // Live IntegrityGovernance proposals, newest first (backend::handlers::
    // get_governance_proposals). Returns 503 until the Governance contract is deployed —
    // callers degrade to the honest "not deployed yet" state rather than an empty live list.
    getGovernanceProposals: () => get<ProposalDto[]>('/v1/governance/proposals'),

    // EventSource doesn't take fetch-style options, so callers construct their own
    // `new EventSource(oracle.streamUrl(id))` — see hooks/useOracleStream.ts.
    streamUrl: (agentId?: string) => `${ORACLE_URL}${agentId ? `/v1/agent/${encodeURIComponent(agentId)}/stream` : '/v1/stream'}`,
};

export { OracleError };
