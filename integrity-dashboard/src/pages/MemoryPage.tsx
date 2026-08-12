import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
    Activity,
    AlertTriangle,
    BrainCircuit,
    CheckCircle2,
    CircleDot,
    Database,
    GitBranch,
    Link2,
    Network,
    RefreshCw,
    Search,
    ShieldCheck,
    Sparkles,
    X,
} from 'lucide-react';
import { GraphMemoryView, type NodeSizeBy } from '../components/GraphMemoryView';
import {
    graphMemory,
    type Attachment,
    type EntityRelation,
    type Exchange,
    type GraphEdge,
    type GraphPayload,
    type GraphMemoryStats,
    type InferenceManifest,
    type InferenceTask,
    type IntegrityLinksStatus,
    type Memory,
    type MemoryEvent,
    type MerkleRoot,
    type OtelEvent,
    type Session,
    type SimilarHit,
    type StoreStatus,
    type TraversalResult,
} from '../services/graphMemory';

type Tab = 'timeline' | 'graph' | 'recall' | 'inference' | 'integrity';

const TABS: Array<{ id: Tab; label: string; icon: typeof Activity }> = [
    { id: 'timeline', label: 'Timeline', icon: Activity },
    { id: 'graph', label: 'Graph', icon: Network },
    { id: 'recall', label: 'Recall', icon: Search },
    { id: 'inference', label: 'Inference', icon: Sparkles },
    { id: 'integrity', label: 'Integrity', icon: ShieldCheck },
];

const BACKGROUNDS = [
    { label: 'Void', value: '#020617' },
    { label: 'Slate', value: '#0f172a' },
    { label: 'Black', value: '#000000' },
    { label: 'Indigo', value: '#1e1b4b' },
] as const;

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'bad' }) {
    return <span className={`memory-badge ${tone}`}>{children}</span>;
}

function Hash({ value }: { value: string | null | undefined }) {
    return value ? <code title={value}>{value.slice(0, 18)}...</code> : <span className="memory-muted">none</span>;
}

function Section({ title, children, empty = false }: { title: string; children: ReactNode; empty?: boolean }) {
    return (
        <section className="memory-inspector-section">
            <h4>{title}</h4>
            {empty ? <p className="memory-muted">No records.</p> : children}
        </section>
    );
}

