import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BrainCircuit,
  Clock3,
  GitMerge,
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

import { SubTabs } from '../components/ui/SubTabs';
import { SystemSummaryCard } from '../components/shared/SystemSummaryCard';
import { useDashboard } from '../context/DashboardContext';
import {
  oracle,
  type AisHistoryPoint,
  type AisResponse,
  type HistoryBucket,
} from '../services/oracle';
import CorrelationPage from './CorrelationPage';
import { IntelligencePage } from './IntelligencePage';

type KnowledgeTab = 'overview' | 'intelligence' | 'evidence';

const TABS = [
  { id: 'overview', label: 'AIS & knowledge', icon: <Sparkles size={14} /> },
  { id: 'intelligence', label: 'Agent intelligence', icon: <Activity size={14} /> },
  { id: 'evidence', label: 'Evidence correlation', icon: <GitMerge size={14} /> },
];

const BUCKETS: Array<{ id: HistoryBucket; label: string }> = [
  { id: '5m', label: '5 minutes' },
  { id: '1h', label: 'Hourly' },
  { id: '1d', label: 'Daily' },
  { id: '1w', label: 'Weekly' },
];

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

// A large local Cortex profile can take longer to assemble graph edges than the
// rest of the operator summary. Keep that optional panel from blocking the
// already-available memory/status cards indefinitely.
function bounded<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error('graph request timed out')), timeoutMs)),
  ]);
}

function PanelHeading({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return (
    <div className="protocol-panel-heading">
      <div>
        <span className="panel-label">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {meta && <span className="panel-count">{meta}</span>}
    </div>
  );
}

function KnowledgeOverview() {
  const { selectedAgent } = useDashboard();
  const [bucket, setBucket] = useState<HistoryBucket>('1h');
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [history, setHistory] = useState<AisHistoryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceErrors, setSourceErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    const agentId = selectedAgent?.eth_address;
    const requests = await Promise.allSettled([
      agentId ? oracle.getAis(agentId) : Promise.resolve(null),
      agentId ? oracle.getAisHistory(agentId, bucket) : Promise.resolve([]),
    ]);

    const [aisResult, historyResult] = requests;
    const errors: string[] = [];

    if (aisResult.status === 'fulfilled') setAis(aisResult.value);
    else { setAis(null); errors.push('Current AIS unavailable'); }
    if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
    else { setHistory([]); errors.push('AIS history unavailable'); }

    setSourceErrors(errors);
    setLoading(false);
  }, [bucket, selectedAgent?.eth_address]);

  useEffect(() => { void load(); }, [load]);

  const aisChart = useMemo(() => history.map((point) => ({
    ...point,
    label: chartTime(point.bucket_start, bucket),
  })), [history, bucket]);

  const sourceState = sourceErrors.length === 0 ? 'online' : sourceErrors.length < 5 ? 'degraded' : 'offline';

  return (
    <div className="knowledge-overview">
      <div className="knowledge-context-bar" aria-label="Knowledge source context">
        <div>
          <span className="knowledge-context-icon"><BrainCircuit size={17} /></span>
          <div><strong>{selectedAgent?.alias || selectedAgent?.name || shortAgent(selectedAgent?.id)}</strong><small>{shortAgent(selectedAgent?.id)}</small></div>
        </div>
        <div><span>Oracle evidence</span><strong className={sourceState}>{sourceErrors.length ? 'Partial' : 'Available'}</strong></div>
        <div className="knowledge-context-note"><ShieldCheck size={15} /><span>AIS is protocol-native, computed by Integrity Core. Cortex owns knowledge/evidence storage -- see its own console for graph exploration.</span></div>
      </div>

      <div className="control-metric-grid knowledge-metric-grid">
        <div className="control-metric"><span><Activity size={14} /> Current AIS</span><strong>{compactNumber(ais?.ais)}</strong><small>{ais ? `${ais.event_count} scored events · zk ×${ais.zk_boost.toFixed(2)}` : 'No current Oracle reading'}</small></div>
      </div>

      <div className="knowledge-toolbar">
        <div><Clock3 size={15} /><span>Time resolution</span>{BUCKETS.map((item) => <button type="button" key={item.id} className={bucket === item.id ? 'active' : undefined} onClick={() => setBucket(item.id)}>{item.label}</button>)}</div>
        <button type="button" className="control-secondary-action" onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : undefined} /> Refresh evidence</button>
      </div>

      {sourceErrors.length > 0 && <div className="knowledge-source-warning"><Activity size={15} /><span>Partial evidence view: {sourceErrors.join(' · ')}</span></div>}

      <div className="knowledge-visual-grid">
        <section className="protocol-panel knowledge-chart-panel">
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

      <section className="protocol-panel knowledge-graph-panel">
        <PanelHeading eyebrow="Cortex" title="Knowledge & evidence storage" />
        <SystemSummaryCard system="cortex" />
      </section>

      <div className="knowledge-assurance-note"><ShieldCheck size={14} /><span>Signed telemetry can contribute to AIS. Vendor OTel remains operational context only; detailed telemetry and integrity vectors are available in Agent intelligence.</span></div>
    </div>
  );
}

export default function IntelligenceControlPage() {
  const [tab, setTab] = useState('overview');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <SubTabs tabs={TABS} activeTab={tab} setActiveTab={setTab} />
      <div style={{ marginTop: 'var(--space-2)' }}>
        {tab === 'overview' && <KnowledgeOverview />}
        {tab === 'intelligence' && <IntelligencePage />}
        {tab === 'evidence' && <CorrelationPage />}
      </div>
    </div>
  );
}