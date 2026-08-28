import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { RefreshCw, GitCompare, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { StatusBadge } from '../components/shared/StatusBadge';
import { graphMemory } from '../services/graphMemory';
import type { Session, KernelIntentTriple } from '../services/graphMemory';

// Kernel-first intent-vs-outcome bridge (~/.claude/plans/iridescent-stirring-kettle.md).
// Reads xibalba-cortex's GraphStore.kernel_bridge_intents() via local_api.py -- correlated
// (declared intent, kernel/adapter decision, actual tool-call outcome) triples for a session.
// The bridge itself is opt-in (XIBALBA_KERNEL_BRIDGE_ENABLED) and submits real signed
// UserOperations against a LOCAL-DEVNET-ONLY, EXPERIMENTAL kernel/account testbed -- an ordinary
// session will show zero rows here, which is expected, not broken.
const LAST_SESSION_KEY = 'kernelIntentPage.lastSessionId';

// Some browser/embedding contexts throw on any localStorage access rather than returning
// null -- see DashboardContext.tsx's identical helper for why this must never be unguarded.
function safeLocalStorageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeLocalStorageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Best-effort only.
  }
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 'var(--space-4)',
        padding: 'var(--space-2) 0',
        borderBottom: '1px solid var(--glass-border)',
        fontSize: '0.85rem',
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono, monospace)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

function TripleCard({ triple }: { triple: KernelIntentTriple }) {
  const kernelSuccess = triple.kernel_decision.success;
  const kernelError = triple.kernel_decision.error;

  return (
    <Panel
      title={triple.tool_name ?? triple.tool_call_id}
      icon={triple.diverges ? <ShieldAlert size={16} /> : <GitCompare size={16} />}
      action={
        triple.diverges ? (
          <StatusBadge status="rejected" />
        ) : (
          <StatusBadge status="verified" />
        )
      }
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        <div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--space-2)' }}>
            Declared intent
          </div>
          <Row label="Rationale" value={triple.declared_intent.intent_rationale ?? 'none'} />
          <Row label="Input hash" value={triple.declared_intent.tool_input_hash ?? 'none'} />
        </div>

        <div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--space-2)' }}>
            Kernel / adapter decision
          </div>
          {kernelError ? (
            <Row label="Bridge error" value={<span style={{ color: 'var(--danger, #e5484d)' }}>{kernelError}</span>} />
          ) : (
            <>
              <Row
                label="Result"
                value={
                  kernelSuccess ? (
                    <span style={{ color: 'var(--success, #30a46c)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={14} /> ALLOW
                    </span>
                  ) : (
                    <span style={{ color: 'var(--danger, #e5484d)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <XCircle size={14} /> DENY
                    </span>
                  )
                }
              />
              <Row label="UserOp hash" value={triple.kernel_decision.user_op_hash ?? 'n/a'} />
              {triple.kernel_decision.revert_reason_hex && (
                <Row label="Revert reason" value={triple.kernel_decision.revert_reason_hex} />
              )}
            </>
          )}
          {triple.kernel_decision.adapter_note && (
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 'var(--space-2)', lineHeight: 1.5 }}>
              {triple.kernel_decision.adapter_note}
            </div>
          )}
        </div>

        <div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--space-2)' }}>
            Actual outcome
          </div>
          {triple.actual_outcome ? (
            <>
              <Row label="Tool outcome" value={triple.actual_outcome.outcome ?? 'unknown'} />
              <Row label="Duration" value={triple.actual_outcome.duration_ms != null ? `${triple.actual_outcome.duration_ms}ms` : 'n/a'} />
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No post_tool_call recorded yet for this tool call.</div>
          )}
        </div>
      </div>

      {triple.diverges && (
        <div
          style={{
            marginTop: 'var(--space-3)',
            background: 'color-mix(in srgb, var(--danger, #e5484d) 12%, var(--bg-secondary))',
            border: '1px solid var(--danger, #e5484d)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3)',
            fontSize: '0.8rem',
          }}
        >
          Divergence: the kernel/adapter decision and the tool's actual outcome disagree.
        </div>
      )}
    </Panel>
  );
}

export default function KernelIntentPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState(() => safeLocalStorageGet(LAST_SESSION_KEY) ?? '');
  const [triples, setTriples] = useState<KernelIntentTriple[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    graphMemory
      .sessions(100)
      .then((list) => {
        setSessions(list);
        if (!selectedSessionId && list[0]) {
          setSelectedSessionId(list[0].external_session_id);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load sessions.'));
    // Only on mount -- selectedSessionId changes are handled by the load() effect below.
  }, []);

  const load = useCallback(async (sessionId: string) => {
    if (!sessionId) {
      setTriples([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await graphMemory.sessionKernelIntents(sessionId);
      setTriples(result);
      safeLocalStorageSet(LAST_SESSION_KEY, sessionId);
    } catch (e) {
      setTriples([]);
      setError(e instanceof Error ? e.message : 'Could not load kernel-intent data for this session.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(selectedSessionId);
  }, [selectedSessionId, load]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
    >
      <Panel title="Kernel intent vs. outcome" icon={<GitCompare size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: '0 0 var(--space-4)' }}>
          For each tool call in the selected session where the kernel-bridge was opted in
          (<code>XIBALBA_KERNEL_BRIDGE_ENABLED=1</code> on xibalba-cortex), this compares what the
          agent <strong>declared</strong> it intended to do against what <code>IntegrityKernel</code>'s
          real on-chain <code>preCheck</code>/adapter decided, and what the tool call{' '}
          <strong>actually did</strong>. Runs against a local-devnet-only, EXPERIMENTAL testbed --
          see <code>contracts/script/DeployKernelBridgeTestbed.s.sol</code>. A session with the
          bridge disabled (the default) will show no rows here, which is expected, not an error.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <select
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            style={{
              flex: 1,
              minWidth: 0,
              background: 'var(--bg-secondary)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.85rem',
            }}
          >
            <option value="">Select a session…</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.external_session_id}>
                {s.external_session_id}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => load(selectedSessionId)}
            disabled={loading || !selectedSessionId}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              background: 'var(--primary)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              padding: '0 var(--space-4)',
              height: '42px',
              color: 'var(--bg-primary, #000)',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: loading ? 'default' : 'pointer',
              opacity: loading ? 0.6 : 1,
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

      {!error && !loading && triples.length === 0 && (
        <Panel>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: 'var(--space-6) 0' }}>
            No kernel-bridge intents recorded for this session.
          </div>
        </Panel>
      )}

      {triples.map((triple) => (
        <TripleCard key={triple.tool_call_id} triple={triple} />
      ))}
    </motion.div>
  );
}