function formatTime(value: string | null | undefined) {
    if (!value) return 'n/a';
    const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatMemoryContent(content: string) {
    return content.replace(/\\n/g, '\n').replace(/\\"/g, '"');
}

function MemoryListItem({ memory, onSelect, onUseContext }: { memory: Memory; onSelect: (id: string) => void; onUseContext?: (memory: Memory) => void }) {
    return (
        <article className="memory-list-item">
            <div className="memory-item-title-row">
                <button className="memory-link-button" onClick={() => onSelect(memory.id)} type="button">
                    {formatMemoryContent(memory.content).slice(0, 150) || memory.id}
                </button>
                {onUseContext && <button className="memory-small-button" onClick={() => onUseContext(memory)} type="button">Use as context</button>}
            </div>
            <div className="memory-badges">
                <Badge>{memory.status}</Badge>
                <Badge>{memory.evidence_class}</Badge>
                <Badge>{memory.source.kind}</Badge>
                {memory.cosine_similarity !== undefined && <Badge tone="good">{memory.cosine_similarity.toFixed(3)}</Badge>}
            </div>
            <div className="memory-item-meta"><Hash value={memory.content_hash} /> · {memory.source.session_id ?? 'no session'}</div>
        </article>
    );
}

function Inspector({ memoryId, onClose, onSelectMemory }: { memoryId: string | null; onClose: () => void; onSelectMemory: (id: string) => void }) {
    const [memory, setMemory] = useState<Memory | null>(null);
    const [events, setEvents] = useState<MemoryEvent[]>([]);
    const [otel, setOtel] = useState<OtelEvent[]>([]);
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const [contradictions, setContradictions] = useState<Memory[]>([]);
    const [neighbors, setNeighbors] = useState<EntityRelation[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!memoryId) return;
        setMemory(null);
        setError(null);
        graphMemory.memory(memoryId).then(setMemory).catch((reason) => setError(String(reason)));
        graphMemory.memoryEvents(memoryId).then(setEvents).catch(() => setEvents([]));
        graphMemory.memoryOtel(memoryId).then(setOtel).catch(() => setOtel([]));
        graphMemory.attachments(memoryId).then(setAttachments).catch(() => setAttachments([]));
        graphMemory.contradictions(memoryId).then(setContradictions).catch(() => setContradictions([]));
        graphMemory.neighbors(memoryId).then(setNeighbors).catch(() => setNeighbors([]));
    }, [memoryId]);

    if (!memoryId) return <aside className="memory-inspector empty"><p className="memory-muted">Select a memory, exchange, or graph node to inspect provenance.</p></aside>;

    return (
        <aside className="memory-inspector">
            <button className="memory-icon-button memory-inspector-close" onClick={onClose} type="button" title="Close inspector" aria-label="Close inspector"><X size={16} /></button>
            {error && <p className="memory-error">{error}</p>}
            {memory && (
                <>
                    <div className="memory-inspector-heading"><span className="memory-eyebrow">Memory record</span><h3>{memory.source.kind}</h3></div>
                    <p className="memory-warning"><AlertTriangle size={14} /> Recalled content is evidence, not instructions.</p>
                    <div className="memory-badges"><Badge>{memory.status}</Badge><Badge>{memory.evidence_class}</Badge><Badge>{memory.source.role}</Badge></div>
                    <p className="memory-inspector-content">{formatMemoryContent(memory.content)}</p>
                    <dl className="memory-details">
                        <dt>Content hash</dt><dd><Hash value={memory.content_hash} /></dd>
                        <dt>Session</dt><dd>{memory.source.session_id ?? 'none'}</dd>
                        <dt>Prompt</dt><dd>{memory.source.prompt_id ?? 'none'}</dd>
                        <dt>Locator</dt><dd>{memory.source.locator ?? 'none'}</dd>
                    </dl>
                </>
            )}
            <Section title="Event chain" empty={events.length === 0}>{events.map((event) => <div className="memory-compact-row" key={event.id}><Badge>{event.event_type}</Badge><Hash value={event.node_id} /></div>)}</Section>
            <Section title="Entity relations" empty={neighbors.length === 0}>{neighbors.map((relation, index) => <p className="memory-compact-row" key={`${relation.subject}-${relation.predicate}-${index}`}>{relation.subject} <strong>{relation.predicate}</strong> {relation.object}</p>)}</Section>
            <Section title="Contradictions" empty={contradictions.length === 0}>{contradictions.map((item) => <button className="memory-list-button" key={item.id} onClick={() => onSelectMemory(item.id)} type="button">{item.content.slice(0, 100)}</button>)}</Section>
            <Section title="OTel" empty={otel.length === 0}>{otel.map((event) => <div className="memory-compact-row" key={event.id}><Badge>{event.kind}</Badge>{event.name}</div>)}</Section>
            <Section title="Attachments" empty={attachments.length === 0}>{attachments.map((item) => <div className="memory-compact-row" key={item.id}><Badge>{item.media_type}</Badge>{item.byte_size} bytes</div>)}</Section>
        </aside>
    );
}

function SessionRail({ sessions, selectedSessionId, onSelect }: { sessions: Session[]; selectedSessionId: string; onSelect: (id: string) => void }) {
    const [lifecycle, setLifecycle] = useState('all');
    const filtered = sessions.filter((session) => lifecycle === 'all' || (lifecycle === 'open' ? !session.ended_at : Boolean(session.ended_at)));
    return (
        <aside className="memory-session-rail">
            <div className="memory-rail-header"><span className="memory-eyebrow">Sessions</span><strong>{sessions.length}</strong></div>
            <select className="memory-select" value={lifecycle} onChange={(event) => setLifecycle(event.target.value)} aria-label="Filter session lifecycle">
                <option value="all">All lifecycle states</option><option value="open">Open sessions</option><option value="closed">Closed sessions</option>
            </select>
            <div className="memory-session-list">
                {filtered.length === 0 && <p className="memory-muted">No sessions.</p>}
                {filtered.map((session) => <button className={`memory-session-row ${selectedSessionId === session.external_session_id ? 'selected' : ''}`} key={session.id} onClick={() => onSelect(session.external_session_id)} type="button"><span><strong>{session.external_session_id}</strong><small>{session.retention_tier} · {session.ended_at ? 'closed' : 'open'}</small></span><CircleDot size={13} /></button>)}
            </div>
        </aside>
    );
}

