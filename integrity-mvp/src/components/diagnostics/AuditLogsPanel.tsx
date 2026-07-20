import { useEffect, useMemo, useState } from 'react';
import { ShieldAlert, CheckCircle, XCircle, CodeSquare, AlertCircle, Clock, MinusCircle, Eye } from 'lucide-react';
import { useAgent } from '../../contexts/AgentContext';
import { oracle, type AuditLogEntryDto } from '../../services/oracle';
import { NotionDatabase } from '../NotionDatabase';
import { SeededDataBadge } from '../../shared/SeededDataBadge';
import type { ColumnDef } from '@tanstack/react-table';

// The genuine "everything logged" table (backend::handlers::get_audit_log):
// merges THREE real event streams for the selected agent -- bcc_middleware's
// real ALLOW/DENY intercept decisions (POST /v1/audit/ingest, see
// bcc_middleware/app/audit.py), the agent's SDK telemetry submissions
// (flagged/recorded), and every real OTel span the agent has produced
// (source="otel_span", "decision" repurposed as that span's own real
// status_code since spans don't have an authorization verdict). Reacts to
// the global TopBar agent selector (AgentContext.selectedAgent) -- there is
// no "all agents" telemetry/span query yet (see get_audit_log's own doc
// comment), so an agent must be selected to see anything beyond the raw
// (agent-less) audit_log feed.
const DECISION_BADGE: Record<string, string> = {
  allow: 'badge-success',
  deny: 'badge-danger',
  // Monitor-only rollout: bcc_middleware in shadow mode reports what enforcement
  // WOULD have blocked (app/audit.py decision="shadow_deny"). It's not a real
  // block, so it reads as a warning, not a danger.
  shadow_deny: 'badge-warning',
  flagged: 'badge-warning',
  recorded: 'badge-info',
  STATUS_CODE_OK: 'badge-success',
  STATUS_CODE_ERROR: 'badge-danger',
  STATUS_CODE_UNSET: 'badge-info',
};

const DECISION_ICON: Record<string, React.ReactElement> = {
  allow: <CheckCircle size={14} />,
  deny: <XCircle size={14} />,
  shadow_deny: <Eye size={14} />,
  flagged: <AlertCircle size={14} />,
  recorded: <AlertCircle size={14} />,
  STATUS_CODE_OK: <CheckCircle size={14} />,
  STATUS_CODE_ERROR: <XCircle size={14} />,
  STATUS_CODE_UNSET: <MinusCircle size={14} />,
};

// Human-facing label overrides where the raw decision string reads badly
// uppercased (e.g. "shadow_deny" -> "WOULD-BE BLOCK").
const DECISION_LABEL: Record<string, string> = {
  shadow_deny: 'Would-be block',
};

const SOURCE_LABELS: Record<string, string> = {
  bcc_middleware: 'BCC Decision',
  sdk_telemetry: 'SDK Telemetry',
  otel_span: 'OTel Span',
};

