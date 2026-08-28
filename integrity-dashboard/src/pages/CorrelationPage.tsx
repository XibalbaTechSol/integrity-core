import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, CircleDashed, GitMerge, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { graphMemory, type InvocationCorrelation } from '../services/graphMemory';
import { oracle, type IntentOutcomeDto } from '../services/oracle';
import { shieldBackend, type ShieldDecision } from '../services/shieldBackend';

type CombinedInvocation = {
  invocationId: string;
  cortex?: InvocationCorrelation;
  oracle?: IntentOutcomeDto;
  shield?: ShieldDecision;
};

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  reconciled: { label: 'Reconciled', color: '#10b981', bg: 'rgba(16,185,129,.12)' },
  complete: { label: 'Runtime complete', color: '#60a5fa', bg: 'rgba(96,165,250,.12)' },
  awaiting_outcome: { label: 'Awaiting outcome', color: '#f59e0b', bg: 'rgba(245,158,11,.12)' },
  intent_without_outcome: { label: 'Missing outcome', color: '#f59e0b', bg: 'rgba(245,158,11,.12)' },
  outcome_without_intent: { label: 'Orphan outcome', color: '#f43f5e', bg: 'rgba(244,63,94,.12)' },
  orphan_outcome: { label: 'Orphan runtime outcome', color: '#f43f5e', bg: 'rgba(244,63,94,.12)' },
  duplicate_invocation: { label: 'Duplicate ID', color: '#f43f5e', bg: 'rgba(244,63,94,.12)' },
  correlation_conflict: { label: 'Correlation conflict', color: '#f43f5e', bg: 'rgba(244,63,94,.12)' },
  legacy_hash_only: { label: 'Legacy hash only', color: '#94a3b8', bg: 'rgba(148,163,184,.12)' },
};

function Stage({ present, label, warning = false }: { present: boolean; label: string; warning?: boolean }) {
  const color = warning ? '#f59e0b' : present ? '#10b981' : 'var(--text-muted)';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color, fontSize: '0.76rem', whiteSpace: 'nowrap' }}>
      {warning ? <AlertTriangle size={14} /> : present ? <CheckCircle2 size={14} /> : <CircleDashed size={14} />}
      {label}
    </span>
  );
}

function shortId(value: string) {
  return `${value.slice(0, 8)}…${value.slice(-6)}`;
}