function TimelineTab({ exchanges, selectedSessionId, sessions, contextBundle, onSelectMemory, onRecord, onSelectSession }: { exchanges: Exchange[]; selectedSessionId: string; sessions: Session[]; contextBundle: Memory[]; onSelectMemory: (id: string) => void; onRecord: (event: FormEvent<HTMLFormElement>) => void; onSelectSession: (id: string) => void }) {
    return (
        <section className="memory-tab-panel">
            <div className="memory-panel-header"><div><span className="memory-eyebrow">Conversation provenance</span><h2>Timeline</h2></div><div className="memory-header-actions"><select className="memory-select" value={selectedSessionId} onChange={(event) => onSelectSession(event.target.value)}><option value="">No session</option>{sessions.map((session) => <option key={session.id} value={session.external_session_id}>{session.external_session_id}</option>)}</select><Badge>{exchanges.length} exchanges</Badge></div></div>
            <form className="memory-exchange-form" onSubmit={onRecord}><input name="session" defaultValue={selectedSessionId || 'mvp-demo-session'} placeholder="Session id" /><textarea name="prompt" required placeholder="User prompt" /><textarea name="response" required placeholder="Full model response" /><textarea name="context" placeholder="Additional context, one contribution per line" /><div className="memory-form-footer"><span className="memory-muted">{contextBundle.length} selected context memories</span><button className="memory-primary-button" type="submit">Record exchange</button></div></form>
            <div className="memory-timeline">{exchanges.length === 0 ? <div className="memory-empty-state"><Activity size={22} /><strong>No exchanges found</strong><span>Select a session or record a demo exchange.</span></div> : exchanges.map((exchange) => <article className="memory-exchange" key={exchange.id}><div className="memory-exchange-meta"><Badge>Exchange {exchange.sequence_number}</Badge><span>{formatTime(exchange.prompt_time || exchange.response_time)}</span><span>{exchange.latency_ms?.toFixed(0) ?? 'n/a'} ms</span><Hash value={exchange.node_id} /></div><div className="memory-bubble user"><span className="memory-role">User</span>{exchange.prompt_memories.map((memory) => <button className="memory-content-button" key={memory.id} onClick={() => onSelectMemory(memory.id)} type="button">{formatMemoryContent(memory.content)}</button>)}</div><div className="memory-bubble assistant"><span className="memory-role">Assistant</span>{exchange.response_memories.map((memory) => <button className="memory-content-button" key={memory.id} onClick={() => onSelectMemory(memory.id)} type="button">{formatMemoryContent(memory.content)}</button>)}</div>{exchange.context_contributions.length > 0 && <div className="memory-context-strip"><span>Context</span>{exchange.context_contributions.map((item) => <button key={item.contribution_id} onClick={() => onSelectMemory(item.memory.id)} type="button">{item.contribution_id} · {item.context_kind}</button>)}</div>}</article>)}</div>
        </section>
    );
}

