import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  BrainCircuit,
  Clock3,
  Database,
  GitMerge,
  Network,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import { EvidenceGraph2D, type EvidenceGraph2DHandle } from '../components/control/EvidenceGraph2D';
import { useDashboard } from '../context/DashboardContext';
import { graphMemory, type GraphMemoryStats, type GraphPayload, type StoreStatus } from '../services/graphMemory';
import {
  oracle,
  type AisHistoryPoint,
  type AisResponse,
  type HistoryBucket,
} from '../services/oracle';
import CorrelationPage from './CorrelationPage';
import CortexPage from './CortexPage';
import { IntelligencePage } from './IntelligencePage';

type KnowledgeTab = 'overview' | 'intelligence' | 'cortex' | 'evidence';

const TABS: ControlTab<KnowledgeTab>[] = [
  { id: 'overview', label: 'AIS & knowledge', icon: Sparkles },
  { id: 'intelligence', label: 'Agent intelligence', icon: Activity },
  { id: 'cortex', label: 'Cortex workspace', icon: BrainCircuit },
  { id: 'evidence', label: 'Evidence correlation', icon: GitMerge },
];

const BUCKETS: Array<{ id: HistoryBucket; label: string }> = [
  { id: '5m', label: '5 minutes' },
  { id: '1h', label: 'Hourly' },
  { id: '1d', label: 'Daily' },
  { id: '1w', label: 'Weekly' },
];

const EMPTY_GRAPH: GraphPayload = { nodes: [], edges: [] };

