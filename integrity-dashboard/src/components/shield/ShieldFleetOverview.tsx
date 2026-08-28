import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, ShieldCheck, ShieldAlert, ShieldOff, Radio, Server, Link2, FileCheck2, Boxes, Eye, Cpu, FileText, Network, Users, Activity, Gauge, Target, Timer } from 'lucide-react';
import { Panel } from '../shared/Panel';
import { useDashboard } from '../../context/DashboardContext';
import { shieldBackend } from '../../services/shieldBackend';
import type { ShieldDashboardSummary, ShieldDetectionQuality, ShieldEnforcementOutcome } from '../../services/shieldBackend';
import { ShieldEvidenceGraph, type ShieldEvidenceGraphHandle } from '../ShieldEvidenceGraph';

// Real fleet/decisions dashboard for xibalba-shield's backend (shield/backend/api.py) --
// what Shield actually is (per its own CLAUDE.md): a fleet-level enforcement/detection
// platform, not the single-machine attack simulator that used to be this page's entire
// identity. All data below is read from shieldBackend.dashboardSummary(); an empty tenant
// shows an honest "no devices enrolled" state, never fabricated rows.

function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return 'just now';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STALE_MS = 5 * 60 * 1000;

// shield/schemas/events.py's real `klass` values (one per Event dataclass) -- the actual
// wire-format strings Shield tags every observation with, not a UI-invented category list.
const EVENT_CLASS_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  process_activity: { label: 'Process activity', icon: <Cpu size={14} />, color: '#60a5fa' },
  file_activity: { label: 'File activity', icon: <FileText size={14} />, color: '#34d399' },
  network_flow: { label: 'Network flow', icon: <Network size={14} />, color: '#f59e0b' },
  agent_event: { label: 'Agent tool calls', icon: <Users size={14} />, color: '#a78bfa' },
  policy_decision: { label: 'Policy decisions', icon: <Activity size={14} />, color: '#f472b6' },
  enforcement_outcome: { label: 'Enforcement outcomes', icon: <ShieldCheck size={14} />, color: '#94a3b8' },
};
function classMeta(cls: string | undefined) {
  const key = (cls || '').toLowerCase();
  return EVENT_CLASS_META[key] ?? { label: cls || 'unclassified', icon: <Radio size={14} />, color: 'var(--text-muted)' };
}

// detection_quality's aggregate fields are nullable (e.g. mean_time_to_contain_sec has no
// value when nothing was ever contained) -- render that honestly as "n/a", not 0 or a crash.
function pct(v: number | null): string {
  return v == null ? 'n/a' : `${(v * 100).toFixed(1)}%`;
}
function secs(v: number | null): string {
  return v == null ? 'n/a' : `${v.toFixed(1)}s`;
}