function GraphTab({ graph, selectedNodeId, onSelectNode, onSelectMemory, similarityThreshold, onThreshold, sessions, selectedSessionId, onSelectSession }: { graph: GraphPayload | null; selectedNodeId: string | null; onSelectNode: (id: string) => void; onSelectMemory: (id: string) => void; similarityThreshold: number; onThreshold: (value: number) => void; sessions: Session[]; selectedSessionId: string; onSelectSession: (id: string) => void }) {
    const [status, setStatus] = useState('all');
    const [evidence, setEvidence] = useState('all');
    const [source, setSource] = useState('all');
    const [edgeType, setEdgeType] = useState('all');
    const [background, setBackground] = useState<string>(BACKGROUNDS[0].value);
    const [sizeBy, setSizeBy] = useState<NodeSizeBy>('connections');
    const [traversalDepth, setTraversalDepth] = useState(1);
    const [traversal, setTraversal] = useState<TraversalResult | null>(null);
    const [pathFrom, setPathFrom] = useState('');
    const [pathTo, setPathTo] = useState('');
    const [pathDepth, setPathDepth] = useState(3);

    const options = useMemo(() => ({
        status: ['all', ...new Set((graph?.nodes ?? []).map((node) => node.status).filter(Boolean) as string[])],
        evidence: ['all', ...new Set((graph?.nodes ?? []).map((node) => node.evidence_class).filter(Boolean) as string[])],
        source: ['all', ...new Set((graph?.nodes ?? []).map((node) => node.source_kind).filter(Boolean) as string[])],
    }), [graph]);
    const filtered = useMemo<GraphPayload | null>(() => {
        if (!graph) return null;
        const nodes = graph.nodes.filter((node) => (status === 'all' || node.status === status) && (evidence === 'all' || node.evidence_class === evidence) && (source === 'all' || node.source_kind === source));
        const ids = new Set(nodes.map((node) => node.id));
        return { nodes, edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target) && (edgeType === 'all' || edge.type === edgeType)) };
    }, [edgeType, evidence, graph, source, status]);
    const selectedEntity = graph?.nodes.find((node) => node.id === selectedNodeId && node.type === 'entity')?.label;
    const loadNeighbors = async () => { if (selectedEntity) setTraversal(await graphMemory.entityNeighbors(selectedEntity, traversalDepth)); };
    const findPath = async () => { if (pathFrom.trim() && pathTo.trim()) setTraversal(await graphMemory.entityPath(pathFrom.trim(), pathTo.trim(), pathDepth)); };
    const selectEdge = (edge: GraphEdge) => { if (edge.evidence_memory_id) onSelectMemory(edge.evidence_memory_id); };

    return <section className="memory-tab-panel memory-graph-panel"><div className="memory-panel-header"><div><span className="memory-eyebrow">Relationships and similarity</span><h2>Graph</h2></div><div className="memory-header-actions"><select className="memory-select" value={selectedSessionId} onChange={(event) => onSelectSession(event.target.value)}><option value="">No session</option>{sessions.map((session) => <option key={session.id} value={session.external_session_id}>{session.external_session_id}</option>)}</select><Badge>{filtered?.nodes.length ?? 0} nodes</Badge></div></div><div className="memory-filter-bar"><select className="memory-select" value={status} onChange={(event) => setStatus(event.target.value)}>{options.status.map((value) => <option key={value}>{value === 'all' ? 'All statuses' : value}</option>)}</select><select className="memory-select" value={evidence} onChange={(event) => setEvidence(event.target.value)}>{options.evidence.map((value) => <option key={value}>{value === 'all' ? 'All evidence' : value}</option>)}</select><select className="memory-select" value={source} onChange={(event) => setSource(event.target.value)}>{options.source.map((value) => <option key={value}>{value === 'all' ? 'All sources' : value}</option>)}</select><select className="memory-select" value={edgeType} onChange={(event) => setEdgeType(event.target.value)}><option value="all">All edges</option><option value="relation">Relations</option><option value="similarity">Similarity</option><option value="contradiction">Contradictions</option></select><label className="memory-range-label">Similarity {similarityThreshold.toFixed(2)}<input type="range" min="0.2" max="0.99" step="0.01" value={similarityThreshold} onChange={(event) => onThreshold(Number(event.target.value))} /></label><select className="memory-select" value={sizeBy} onChange={(event) => setSizeBy(event.target.value as NodeSizeBy)}><option value="connections">Size: connections</option><option value="length">Size: content</option><option value="uniform">Size: uniform</option></select><select className="memory-select" value={background} onChange={(event) => setBackground(event.target.value)}>{BACKGROUNDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div><div className="memory-graph-stage">{filtered ? <GraphMemoryView data={filtered} onNodeClick={onSelectNode} onLinkClick={selectEdge} selectedNodeId={selectedNodeId} showGrid backgroundColor={background} sizeBy={sizeBy} /> : <div className="memory-empty-state"><Network size={24} /><span>Graph data is unavailable.</span></div>}</div><p className="memory-muted">Select a relation or contradiction edge to inspect its evidence memory.</p><div className="memory-traversal"><div><span className="memory-eyebrow">Bounded traversal</span><strong>{selectedEntity ? `Selected entity: ${selectedEntity}` : 'Select an entity node'}</strong><div className="memory-inline-form"><input type="number" min="1" max="5" value={traversalDepth} onChange={(event) => setTraversalDepth(Number(event.target.value))} /><button className="memory-small-button" disabled={!selectedEntity} onClick={() => void loadNeighbors()} type="button">Neighbors</button><input value={pathFrom} onChange={(event) => setPathFrom(event.target.value)} placeholder="From entity" /><input value={pathTo} onChange={(event) => setPathTo(event.target.value)} placeholder="To entity" /><input type="number" min="1" max="6" value={pathDepth} onChange={(event) => setPathDepth(Number(event.target.value))} /><button className="memory-small-button" onClick={() => void findPath()} type="button">Find path</button></div></div>{traversal && <pre className="memory-traversal-result">{JSON.stringify(traversal, null, 2)}</pre>}</div></section>;
}