const COLUMNS: ColumnDef<AuditLogEntryDto>[] = [
  {
    accessorKey: 'created_at',
    header: 'Timestamp',
    cell: info => (
      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
        <Clock size={12} /> {new Date(info.getValue() as string).toLocaleString()}
      </span>
    ),
    size: 170,
  },
  {
    accessorKey: 'event_type',
    header: 'Event',
    cell: info => (
      <div>
        <div style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '4px', color: 'var(--text-primary)' }}>{info.getValue() as string}</div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{info.row.original.detail ?? '—'}</div>
      </div>
    ),
    size: 340,
  },
  {
    accessorKey: 'source',
    header: 'Source',
    cell: info => {
      const source = info.getValue() as string;
      return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          <CodeSquare size={14} color="var(--accent-primary)" />
          {SOURCE_LABELS[source] ?? source}
        </span>
      );
    },
    size: 150,
  },
  {
    accessorKey: 'reason_code',
    header: 'Reason / Parent',
    cell: info => <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>{(info.getValue() as string | null) ?? '—'}</span>,
    size: 180,
  },
  {
    accessorKey: 'agent_id',
    header: 'Agent',
    cell: info => <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>{((info.getValue() as string | null) ?? '—').slice(-12)}</span>,
    size: 120,
  },
  {
    accessorKey: 'decision',
    header: 'Decision / Status',
    cell: info => {
      const decision = info.getValue() as string;
      return (
        <span className={`badge ${DECISION_BADGE[decision] ?? 'badge-warning'}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 12px', textTransform: 'uppercase' }}>
          {DECISION_ICON[decision] ?? <AlertCircle size={14} />}
          {DECISION_LABEL[decision] ?? decision.replace('STATUS_CODE_', '')}
        </span>
      );
    },
    size: 140,
  },
];

const SOURCE_FILTERS = ['all', 'bcc_middleware', 'sdk_telemetry', 'otel_span'] as const;
type SourceFilter = (typeof SOURCE_FILTERS)[number];

export const AuditLogsPanel = () => {
  const { selectedAgent } = useAgent();
  const [logs, setLogs] = useState<AuditLogEntryDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');

  useEffect(() => {
    setLoading(true);
    setError(null);
    oracle
      .getAuditLog(selectedAgent?.id, 300)
      .then(setLogs)
      .catch(err => setError(err.message || 'Failed to fetch audit log'))
      .finally(() => setLoading(false));
  }, [selectedAgent]);

  const counts = useMemo(() => {
    const bySource: Record<string, number> = {};
    let denyCount = 0;
    let shadowCount = 0;
    for (const l of logs) {
      bySource[l.source] = (bySource[l.source] ?? 0) + 1;
      if (l.decision === 'deny' || l.decision === 'STATUS_CODE_ERROR') denyCount += 1;
      // Monitor-only "would-be blocks" are tracked separately from real,
      // enforced denials — they signal what shadow-mode enforcement caught
      // without actually blocking (see bcc_middleware shadow_mode).
      if (l.decision === 'shadow_deny') shadowCount += 1;
    }
    return { bySource, denyCount, shadowCount };
  }, [logs]);

  const filteredLogs = useMemo(
    () => (sourceFilter === 'all' ? logs : logs.filter(l => l.source === sourceFilter)),
    [logs, sourceFilter],
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', overflow: 'hidden' }}>
      <div className="card glass-panel" style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: '20px', padding: '24px', borderLeft: `4px solid ${counts.denyCount > 0 ? 'var(--danger)' : 'var(--success)'}` }}>
        <div style={{ padding: '16px', background: counts.denyCount > 0 ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)', borderRadius: '50%', color: counts.denyCount > 0 ? 'var(--danger)' : 'var(--success)' }}>
          <ShieldAlert size={32} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-primary)' }}>Unified Event Log</h3>
            {!selectedAgent && <SeededDataBadge label="Select an agent to include telemetry + OTel spans alongside global policy decisions" />}
          </div>
          <p style={{ margin: '8px 0 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.5 }}>
            Every real BCC policy decision, SDK telemetry submission, and OTel span for {selectedAgent ? `${selectedAgent.name || selectedAgent.id}` : 'the network'}
            {' '}in one time-ordered feed ({logs.length} entries: {counts.bySource.bcc_middleware ?? 0} BCC decisions, {counts.bySource.sdk_telemetry ?? 0} telemetry,{' '}
            {counts.bySource.otel_span ?? 0} spans, {counts.denyCount} denied/errored{counts.shadowCount > 0 ? `, ${counts.shadowCount} would-be blocks (shadow)` : ''}). No client-side simulation — every row is a live query against the oracle's real tables.
          </p>
        </div>
      </div>

      <div style={{ flex: '0 0 auto', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {SOURCE_FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setSourceFilter(f)}
            className={`btn btn-sm ${sourceFilter === f ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 14px', fontSize: '0.8rem' }}
          >
            {f === 'all' ? `All (${logs.length})` : `${SOURCE_LABELS[f]} (${counts.bySource[f] ?? 0})`}
          </button>
        ))}
      </div>

      {error && (
        <div className="card" style={{ padding: '16px', color: 'var(--danger)', flex: '0 0 auto' }}>
          Failed to load audit log: {error}
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0 }}>
        <NotionDatabase
          data={filteredLogs}
          columns={COLUMNS}
          title={loading ? 'Loading…' : 'Unified Event Stream'}
          readOnly={true}
        />
      </div>
    </div>
  );
};