export default function CorrelationPage() {
  const { selectedAgent } = useDashboard();
  const [rows, setRows] = useState<CombinedInvocation[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    const agentId = selectedAgent?.id;
    const tenantId = selectedAgent?.eth_address;
    const [cortexResult, oracleResult, shieldResult] = await Promise.allSettled([
      graphMemory.invocations(200),
      agentId ? oracle.getReconciliation(agentId) : Promise.resolve([]),
      tenantId ? shieldBackend.dashboardSummary(tenantId) : Promise.resolve(null),
    ]);

    const byId = new Map<string, CombinedInvocation>();
    const nextErrors: string[] = [];
    if (cortexResult.status === 'fulfilled') {
      cortexResult.value.forEach(cortex => byId.set(cortex.invocation_id, { invocationId: cortex.invocation_id, cortex }));
    } else nextErrors.push('Cortex correlation API unavailable');
    if (oracleResult.status === 'fulfilled') {
      oracleResult.value.forEach(oracleRow => {
        if (!oracleRow.invocation_id) return;
        const row = byId.get(oracleRow.invocation_id) ?? { invocationId: oracleRow.invocation_id };
        row.oracle = oracleRow;
        byId.set(row.invocationId, row);
      });
    } else nextErrors.push('Oracle reconciliation API unavailable');
    if (shieldResult.status === 'fulfilled' && shieldResult.value) {
      shieldResult.value.latest_decisions.forEach(shield => {
        const id = shield.decision.invocation_id ?? shield.decision.export?.invocation_id;
        if (!id) return;
        const row = byId.get(id) ?? { invocationId: id };
        row.shield = shield;
        byId.set(id, row);
      });
    } else if (shieldResult.status === 'rejected') nextErrors.push('Shield decision API unavailable');

    setRows(Array.from(byId.values()).sort((a, b) => {
      const at = a.cortex?.last_seen_at ?? a.oracle?.outcome_at ?? a.oracle?.intent_at ?? a.shield?.received_at ?? '';
      const bt = b.cortex?.last_seen_at ?? b.oracle?.outcome_at ?? b.oracle?.intent_at ?? b.shield?.received_at ?? '';
      return bt.localeCompare(at);
    }));
    setErrors(nextErrors);
    setLoading(false);
  }, [selectedAgent?.id, selectedAgent?.eth_address]);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => rows.filter(row => {
    const status = row.oracle?.status ?? row.cortex?.runtime_status ?? 'unknown';
    if (filter === 'all') return true;
    if (filter === 'attention') return !['reconciled', 'complete'].includes(status);
    return status === filter;
  }), [rows, filter]);

  const reconciled = rows.filter(row => row.oracle?.status === 'reconciled').length;
  const attention = rows.filter(row => !['reconciled', 'complete'].includes(row.oracle?.status ?? row.cortex?.runtime_status ?? 'unknown')).length;

  return (
    <div className="correlation-page" style={{ padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-4)', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: '0 0 8px', fontSize: '2rem', display: 'flex', alignItems: 'center', gap: 12 }}><GitMerge size={28} /> Invocation Correlation</h1>
          <p style={{ margin: 0, color: 'var(--text-secondary)', maxWidth: 760, lineHeight: 1.55 }}>
            Follow one attempted action across Cortex runtime hooks, Shield enforcement, the signed BCC intent, and Oracle outcome evidence.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <RefreshCw size={16} className={loading ? 'spin' : undefined} /> Refresh evidence
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', borderTop: '1px solid var(--glass-border)', borderBottom: '1px solid var(--glass-border)' }}>
        {[
          ['Observed invocations', rows.length, 'Cross-source IDs currently visible'],
          ['Fully reconciled', reconciled, 'Signed intent and authoritative outcome'],
          ['Needs attention', attention, 'Missing, conflicting, duplicate, or legacy evidence'],
          ['Sources online', `${3 - errors.length}/3`, errors.length ? errors.join(' · ') : 'Cortex, Shield, and Oracle responded'],
        ].map(([label, value, detail], index) => (
          <div key={String(label)} style={{ padding: 'var(--space-5)', borderRight: index < 3 ? '1px solid var(--glass-border)' : undefined }}>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '.06em' }}>{label}</div>
            <div style={{ fontSize: '1.7rem', fontWeight: 650, margin: '6px 0' }}>{value}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.74rem', lineHeight: 1.4 }}>{detail}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[['all', 'All'], ['attention', 'Needs attention'], ['reconciled', 'Reconciled'], ['awaiting_outcome', 'Awaiting outcome']].map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)} style={{ padding: '8px 12px', border: `1px solid ${filter === id ? 'var(--theme-accent)' : 'var(--glass-border)'}`, background: filter === id ? 'var(--theme-accent-muted)' : 'transparent', color: filter === id ? 'var(--theme-accent)' : 'var(--text-secondary)', borderRadius: 4, cursor: 'pointer', fontSize: '0.78rem' }}>{label}</button>
        ))}
      </div>

      <div style={{ border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', overflow: 'hidden', background: 'var(--bg-secondary)' }}>
        <div className="correlation-table-header" style={{ display: 'grid', gridTemplateColumns: '34px minmax(190px,1.25fr) minmax(120px,.8fr) minmax(320px,2fr) minmax(140px,.8fr)', gap: 12, padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '.06em', borderBottom: '1px solid var(--glass-border)' }}>
          <span /><span>Invocation</span><span>Status</span><span>Evidence path</span><span>Last observed</span>
        </div>
        {filtered.length === 0 && <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-muted)' }}>{loading ? 'Loading correlation evidence…' : 'No invocation evidence matches this view.'}</div>}
        {filtered.map(row => {
          const statusKey = row.oracle?.status ?? row.cortex?.runtime_status ?? 'unknown';
          const tone = STATUS[statusKey] ?? { label: 'Partial evidence', color: '#94a3b8', bg: 'rgba(148,163,184,.12)' };
          const open = expanded === row.invocationId;
          return (
            <div key={row.invocationId} style={{ borderBottom: '1px solid var(--glass-border)' }}>
              <button className="correlation-row" onClick={() => setExpanded(open ? null : row.invocationId)} style={{ width: '100%', display: 'grid', gridTemplateColumns: '34px minmax(190px,1.25fr) minmax(120px,.8fr) minmax(320px,2fr) minmax(140px,.8fr)', gap: 12, padding: '15px 16px', alignItems: 'center', border: 0, background: open ? 'var(--glass-surface-light)' : 'transparent', color: 'var(--text-primary)', cursor: 'pointer', textAlign: 'left' }}>
                {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <span><code title={row.invocationId} style={{ color: 'var(--text-primary)' }}>{shortId(row.invocationId)}</code><small style={{ display: 'block', color: 'var(--text-muted)', marginTop: 4 }}>{row.cortex?.tool_name ?? row.oracle?.intent_type ?? 'Unclassified action'}</small></span>
                <span style={{ color: tone.color, background: tone.bg, padding: '5px 8px', borderRadius: 4, width: 'fit-content', fontSize: '0.72rem', fontWeight: 600 }}>{tone.label}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
                  <Stage present={Boolean(row.cortex?.pre_tool)} label="Cortex" />
                  <Stage present={Boolean(row.shield)} label="Shield" />
                  <Stage present={Boolean(row.oracle?.intent_at)} label="BCC" />
                  <Stage present={Boolean(row.oracle?.outcome_at ?? row.cortex?.post_tool)} label="Outcome" warning={statusKey.includes('conflict') || statusKey.includes('duplicate')} />
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{row.cortex?.last_seen_at ?? row.oracle?.outcome_at ?? row.oracle?.intent_at ?? row.shield?.received_at ?? 'unknown'}</span>
              </button>
              {open && (
                <div className="correlation-detail" style={{ padding: '0 16px 18px 62px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', background: 'var(--glass-surface-light)' }}>
                  <section><h3 style={{ fontSize: '.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Runtime</h3><code style={{ fontSize: '.72rem', wordBreak: 'break-all' }}>{row.invocationId}</code><p style={{ color: 'var(--text-secondary)', fontSize: '.8rem' }}>{row.cortex?.pre_tool?.intent_rationale ?? 'No Cortex pre-tool evidence.'}</p></section>
                  <section><h3 style={{ fontSize: '.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Shield / policy</h3><p style={{ color: 'var(--text-secondary)', fontSize: '.8rem' }}>{row.shield ? `${row.shield.decision.decision?.action ?? 'unknown'} · ${row.shield.decision.rule?.name ?? 'policy decision'}` : 'No Shield decision correlated.'}</p></section>
                  <section><h3 style={{ fontSize: '.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Signed intent</h3><code style={{ fontSize: '.72rem', wordBreak: 'break-all' }}>{row.oracle?.intended_state_hash ?? row.cortex?.pre_tool?.tool_input_hash ?? 'No signed BCC intent observed.'}</code></section>
                  <section><h3 style={{ fontSize: '.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Outcome</h3><p style={{ color: 'var(--text-secondary)', fontSize: '.8rem' }}>{row.oracle?.outcome ?? row.cortex?.post_tool?.outcome ?? 'No outcome reported.'}</p></section>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {errors.length > 0 && <div style={{ color: '#f59e0b', fontSize: '.78rem', display: 'flex', alignItems: 'center', gap: 8 }}><AlertTriangle size={15} /> Partial view: {errors.join(' · ')}</div>}
      {rows.some(row => row.oracle?.status === 'correlation_conflict' || row.oracle?.status === 'duplicate_invocation') && <div style={{ color: '#f43f5e', fontSize: '.78rem', display: 'flex', alignItems: 'center', gap: 8 }}><XCircle size={15} /> Conflicting correlation evidence requires operator review; it is never counted as reconciled.</div>}
      {reconciled > 0 && <div style={{ color: '#10b981', fontSize: '.78rem', display: 'flex', alignItems: 'center', gap: 8 }}><ShieldCheck size={15} /> Reconciled rows have one signed intent and one authoritative outcome sharing the same invocation identifier.</div>}
    </div>
  );
}