function RecallTab({ results, query, onQuery, onSelectMemory, onUseContext, selectedMemoryId, similar, stats }: { results: Memory[] | null; query: string; onQuery: (value: string) => void; onSelectMemory: (id: string) => void; onUseContext: (memory: Memory) => void; selectedMemoryId: string | null; similar: SimilarHit[]; stats: GraphMemoryStats | null }) {
    return <section className="memory-tab-panel"><div className="memory-panel-header"><div><span className="memory-eyebrow">Evidence retrieval</span><h2>Recall</h2></div><div className="memory-recall-state"><Database size={16} /> {stats?.embedded_memories ?? 0} embedded · vector search {stats?.embedded_memories ? 'available' : 'unavailable'}</div></div><div className="memory-search-box"><Search size={17} /><input autoFocus value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search memory content" /></div>{selectedMemoryId && <p className="memory-muted">Selected memory: <Hash value={selectedMemoryId} /></p>}<div className="memory-results">{results === null ? <div className="memory-empty-state"><Search size={22} /><strong>Search the local memory store</strong><span>Results include status, source, evidence class, and content hash.</span></div> : results.length === 0 ? <div className="memory-empty-state"><span>No matching memories.</span></div> : results.map((memory) => <MemoryListItem key={memory.id} memory={memory} onSelect={onSelectMemory} onUseContext={onUseContext} />)}</div>{selectedMemoryId && <section className="memory-similar"><div className="memory-block-header"><h3>Similar memories</h3><Badge>{similar.length}</Badge></div>{similar.length === 0 ? <p className="memory-muted">No similar memories available.</p> : similar.map((hit) => <button className="memory-list-button" key={hit.memory.id} onClick={() => onSelectMemory(hit.memory.id)} type="button"><span>{formatMemoryContent(hit.memory.content).slice(0, 120)}</span><Badge tone="good">{hit.cosine_similarity.toFixed(3)}</Badge></button>)}</section>}</section>;
}

function InferenceTab({ manifest, tasks, taskStatus, onTaskStatus, onQueue, onClaim, onComplete, onWriteBack, autoRefresh, onToggleAutoRefresh }: { manifest: InferenceManifest | null; tasks: InferenceTask[]; taskStatus: string; onTaskStatus: (value: string) => void; onQueue: (event: FormEvent<HTMLFormElement>) => void; onClaim: (task: InferenceTask) => void; onComplete: (task: InferenceTask) => void; onWriteBack: (task: InferenceTask, action: string) => void; autoRefresh: boolean; onToggleAutoRefresh: (val: boolean) => void }) {
    return <section className="memory-tab-panel"><div className="memory-panel-header"><div><span className="memory-eyebrow">Evidence-derived operations</span><h2>Inference</h2></div><Badge tone="warn">Local harness</Badge></div><div className="memory-inference-grid"><div className="memory-panel-block"><h3>Inference manifest</h3>{manifest ? <><p>{manifest.role}</p><dl className="memory-details"><dt>Task types</dt><dd>{manifest.task_types.join(', ')}</dd><dt>Tools</dt><dd>{manifest.tools.join(', ')}</dd></dl></> : <p className="memory-muted">Manifest unavailable.</p>}<form className="memory-queue-form" onSubmit={onQueue}><select name="task_type" defaultValue={manifest?.task_types[0] ?? 'summarize_session'}>{(manifest?.task_types ?? ['summarize_session', 'extract_entities', 'detect_contradictions']).map((type) => <option key={type}>{type}</option>)}</select><select name="subject_type" defaultValue="session"><option>session</option><option>memory</option><option>exchange</option><option>context_bundle</option></select><input name="subject_id" required placeholder="Subject id" /><button className="memory-primary-button" type="submit">Queue task</button></form></div><div className="memory-panel-block"><div className="memory-block-header"><h3>Task queue</h3><div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>{autoRefresh && <span className="memory-muted" style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}><RefreshCw size={12} className="memory-spin" /> Auto-refreshing</span>}<button className="memory-small-button" onClick={() => onToggleAutoRefresh(!autoRefresh)} type="button">{autoRefresh ? 'Stop polling' : 'Auto-refresh'}</button><select className="memory-select" value={taskStatus} onChange={(event) => onTaskStatus(event.target.value)}><option>pending</option><option>claimed</option><option>completed</option><option>failed</option></select></div></div>{tasks.length === 0 ? <p className="memory-muted">No tasks in this state.</p> : tasks.map((task) => <div className="memory-task-row" key={task.id}><div><strong>{task.task_type}</strong><span>{task.subject_type}:{task.subject_id}</span><small>{task.status} · {formatTime(task.updated_at)}</small></div><div className="memory-task-actions">{task.status === 'pending' && <button className="memory-small-button" onClick={() => onClaim(task)} type="button">Claim</button>}{task.status === 'claimed' && <button className="memory-small-button" onClick={() => onComplete(task)} type="button">Complete</button>}{task.status === 'completed' && <><button className="memory-small-button" onClick={() => onWriteBack(task, 'proposition')} type="button">Proposition</button><button className="memory-small-button" onClick={() => onWriteBack(task, 'contradiction')} type="button">Contradiction</button><button className="memory-small-button" onClick={() => onWriteBack(task, 'link')} type="button">Link entities</button><button className="memory-small-button" onClick={() => onWriteBack(task, 'supersede')} type="button">Supersede</button></>}</div></div>)}</div></div></section>;
}

