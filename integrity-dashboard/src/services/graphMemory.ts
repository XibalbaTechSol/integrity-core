import { GRAPH_MEMORY_URL } from '../config';

// Mirrors xibalba_cortex.local_api's routes exactly, which themselves are thin wrappers around
// GraphStore's own methods (store.py) -- no response envelope, each route just returns the
// JSON the underlying GraphStore method returned.

import type {
    Attachment,
    EntityRelation,
    Exchange,
    GraphMemoryStats,
    GraphPayload,
    InferenceManifest,
    InferenceTask,
    KernelDecision,
    KernelIntentTriple,
    ParaClassification,
    IntegrityLinksStatus,
    Memory,
    MemoryEvent,
    MerkleRoot,
    OtelEvent,
    RecordModelExchangePayload,
    RecordModelExchangeResult,
    Session,
    SimilarHit,
    StoreStatus,
    TraversalResult,
} from '../types/graphMemory';

export type {
    Attachment,
    ContextContribution,
    EntityRelation,
    Exchange,
    GraphEdge,
    GraphMemoryStats,
    GraphNode,
    GraphPayload,
    InferenceManifest,
    InferenceTask,
    KernelDecision,
    KernelIntentTriple,
    ParaClassification,
    IntegrityLinkRecord,
    IntegrityLinksStatus,
    Memory,
    MemoryEvent,
    MemorySource,
    MerkleRoot,
    OtelEvent,
    RecordModelExchangePayload,
    RecordModelExchangeResult,
    Session,
    SimilarHit,
    StoreStatus,
    TraversalEdge,
    TraversalResult,
} from '../types/graphMemory';


// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function getJson<T>(path: string): Promise<T> {
    const response = await fetch(`${GRAPH_MEMORY_URL}${path}`);
    if (!response.ok) {
        const body = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(body.error ?? `request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
    const response = await fetch(`${GRAPH_MEMORY_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(body.error ?? `request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API client — full parity with xibalba-cortex viewer/src/api.ts
// ---------------------------------------------------------------------------

export const graphMemory = {
    // Read operations — store health & overview
    stats: () => getJson<GraphMemoryStats>('/api/stats'),
    status: () => getJson<StoreStatus>('/api/status'),
    integrityLinks: (limit = 50) => getJson<IntegrityLinksStatus>(`/api/integrity-links?limit=${limit}`),

    // Sessions
    sessions: (limit = 100) => getJson<Session[]>(`/api/sessions?limit=${limit}`),
    sessionExchanges: (id: string) => getJson<Exchange[]>(`/api/session/${encodeURIComponent(id)}/exchanges`),
    sessionMerkleRoot: (id: string) => getJson<MerkleRoot>(`/api/session/${encodeURIComponent(id)}/merkle-root`),
    sessionKernelIntents: (id: string) => getJson<KernelIntentTriple[]>(`/api/session/${encodeURIComponent(id)}/kernel-intents`),

    // Graph & search
    graph: (limit = 500, similarityThreshold = 0.75) =>
        getJson<GraphPayload>(`/api/graph?limit=${limit}&similarity_threshold=${similarityThreshold}`),
    search: (query: string, limit = 20) =>
        getJson<Memory[]>(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`),

    // Individual memory
    memory: (id: string) => getJson<Memory>(`/api/memory/${encodeURIComponent(id)}`),
    similar: (id: string, limit = 10) =>
        getJson<SimilarHit[]>(`/api/memory/${encodeURIComponent(id)}/similar?limit=${limit}`),
    neighbors: (id: string) => getJson<EntityRelation[]>(`/api/memory/${encodeURIComponent(id)}/neighbors`),
    memoryEvents: (id: string) => getJson<MemoryEvent[]>(`/api/memory/${encodeURIComponent(id)}/events`),
    memoryOtel: (id: string) => getJson<OtelEvent[]>(`/api/memory/${encodeURIComponent(id)}/otel`),
    attachments: (id: string) => getJson<Attachment[]>(`/api/memory/${encodeURIComponent(id)}/attachments`),
    contradictions: (id: string) => getJson<Memory[]>(`/api/memory/${encodeURIComponent(id)}/contradictions`),

    // Entity traversal
    entityNeighbors: (name: string, maxDepth = 1) =>
        getJson<TraversalResult>(`/api/entity/${encodeURIComponent(name)}/neighbors?max_depth=${maxDepth}`),
    entityPath: (from: string, to: string, maxDepth = 3) =>
        getJson<TraversalResult>(`/api/entity/path?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&max_depth=${maxDepth}`),

    // Inference
    inferenceManifest: () => getJson<InferenceManifest>('/api/inference/manifest'),
    inferenceTasks: (status = 'pending', limit = 50) =>
        getJson<InferenceTask[]>(`/api/inference/tasks?status=${encodeURIComponent(status)}&limit=${limit}`),

    paraClassifications: (status = 'proposed', limit = 50) =>
        getJson<ParaClassification[]>(`/api/para/classifications?status=${encodeURIComponent(status)}&limit=${limit}`),
    decideParaClassification: (taskId: string, decision: 'accept' | 'dismiss' | 'keep_original', note?: string) =>
        postJson<ParaClassification>(`/api/para/classifications/${encodeURIComponent(taskId)}/decision`, { decision, ...(note ? { note } : {}) }),
    recordModelExchange: (payload: RecordModelExchangePayload) =>
        postJson<RecordModelExchangeResult>('/api/exchanges/model', payload as unknown as Record<string, unknown>),
    requestInferenceTask: (payload: Record<string, unknown>) =>
        postJson<InferenceTask>('/api/inference/tasks', payload),
    createProposition: (payload: Record<string, unknown>) =>
        postJson<Memory>('/api/memory/propositions', payload),
    linkEntities: (payload: Record<string, unknown>) =>
        postJson<EntityRelation>('/api/memory/link-entities', payload),
    markContradiction: (payload: Record<string, unknown>) =>
        postJson<Record<string, unknown>>('/api/memory/contradictions', payload),
    supersedeMemory: (id: string, payload: Record<string, unknown>) =>
        postJson<Memory>(`/api/memory/${encodeURIComponent(id)}/supersede`, payload),
    claimInferenceTask: (id: string, claimedBy: string) =>
        postJson<InferenceTask>(`/api/inference/tasks/${encodeURIComponent(id)}/claim`, { claimed_by: claimedBy }),
    completeInferenceTask: (id: string, outputPayload: Record<string, unknown>, error?: string) =>
        postJson<InferenceTask>(`/api/inference/tasks/${encodeURIComponent(id)}/complete`, {
            output_payload: outputPayload,
            ...(error ? { error } : {}),
        }),
};