function actionTone(action: string | undefined): { label: string; color: string; bg: string } {
  const a = (action || '').toLowerCase();
  if (a === 'contain' || a === 'deny') return { label: a.toUpperCase(), color: '#f43f5e', bg: 'rgba(244,63,94,0.12)' };
  if (a === 'escalate') return { label: 'ESCALATE', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' };
  if (a === 'allow' || a === 'log_only') return { label: a === 'allow' ? 'ALLOW' : 'LOG ONLY', color: '#10b981', bg: 'rgba(16,185,129,0.12)' };
  return { label: (action || 'UNKNOWN').toUpperCase(), color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.05)' };
}

export default function ShieldFleetOverview() {
  const { selectedAgent } = useDashboard();
  const [tenantId, setTenantId] = useState('');
  const [summary, setSummary] = useState<ShieldDashboardSummary | null>(null);
  const [detectionQuality, setDetectionQuality] = useState<ShieldDetectionQuality[]>([]);
  const [enforcementOutcomes, setEnforcementOutcomes] = useState<ShieldEnforcementOutcome[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [background, setBackground] = useState<'light' | 'dark' | 'plain' | 'blueprint'>('dark');
  const [edgeType, setEdgeType] = useState('all');
  const graphRef = useRef<ShieldEvidenceGraphHandle>(null);

  useEffect(() => {
    if (selectedAgent?.eth_address && !tenantId) setTenantId(selectedAgent.eth_address);
  }, [selectedAgent?.eth_address, tenantId]);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await shieldBackend.dashboardSummary(id);
      setSummary(result);
      // Best-effort, independent reads -- neither being unavailable should hide the fleet
      // summary that just loaded fine.
      const [qualityR, outcomesR] = await Promise.allSettled([
        shieldBackend.detectionQuality(id),
        shieldBackend.enforcementOutcomes(id),
      ]);
      setDetectionQuality(qualityR.status === 'fulfilled' ? qualityR.value.detection_quality : []);
      setEnforcementOutcomes(outcomesR.status === 'fulfilled' ? outcomesR.value.enforcement_outcomes : []);
    } catch (e) {
      setSummary(null);
      setDetectionQuality([]);
      setEnforcementOutcomes([]);
      setError(e instanceof Error ? e.message : 'Could not load Shield fleet data for this tenant.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tenantId) load(tenantId);
  }, [tenantId, load]);

  const deviceCount = summary?.device_count ?? 0;
  const decisionCounts = summary?.decisions_by_action ?? {};
  const blockedCount = (decisionCounts['contain'] ?? 0) + (decisionCounts['deny'] ?? 0);
  const escalateCount = decisionCounts['escalate'] ?? 0;
  const allowCount = (decisionCounts['allow'] ?? 0) + (decisionCounts['log_only'] ?? 0);

  // What kind of raw machine activity Shield actually classified each decision's triggering
  // event as -- real tally over event_ref.class from summary.latest_decisions, not a
  // separately-fabricated breakdown. This is "what Shield sees on the machine," derived
  // straight from live enforcement data.
  const classCounts: Record<string, number> = {};
  (summary?.latest_decisions ?? []).forEach((d) => {
    const cls = (d.decision.event_ref?.class || d.decision.class || 'unclassified').toLowerCase();
    classCounts[cls] = (classCounts[cls] ?? 0) + 1;
  });
  const classEntries = Object.entries(classCounts).sort((a, b) => b[1] - a[1]);
  const maxClassCount = classEntries.length ? classEntries[0][1] : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        <img src="/shield-logo.png" alt="Xibalba Shield" style={{ width: '56px', height: '56px', objectFit: 'contain', flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: '1.1rem', fontWeight: 800 }}>Xibalba Shield</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            The AI agent security platform -- real device enrollment, policy, and enforcement data below.
          </div>
        </div>
      </div>

      <Panel title="Fleet tenant" icon={<Server size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: '0 0 var(--space-4)' }}>
          Real device enrollment, policy, and enforcement-decision data from the Shield backend (<code>shield/backend/api.py</code>).
          Defaults to the active agent's identity as tenant -- the same tenant the Guided System Test wizard's Shield step seeds.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="tenant id"
            style={{
              flex: 1, minWidth: 0, background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-3)', color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono, monospace)', fontSize: '0.85rem',
            }}
          />
          <button
            type="button"
            onClick={() => load(tenantId)}
            disabled={loading || !tenantId}
            style={{
              display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'var(--primary)',
              border: 'none', borderRadius: 'var(--radius-md)', padding: '0 var(--space-4)', height: '42px',
              color: 'var(--bg-primary, #000)', fontWeight: 600, fontSize: '0.85rem',
              cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.6 : 1,
            }}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </Panel>

      {error && (
        <Panel icon={<ShieldAlert size={16} />}>
          <div style={{ color: 'var(--danger, #e5484d)', fontSize: '0.85rem', padding: 'var(--space-2) 0' }}>{error}</div>
        </Panel>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-4)' }}>
        <SummaryCard icon={<Boxes size={18} />} label="Enrolled devices" value={deviceCount} />
        <SummaryCard icon={<ShieldOff size={18} />} label="Denied / contained" value={blockedCount} tone="#f43f5e" />
        <SummaryCard icon={<ShieldAlert size={18} />} label="Escalated" value={escalateCount} tone="#f59e0b" />
        <SummaryCard icon={<ShieldCheck size={18} />} label="Allowed / log-only" value={allowCount} tone="#10b981" />
      </div>

      {!loading && !error && summary && deviceCount === 0 && (
        <Panel>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: 'var(--space-6) 0' }}>
            No devices enrolled for this tenant yet -- run the Guided System Test wizard's Shield step (Developer page),
            or enroll one directly via <code>POST /api/shield/enroll</code>.
          </div>
        </Panel>
      )}

      {summary && classEntries.length > 0 && (
        <Panel title="What Shield sees on this fleet" icon={<Eye size={16} />}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-4)' }}>
            Real breakdown of recent enforcement decisions by the machine-activity class that triggered them
            (Shield's own event taxonomy -- process, file, network flow, and agent tool-call activity).
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {classEntries.map(([cls, count]) => {
              const meta = classMeta(cls);
              return (
                <div key={cls} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', width: '170px', flexShrink: 0, color: meta.color, fontSize: '0.8rem' }}>
                    {meta.icon} {meta.label}
                  </div>
                  <div style={{ flex: 1, height: '10px', borderRadius: '5px', background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(count / maxClassCount) * 100}%`, background: meta.color, transition: 'width 0.2s ease' }} />
                  </div>
                  <div style={{ width: '32px', textAlign: 'right', fontWeight: 700, fontSize: '0.8rem' }}>{count}</div>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {summary && deviceCount > 0 && (
        <Panel
          title="Evidence graph"
          icon={<Eye size={16} />}
          action={
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
              <select
                value={edgeType}
                onChange={(e) => setEdgeType(e.target.value)}
                style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '4px 8px', color: 'var(--text-primary)', fontSize: '0.75rem' }}
              >
                <option value="all">All edges</option>
                <option value="enrollment">Enrollment</option>
                <option value="policy">Policy</option>
                <option value="decision">Decision</option>
                <option value="export">Export</option>
                <option value="integration">Integration</option>
                <option value="metrics">Metrics</option>
              </select>
              <select
                value={background}
                onChange={(e) => setBackground(e.target.value as typeof background)}
                style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '4px 8px', color: 'var(--text-primary)', fontSize: '0.75rem' }}
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="blueprint">Blueprint</option>
                <option value="plain">Plain</option>
              </select>
              <button
                type="button"
                onClick={() => graphRef.current?.zoomToFit()}
                style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '4px 10px', color: 'var(--text-primary)', fontSize: '0.75rem', cursor: 'pointer' }}
              >
                Zoom to fit
              </button>
            </div>
          }
        >
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-3)' }}>
            Tenant → devices → policies → decisions → exports, built live from the same summary below.
          </p>
          <ShieldEvidenceGraph ref={graphRef} summary={summary} background={background} edgeType={edgeType} />
        </Panel>
      )}

      {summary && deviceCount > 0 && (
        <Panel title="Devices" icon={<Boxes size={16} />}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  <th style={{ padding: 'var(--space-2) var(--space-3)' }}>Device</th>
                  <th style={{ padding: 'var(--space-2) var(--space-3)' }}>Role</th>
                  <th style={{ padding: 'var(--space-2) var(--space-3)' }}>Policy hash</th>
                  <th style={{ padding: 'var(--space-2) var(--space-3)' }}>Last seen</th>
                  <th style={{ padding: 'var(--space-2) var(--space-3)' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {summary.devices.map((d) => {
                  const stale = !d.last_seen_at || Date.now() - new Date(d.last_seen_at).getTime() > STALE_MS;
                  return (
                    <tr key={d.device_id} style={{ borderTop: '1px solid var(--glass-border)' }}>
                      <td style={{ padding: 'var(--space-2) var(--space-3)', fontFamily: 'var(--font-mono, monospace)' }}>{d.device_id}</td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)' }}>{d.device_role}</td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)', fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-muted)' }}>
                        {d.policy_hash ? `${d.policy_hash.slice(0, 10)}…` : 'none'}
                      </td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--text-muted)' }}>{timeAgo(d.last_seen_at)}</td>
                      <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', fontWeight: 700,
                          padding: '2px 8px', borderRadius: '999px',
                          color: stale ? '#f59e0b' : '#10b981',
                          background: stale ? 'rgba(245,158,11,0.12)' : 'rgba(16,185,129,0.12)',
                        }}>
                          <Radio size={10} /> {stale ? 'STALE' : 'ONLINE'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {summary && summary.latest_decisions.length > 0 && (
        <Panel title="Recent decisions" icon={<ShieldAlert size={16} />}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.latest_decisions.map((d, idx) => {
              const tone = actionTone(d.decision.decision?.action);
              return (
                <div
                  key={`${d.decision.event_ref?.event_id ?? 'noref'}-${idx}`}
                  style={{
                    display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center',
                    padding: 'var(--space-3) 0', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem',
                  }}
                >
                  <span style={{ width: '84px', color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                    {d.received_at ? new Date(d.received_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                  </span>
                  <span style={{
                    fontWeight: 800, fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px',
                    color: tone.color, background: tone.bg,
                  }}>
                    {tone.label}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-muted)' }}>
                    {d.decision.device_id ?? 'unknown device'}
                  </span>
                  <span style={{ flex: 1, minWidth: '200px' }}>
                    {d.decision.rule?.name ?? d.decision.rule?.rule_id ?? 'unnamed rule'}
                  </span>
                  {d.decision.decision?.reason && (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{d.decision.decision.reason}</span>
                  )}
                  {d.decision.export?.decision_exported && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.68rem', color: '#10b981' }}>
                      <FileCheck2 size={12} /> exported
                    </span>
                  )}
                  {d.decision.synthetic && (
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>synthetic</span>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {detectionQuality.length > 0 && (
        <Panel title="Detection quality" icon={<Gauge size={16} />}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-4)' }}>
            Shield's own scorecard, computed from recorded decisions per device -- not a fabricated demo metric.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {detectionQuality.map((dq) => {
              const agg = dq.quality.aggregate;
              return (
                <div key={`${dq.device_id}-${dq.received_at}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)', alignItems: 'center', padding: 'var(--space-3) 0', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem' }}>
                  <span style={{ fontFamily: 'var(--font-mono, monospace)', width: '140px', flexShrink: 0 }}>{dq.device_id}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981' }}><Target size={12} /> ADR {pct(agg.shield_adr)}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#60a5fa' }}><ShieldCheck size={12} /> Precision {pct(agg.precision)}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#f43f5e' }}><ShieldAlert size={12} /> FP rate {pct(agg.blocking_false_positive_rate)}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#f59e0b' }}><Timer size={12} /> MTTC {secs(agg.mean_time_to_contain_sec)}</span>
                  {dq.quality.synthetic && <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>synthetic</span>}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {enforcementOutcomes.length > 0 && (
        <Panel title="Enforcement outcomes" icon={<ShieldCheck size={16} />}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-3)' }}>
            What actually happened when a decision's chosen action was carried out on the device -- the forward-link
            counterpart to Recent decisions above, keyed by the same triggering event.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {enforcementOutcomes.map((o, idx) => (
              <div key={`${o.outcome.event_id}-${idx}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center', padding: 'var(--space-2) 0', borderBottom: '1px solid var(--glass-border)', fontSize: '0.8rem' }}>
                <span style={{ width: '84px', color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                  {o.received_at ? new Date(o.received_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                </span>
                <span style={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase' }}>{o.outcome.action}</span>
                <span style={{ color: o.outcome.completed ? '#10b981' : '#f43f5e', fontSize: '0.75rem' }}>
                  {o.outcome.completed ? 'completed' : 'not completed'}
                </span>
                {o.outcome.escalated && <span style={{ color: '#f59e0b', fontSize: '0.75rem' }}>escalated</span>}
                <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-muted)', fontSize: '0.72rem' }}>{o.outcome.event_id}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {summary && summary.exporter_status.length > 0 && (
        <Panel title="Exporter status" icon={<FileCheck2 size={16} />}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-3)' }}>
            Per-device DID registration and Oracle audit-log readback -- proof a device's decisions are actually reaching the chain-anchored audit trail, not just this backend's own DB.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.exporter_status.map((e) => (
              <div key={e.device_id} style={{ display: 'flex', gap: 'var(--space-4)', padding: 'var(--space-2) 0', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem' }}>
                <span style={{ fontFamily: 'var(--font-mono, monospace)', flex: 1 }}>{e.device_id}</span>
                <span style={{ color: e.status.did_registered ? '#10b981' : 'var(--text-muted)' }}>
                  {e.status.did_registered ? 'DID registered' : 'DID not registered'}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {summary && summary.integrations.length > 0 && (
        <Panel title="SIEM / SOAR integrations" icon={<Link2 size={16} />}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.integrations.map((i) => (
              <div key={i.integration_id} style={{ display: 'flex', gap: 'var(--space-4)', padding: 'var(--space-2) 0', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem' }}>
                <span style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.7rem', color: 'var(--primary)' }}>{i.kind}</span>
                <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-muted)', flex: 1 }}>{i.integration_id}</span>
                {i.created_at && <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{timeAgo(i.created_at)}</span>}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)',
      padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: tone ?? 'var(--primary)' }}>
        {icon}
        <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>{label}</span>
      </div>
      <span style={{ fontSize: '1.6rem', fontWeight: 700, color: tone ?? 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}