function IntegrityTab({ status, links, root, exchanges, selectedMemoryId, events }: { status: StoreStatus | null; links: IntegrityLinksStatus | null; root: MerkleRoot | null; exchanges: Exchange[]; selectedMemoryId: string | null; events: MemoryEvent[] }) {
    return <section className="memory-tab-panel"><div className="memory-panel-header"><div><span className="memory-eyebrow">Local tamper evidence</span><h2>Integrity</h2></div><Badge tone={root?.valid === false || status?.integrity_check !== 'ok' ? 'bad' : 'good'}>{root?.valid === false ? 'Review required' : 'Local checks'}</Badge></div><div className="memory-integrity-grid"><div className="memory-panel-block"><h3>Store status</h3><div className="memory-status-grid"><StatusValue label="Schema" value={status ? String(status.schema_version) : 'n/a'} /><StatusValue label="Journal" value={status?.journal_mode ?? 'n/a'} /><StatusValue label="Foreign keys" value={status?.foreign_keys ? 'enabled' : 'disabled'} good={status?.foreign_keys} /><StatusValue label="FTS5" value={status?.fts5 ? 'enabled' : 'disabled'} good={status?.fts5} /><StatusValue label="Integrity check" value={status?.integrity_check ?? 'n/a'} good={status?.integrity_check === 'ok'} /><StatusValue label="Backup" value={status?.backup_ready ? 'ready' : 'not ready'} good={status?.backup_ready} /></div></div><div className="memory-panel-block"><h3>Integrity links</h3>{links ? <div className="memory-status-grid"><StatusValue label="Total memories" value={String(links.total_memories)} /><StatusValue label="Linked records" value={String(links.linked_records)} /><StatusValue label="States" value={Object.entries(links.states).map(([key, value]) => `${key}:${value}`).join(' · ')} /></div> : <p className="memory-muted">Integrity link status unavailable.</p>}</div><div className="memory-panel-block"><h3>Session Merkle root</h3><div className="memory-root-row"><span>Exchanges</span><strong>{root?.exchange_count ?? exchanges.length}</strong><Badge tone={root?.valid ? 'good' : 'warn'}>{root ? (root.valid ? 'valid' : 'invalid') : 'not anchored'}</Badge></div><div className="memory-item-meta"><Hash value={root?.root_node_id} /></div></div><div className="memory-panel-block"><h3>Selected event chain</h3>{selectedMemoryId ? <><p className="memory-muted">Memory: <Hash value={selectedMemoryId} /></p>{events.length === 0 ? <p className="memory-muted">No event records.</p> : <div className="memory-event-chain">{events.map((event) => <div className="memory-event-row" key={event.id}><strong>{event.event_type}</strong><span>{event.created_at}</span><Hash value={event.node_id} /><small>parent: {event.parent_event_id ?? 'root'}</small></div>)}</div>}</> : <p className="memory-muted">Select a memory to load its event chain.</p>}<p className="memory-boundary"><ShieldCheck size={15} /> Local integrity proves stored byte lineage and tamper evidence. It does not establish truth, authorization, or completeness.</p></div></div></section>;
}

function StatusValue({ label, value, good }: { label: string; value: string; good?: boolean }) {
    return <div className="memory-status-value"><span>{label}</span><strong className={good === undefined ? '' : good ? 'good' : 'bad'}>{good !== undefined && (good ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />)}{value}</strong></div>;
}