function compactNumber(value: number | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return Intl.NumberFormat('en-US', { notation: value >= 10_000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value);
}

function shortAgent(value: string | undefined) {
  if (!value) return 'No agent selected';
  if (value.length < 22) return value;
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function chartTime(value: string, bucket: HistoryBucket) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  if (bucket === '1d' || bucket === '1w') return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function PanelHeading({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return (
    <div className="control-section-heading">
      <div>
        <span className="control-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {meta && <span className="control-count">{meta}</span>}
    </div>
  );
}

function KnowledgeOverview() {
  const { selectedAgent } = useDashboard();
  const graphRef = useRef<EvidenceGraph2DHandle>(null);
  const [bucket, setBucket] = useState<HistoryBucket>('1h');
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [history, setHistory] = useState<AisHistoryPoint[]>([]);
  const [stats, setStats] = useState<GraphMemoryStats | null>(null);
  const [store, setStore] = useState<StoreStatus | null>(null);
  const [graph, setGraph] = useState<GraphPayload>(EMPTY_GRAPH);
  const [pendingInference, setPendingInference] = useState<number | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sourceErrors, setSourceErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    const agentId = selectedAgent?.eth_address;
    const requests = await Promise.allSettled([
      agentId ? oracle.getAis(agentId) : Promise.resolve(null),
      agentId ? oracle.getAisHistory(agentId, bucket) : Promise.resolve([]),
      graphMemory.stats(),
      graphMemory.status(),
      graphMemory.graph(220, 0.78),
      graphMemory.inferenceTasks('pending', 50),
    ]);

    const [aisResult, historyResult, statsResult, storeResult, graphResult, inferenceResult] = requests;
    const errors: string[] = [];

    if (aisResult.status === 'fulfilled') setAis(aisResult.value);
    else { setAis(null); errors.push('Current AIS unavailable'); }
    if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
    else { setHistory([]); errors.push('AIS history unavailable'); }
    if (statsResult.status === 'fulfilled') setStats(statsResult.value);
    else { setStats(null); errors.push('Cortex statistics unavailable'); }
    if (storeResult.status === 'fulfilled') setStore(storeResult.value);
    else { setStore(null); errors.push('Cortex integrity status unavailable'); }
    if (graphResult.status === 'fulfilled') {
      setGraph(graphResult.value);
      setSelectedNodeId((current) => current && graphResult.value.nodes.some((node) => node.id === current) ? current : graphResult.value.nodes[0]?.id ?? null);
    } else {
      setGraph(EMPTY_GRAPH);
      setSelectedNodeId(null);
      errors.push('Evidence graph unavailable');
    }
    if (inferenceResult.status === 'fulfilled') setPendingInference(inferenceResult.value.length);
    else { setPendingInference(null); errors.push('Inference queue unavailable'); }

    setSourceErrors(errors);
    setLoading(false);
  }, [bucket, selectedAgent?.eth_address]);

  useEffect(() => { void load(); }, [load]);

  const selectedNode = useMemo(() => graph.nodes.find((node) => node.id === selectedNodeId) ?? null, [graph.nodes, selectedNodeId]);
  const selectedEdges = useMemo(() => graph.edges.filter((edge) => {
    const source = typeof edge.source === 'string' ? edge.source : String((edge.source as { id?: string }).id);
    const target = typeof edge.target === 'string' ? edge.target : String((edge.target as { id?: string }).id);
    return source === selectedNodeId || target === selectedNodeId;
  }), [graph.edges, selectedNodeId]);

  const aisChart = useMemo(() => history.map((point) => ({
    ...point,
    label: chartTime(point.bucket_start, bucket),
  })), [history, bucket]);

  const integrityState = store?.integrity_check === 'ok';
  const sourceState = sourceErrors.length === 0 ? 'online' : sourceErrors.length < 5 ? 'degraded' : 'offline';

  return (
    <div className="knowledge-overview">
      <div className="knowledge-context-bar" aria-label="Knowledge source context">
        <div>
          <span className="knowledge-context-icon"><BrainCircuit size={17} /></span>
          <div><strong>{selectedAgent?.alias || selectedAgent?.name || shortAgent(selectedAgent?.id)}</strong><small>{shortAgent(selectedAgent?.id)}</small></div>
        </div>
        <div><span>Oracle evidence</span><strong className={sourceState}>{sourceErrors.length ? 'Partial' : 'Available'}</strong></div>
        <div><span>Cortex store</span><strong className={integrityState ? 'online' : store ? 'degraded' : 'offline'}>{store ? (integrityState ? 'Integrity OK' : store.integrity_check) : 'Unavailable'}</strong></div>
        <div><span>Graph filter</span><strong>Similarity ≥ 0.78</strong></div>
        <div className="knowledge-context-note"><ShieldCheck size={15} /><span>AIS and graph evidence retain separate provenance and assurance boundaries.</span></div>
      </div>

      <div className="control-metric-grid knowledge-metric-grid">
        <div className="control-metric"><span><Activity size={14} /> Current AIS</span><strong>{compactNumber(ais?.ais)}</strong><small>{ais ? `${ais.event_count} scored events · zk ×${ais.zk_boost.toFixed(2)}` : 'No current Oracle reading'}</small></div>
        <div className="control-metric"><span><Database size={14} /> Cortex memories</span><strong>{compactNumber(stats?.memories)}</strong><small>{stats ? `${compactNumber(stats.embedded_memories)} embedded` : 'Store statistics unavailable'}</small></div>
        <div className="control-metric"><span><Network size={14} /> Graph evidence</span><strong>{compactNumber(graph.nodes.length)}</strong><small>{compactNumber(graph.edges.length)} visible relationships</small></div>
        <div className={`control-metric ${pendingInference ? 'attention' : ''}`}><span><BrainCircuit size={14} /> Inference queue</span><strong>{compactNumber(pendingInference ?? undefined)}</strong><small>{pendingInference == null ? 'Queue unavailable' : pendingInference ? 'Pending review or processing' : 'No pending tasks'}</small></div>
      </div>

      <div className="knowledge-toolbar">
        <div><Clock3 size={15} /><span>Time resolution</span>{BUCKETS.map((item) => <button type="button" key={item.id} className={bucket === item.id ? 'active' : undefined} onClick={() => setBucket(item.id)}>{item.label}</button>)}</div>
        <button type="button" className="control-secondary-action" onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : undefined} /> Refresh evidence</button>
      </div>

      {sourceErrors.length > 0 && <div className="knowledge-source-warning"><Activity size={15} /><span>Partial evidence view: {sourceErrors.join(' · ')}</span></div>}

      <div className="knowledge-visual-grid">
        <section className="control-section knowledge-chart-panel">
          <PanelHeading eyebrow="Oracle AIS" title="AIS time series" meta={`${aisChart.length} buckets`} />
          <div className="knowledge-chart-stage">
            {aisChart.length === 0 ? <div className="chart-empty">No AIS history is available for this agent and resolution.</div> : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={aisChart} margin={{ top: 14, right: 18, left: -8, bottom: 4 }}>
                  <CartesianGrid stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--text-muted)" tick={{ fontSize: 10 }} minTickGap={28} />
                  <YAxis domain={[0, 1000]} stroke="var(--text-muted)" tick={{ fontSize: 10 }} width={42} />
                  <Tooltip contentStyle={{ background: 'var(--surface-color)', border: '1px solid var(--border-color)', borderRadius: 5, fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Line type="monotone" dataKey="ais" name="AIS" stroke="var(--accent-color)" strokeWidth={2.2} dot={false} activeDot={{ r: 4 }} />
                  <Line type="monotone" dataKey="grounding" name="Grounding" stroke="#5b8def" strokeWidth={1.2} dot={false} />
                  <Line type="monotone" dataKey="compliance" name="Compliance" stroke="#f59e0b" strokeWidth={1.2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

      </div>

      <section className="control-section knowledge-graph-panel">
        <PanelHeading eyebrow="Cortex knowledge graph" title="Knowledge evidence graph" meta={`${graph.nodes.length} nodes · ${graph.edges.length} edges`} />
        <div className="knowledge-graph-layout">
          <div className="knowledge-graph-stage">
            {graph.nodes.length === 0 ? <div className="chart-empty">No Cortex graph data is available. This is not treated as positive evidence.</div> : <EvidenceGraph2D ref={graphRef} data={graph} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />}
            <div className="knowledge-graph-legend" aria-label="Evidence graph legend"><span><i className="memory" />Memory</span><span><i className="entity" />Entity</span><span><i className="similarity" />Similarity</span><span><i className="contradiction" />Contradiction</span></div>
            {graph.nodes.length > 0 && <button className="knowledge-fit-button" type="button" onClick={() => graphRef.current?.zoomToFit()}>Fit graph</button>}
          </div>
          <aside className="knowledge-node-inspector">
            <span className="control-eyebrow">Selected evidence</span>
            {selectedNode ? <>
              <h3>{selectedNode.label}</h3>
              <code title={selectedNode.id}>{selectedNode.id}</code>
              <dl>
                <div><dt>Type</dt><dd>{selectedNode.type}</dd></div>
                <div><dt>Status</dt><dd>{selectedNode.status ?? 'not reported'}</dd></div>
                <div><dt>Evidence class</dt><dd>{selectedNode.evidence_class ?? 'not reported'}</dd></div>
                <div><dt>Source kind</dt><dd>{selectedNode.source_kind ?? 'not reported'}</dd></div>
                <div><dt>Relationships</dt><dd>{selectedEdges.length}</dd></div>
              </dl>
              <div className="knowledge-edge-list">{selectedEdges.slice(0, 8).map((edge, index) => <span key={`${edge.type}-${index}`}><i className={edge.type} />{edge.predicate || edge.type}</span>)}</div>
            </> : <p>Select a memory or entity to inspect its provenance and relationships.</p>}
          </aside>
        </div>
      </section>

      <div className="knowledge-assurance-note"><ShieldCheck size={14} /><span>Signed telemetry can contribute to AIS. Vendor OTel remains operational context only; detailed telemetry and integrity vectors are available in Agent intelligence.</span></div>
    </div>
  );
}

export default function KnowledgeControlPage() {
  const [tab, setTab] = useState<KnowledgeTab>('overview');

  return (
    <div className="control-page control-page-full knowledge-control-page">
      <ControlHeader
        eyebrow="Intelligence control plane"
        title="Knowledge & Evidence"
        description="Monitor AIS behavior over time, explore Cortex knowledge relationships, and trace decisions from agent intent through enforcement and outcome evidence."
      />
      <ControlTabs tabs={TABS} active={tab} onChange={setTab} label="Knowledge and evidence views" />
      <div className="control-page-body control-hub-content">
        {tab === 'overview' && <KnowledgeOverview />}
        {tab === 'intelligence' && <IntelligencePage />}
        {tab === 'cortex' && <CortexPage />}
        {tab === 'evidence' && <CorrelationPage />}
      </div>
    </div>
  );
}