export default function MemoryPage() {
    const [activeTab, setActiveTab] = useState<Tab>('timeline');
    const [stats, setStats] = useState<GraphMemoryStats | null>(null);
    const [status, setStatus] = useState<StoreStatus | null>(null);
    const [links, setLinks] = useState<IntegrityLinksStatus | null>(null);
    const [sessions, setSessions] = useState<Session[]>([]);
    const [selectedSessionId, setSelectedSessionId] = useState('');
    const [exchanges, setExchanges] = useState<Exchange[]>([]);
    const [root, setRoot] = useState<MerkleRoot | null>(null);
    const [graph, setGraph] = useState<GraphPayload | null>(null);
    const [similarityThreshold, setSimilarityThreshold] = useState(0.75);
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<Memory[] | null>(null);
    const [similar, setSimilar] = useState<SimilarHit[]>([]);
    const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);
    const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
    const [selectedEvents, setSelectedEvents] = useState<MemoryEvent[]>([]);
    const [contextBundle, setContextBundle] = useState<Memory[]>([]);
    const [manifest, setManifest] = useState<InferenceManifest | null>(null);
    const [tasks, setTasks] = useState<InferenceTask[]>([]);
    const [taskStatus, setTaskStatus] = useState('pending');
    const [apiError, setApiError] = useState<string | null>(null);
    const [refreshing, setRefreshing] = useState(false);
    const [autoRefreshInference, setAutoRefreshInference] = useState(false);

    const refresh = async () => {
        setRefreshing(true);
        setApiError(null);
        try {
            const [nextStats, nextStatus, nextLinks, nextSessions, nextGraph, nextManifest] = await Promise.all([
                graphMemory.stats(), graphMemory.status(), graphMemory.integrityLinks(), graphMemory.sessions(), graphMemory.graph(500, similarityThreshold), graphMemory.inferenceManifest(),
            ]);
            setStats(nextStats); setStatus(nextStatus); setLinks(nextLinks); setSessions(nextSessions); setGraph(nextGraph); setManifest(nextManifest);
            if (!selectedSessionId && nextSessions[0]) setSelectedSessionId(nextSessions[0].external_session_id);
        } catch (error) { setApiError(String(error)); } finally { setRefreshing(false); }
    };

    useEffect(() => { void refresh(); }, []);
    useEffect(() => { const timer = window.setTimeout(() => { graphMemory.graph(500, similarityThreshold).then(setGraph).catch((error) => setApiError(String(error))); }, 180); return () => window.clearTimeout(timer); }, [similarityThreshold]);
    useEffect(() => { if (!selectedSessionId) { setExchanges([]); setRoot(null); return; } graphMemory.sessionExchanges(selectedSessionId).then(setExchanges).catch(() => setExchanges([])); graphMemory.sessionMerkleRoot(selectedSessionId).then(setRoot).catch(() => setRoot(null)); }, [selectedSessionId]);
    useEffect(() => {
        if (activeTab !== 'inference') return;
        graphMemory.inferenceTasks(taskStatus).then(setTasks).catch(() => setTasks([]));
        if (!autoRefreshInference) return;
        const timer = window.setInterval(() => {
            graphMemory.inferenceTasks(taskStatus).then(setTasks).catch(() => setTasks([]));
            graphMemory.inferenceManifest().then(setManifest).catch(() => {});
        }, 10000);
        return () => window.clearInterval(timer);
    }, [activeTab, taskStatus, autoRefreshInference]);
    useEffect(() => { if (!query.trim()) { setResults(null); return; } const timer = window.setTimeout(() => graphMemory.search(query, 50).then(setResults).catch(() => setResults([])), 220); return () => window.clearTimeout(timer); }, [query]);

    const selectMemory = (id: string) => { setSelectedMemoryId(id); setSelectedGraphNodeId(`memory:${id}`); void graphMemory.memoryEvents(id).then(setSelectedEvents).catch(() => setSelectedEvents([])); void graphMemory.similar(id).then(setSimilar).catch(() => setSimilar([])); };
    const selectGraphNode = (nodeId: string) => {
        setSelectedGraphNodeId(nodeId);
        if (nodeId.startsWith('memory:')) setSelectedMemoryId(nodeId.slice(7));
    };
    const recordExchange = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); const context = contextBundle.map((memory) => ({ memory_id: memory.id, context_kind: 'selected_context' })); try { await graphMemory.recordModelExchange({ external_session_id: String(form.get('session') || selectedSessionId), user_prompt: String(form.get('prompt') || ''), model_response: String(form.get('response') || ''), context, metadata: { source: 'integrity-mvp-memory-page' } }); setSelectedSessionId(String(form.get('session') || selectedSessionId)); await refresh(); } catch (error) { setApiError(String(error)); } };
    const queueTask = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { await graphMemory.requestInferenceTask({ task_type: String(form.get('task_type')), subject_type: String(form.get('subject_type')), subject_id: String(form.get('subject_id')), requested_by: 'integrity-mvp' }); setTasks(await graphMemory.inferenceTasks(taskStatus)); event.currentTarget.reset(); } catch (error) { setApiError(String(error)); } };
    const claimTask = async (task: InferenceTask) => { await graphMemory.claimInferenceTask(task.id, 'integrity-mvp'); setTasks(await graphMemory.inferenceTasks(taskStatus)); };
    const completeTask = async (task: InferenceTask) => { await graphMemory.completeInferenceTask(task.id, { completed_by: 'integrity-mvp', note: 'Completed from local operator console' }); setTasks(await graphMemory.inferenceTasks(taskStatus)); };
    const writeBack = async (task: InferenceTask, action: string) => { try { const output = task.output ?? task.input; if (action === 'proposition') await graphMemory.createProposition({ content: JSON.stringify(output), source_kind: 'inference', source_locator: task.id, evidence_class: 'derived' }); else if (action === 'contradiction') await graphMemory.markContradiction({ memory_id_a: task.subject_id, memory_id_b: String(output.memory_id ?? output.contradicts ?? ''), reason: `Inference task ${task.id} marked a contradiction` }); else if (action === 'link') await graphMemory.linkEntities({ subject: String(output.subject ?? output.subject_name ?? ''), predicate: String(output.predicate ?? 'related_to'), object: String(output.object ?? output.object_name ?? ''), evidence_memory_id: task.subject_id, confidence: Number(output.confidence ?? 1) }); else if (action === 'supersede') await graphMemory.supersedeMemory(task.subject_id, { new_content: String(output.new_content ?? output.content ?? JSON.stringify(output)), source: { kind: 'inference', locator: task.id }, evidence_class: 'derived' }); await refresh(); } catch (error) { setApiError(String(error)); } };

    return <div className="memory-page"><header className="memory-header"><div className="memory-title"><BrainCircuit size={25} /><div><span className="memory-eyebrow">Xibalba graph memory</span><h1>Memory</h1></div></div><div className="memory-health"><Badge tone={apiError ? 'bad' : 'good'}>{apiError ? 'API unavailable' : 'API connected'}</Badge><Badge>{stats?.memories ?? 0} memories</Badge><Badge>{stats?.entities ?? 0} entities</Badge><Badge>{stats?.relations ?? 0} relations</Badge><Badge>schema {status?.schema_version ?? 'n/a'}</Badge><button className="memory-icon-button" onClick={() => void refresh()} type="button" title="Refresh memory data" aria-label="Refresh memory data"><RefreshCw size={16} className={refreshing ? 'memory-spin' : ''} /></button></div></header>{apiError && <div className="memory-api-banner"><AlertTriangle size={16} /> {apiError} <span>Start xibalba-graph-memory local_api to reconnect.</span></div>}<div className="memory-shell"><SessionRail sessions={sessions} selectedSessionId={selectedSessionId} onSelect={setSelectedSessionId} /><main className="memory-workspace"><nav className="memory-tabs" aria-label="Memory views">{TABS.map(({ id, label, icon: Icon }) => <button className={activeTab === id ? 'active' : ''} key={id} onClick={() => setActiveTab(id)} type="button"><Icon size={16} />{label}</button>)}</nav>{activeTab === 'timeline' && <TimelineTab exchanges={exchanges} selectedSessionId={selectedSessionId} sessions={sessions} contextBundle={contextBundle} onSelectMemory={selectMemory} onRecord={recordExchange} onSelectSession={setSelectedSessionId} />}{activeTab === 'graph' && <GraphTab graph={graph} selectedNodeId={selectedGraphNodeId} onSelectNode={selectGraphNode} onSelectMemory={selectMemory} similarityThreshold={similarityThreshold} onThreshold={setSimilarityThreshold} sessions={sessions} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} />}{activeTab === 'recall' && <RecallTab results={results} query={query} onQuery={setQuery} onSelectMemory={selectMemory} onUseContext={(memory) => setContextBundle((current) => current.some((item) => item.id === memory.id) ? current : [...current, memory])} selectedMemoryId={selectedMemoryId} similar={similar} stats={stats} />}{activeTab === 'inference' && <InferenceTab manifest={manifest} tasks={tasks} taskStatus={taskStatus} onTaskStatus={setTaskStatus} onQueue={queueTask} onClaim={(task) => void claimTask(task)} onComplete={(task) => void completeTask(task)} onWriteBack={(task, action) => void writeBack(task, action)} autoRefresh={autoRefreshInference} onToggleAutoRefresh={setAutoRefreshInference} />}{activeTab === 'integrity' && <IntegrityTab status={status} links={links} root={root} exchanges={exchanges} selectedMemoryId={selectedMemoryId} events={selectedEvents} />}</main><Inspector memoryId={selectedMemoryId} onClose={() => { setSelectedMemoryId(null); setSelectedGraphNodeId(null); setSelectedEvents([]); setSimilar([]); }} onSelectMemory={selectMemory} /></div></div>;
}
