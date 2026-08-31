import { useState } from 'react';
import { CheckCircle2, XCircle, Loader2, Circle, ShieldCheck, Database, Cpu, Radio, Play, IdCard, Gauge, History, RefreshCw } from 'lucide-react';
import { Panel } from '../shared/Panel';
import { useServiceHealth } from '../../services/health';
import { graphMemory } from '../../services/graphMemory';
import { shieldBackend } from '../../services/shieldBackend';
import { oracle } from '../../services/oracle';
import { reportTestResult, XIBALBA_SYSTEM_TESTS_SESSION_ID } from '../../services/testResults';
import { GRAPH_MEMORY_URL } from '../../config';
import { XIBALBA_TEST_AGENT_ID } from '../../constants';

interface ActivityRow {
  source: 'oracle' | 'cortex' | 'shield';
  testName: string;
  status: string;
  detail: string | null;
  timestamp: string;
}

// Guided System Test (~/.claude/plans/velvet-giggling-quill.md): one place to verify
// integrity-core's backbone (Oracle), Cortex/Memory, and Shield actually work, end to end,
// with real requests against real backends -- no mocked results. Lives as a Developer-page
// tab rather than new sidebar navigation (an earlier decision). The BCC/Oracle pipeline is
// shown but disabled -- it has no server-side signer reachable from the browser today, and
// this page would rather disclose that than fake a passing check.
//
// Every test result also fans out to all three systems' own durable event logs
// (reportTestResult, testResults.ts), tagged with the same real, on-chain registered
// identity (XIBALBA_TEST_AGENT_ID) -- so a test run here is queryable from Oracle's
// audit_log, Cortex's otel_events, and Shield's test_events alike, not just visible in
// this page's own React state until the next reload.

type StepStatus = 'idle' | 'running' | 'passed' | 'failed';

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === 'passed') return <CheckCircle2 size={18} color="var(--success, #30a46c)" />;
  if (status === 'failed') return <XCircle size={18} color="var(--danger, #e5484d)" />;
  if (status === 'running') return <Loader2 size={18} className="spin" color="var(--primary)" />;
  return <Circle size={18} color="var(--text-muted)" opacity={0.5} />;
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
        fontSize: '0.8rem',
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono, monospace)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

function ActionStep({
  icon,
  title,
  description,
  status,
  disabledReason,
  onRun,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  status: StepStatus;
  disabledReason?: string;
  onRun: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Panel title={title} icon={icon} action={<StatusIcon status={status} />}>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-3)', overflowWrap: 'anywhere' }}>{description}</p>
      {disabledReason ? (
        <div style={{ color: 'var(--danger, #e5484d)', fontSize: '0.8rem', marginBottom: 'var(--space-2)' }}>{disabledReason}</div>
      ) : (
        <button
          type="button"
          onClick={onRun}
          disabled={status === 'running' || !!disabledReason}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            background: 'var(--primary)',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            padding: '0.5rem 1rem',
            color: 'var(--bg-primary, #000)',
            fontWeight: 600,
            fontSize: '0.8rem',
            cursor: status === 'running' ? 'default' : 'pointer',
            opacity: status === 'running' ? 0.6 : 1,
            marginBottom: 'var(--space-3)',
          }}
        >
          <Play size={14} />
          {status === 'idle' ? 'Run test' : 'Run again'}
        </button>
      )}
      {children}
    </Panel>
  );
}

export function GuidedSystemTest() {
  const services = useServiceHealth();
  const svc = (key: string) => services.find((s) => s.key === key);

  const [shieldStatus, setShieldStatus] = useState<StepStatus>('idle');
  const [shieldResult, setShieldResult] = useState<{ ok: boolean; seededDecisions?: number; error?: string } | null>(null);

  const [kernelStatus, setKernelStatus] = useState<StepStatus>('idle');
  const [kernelResult, setKernelResult] = useState<{
    passed: boolean;
    matchedSuccess?: boolean;
    kernelExceedingSuccess?: boolean;
    error?: string;
  } | null>(null);

  const [memoryStatus, setMemoryStatus] = useState<StepStatus>('idle');
  const [memoryResult, setMemoryResult] = useState<{ ok: boolean; exchangeId?: string; readBack?: boolean; error?: string } | null>(null);

  const runShieldTest = async () => {
    setShieldStatus('running');
    try {
      const result = await shieldBackend.seedDemo(XIBALBA_TEST_AGENT_ID);
      setShieldResult({ ok: true, seededDecisions: result.seeded_decisions });
      setShieldStatus('passed');
      void reportTestResult({ testName: 'shield', status: 'passed', detail: `${result.seeded_decisions} decisions seeded` });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setShieldResult({ ok: false, error: message });
      setShieldStatus('failed');
      void reportTestResult({ testName: 'shield', status: 'failed', detail: message });
    }
  };

  const runKernelTest = async () => {
    setKernelStatus('running');
    try {
      const response = await fetch(`${GRAPH_MEMORY_URL}/api/kernel-bridge/self-test`, {
        method: 'POST',
        body: JSON.stringify({ session_id: XIBALBA_SYSTEM_TESTS_SESSION_ID }),
      });
      const body = await response.json();
      if (!body.ok) throw new Error(body.error ?? 'self-test failed');
      setKernelResult({
        passed: !!body.passed,
        matchedSuccess: body.matched?.success,
        kernelExceedingSuccess: body.kernel_exceeding?.success,
      });
      setKernelStatus(body.passed ? 'passed' : 'failed');
      void reportTestResult({
        testName: 'kernel_bridge',
        status: body.passed ? 'passed' : 'failed',
        detail: `matched=${body.matched?.success} kernel_exceeding=${body.kernel_exceeding?.success}`,
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setKernelResult({ passed: false, error: message });
      setKernelStatus('failed');
      void reportTestResult({ testName: 'kernel_bridge', status: 'failed', detail: message });
    }
  };

  const runMemoryTest = async () => {
    setMemoryStatus('running');
    const sessionId = `system-test-${Date.now()}`;
    try {
      const written = await graphMemory.recordModelExchange({
        external_session_id: sessionId,
        user_prompt: 'Guided System Test: does write-then-read work?',
        model_response: 'Guided System Test round-trip check.',
        metadata: { source: 'guided-system-test' },
      });
      const readBack = await graphMemory.sessionExchanges(sessionId);
      const found = readBack.some((ex) => ex.id === written.exchange.id);
      setMemoryResult({ ok: found, exchangeId: written.exchange.id, readBack: found });
      setMemoryStatus(found ? 'passed' : 'failed');
      void reportTestResult({ testName: 'memory', status: found ? 'passed' : 'failed', detail: `exchange ${written.exchange.id}` });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setMemoryResult({ ok: false, error: message });
      setMemoryStatus('failed');
      void reportTestResult({ testName: 'memory', status: 'failed', detail: message });
    }
  };

  const [agentLookupStatus, setAgentLookupStatus] = useState<StepStatus>('idle');
  const [agentLookupResult, setAgentLookupResult] = useState<{ tier?: number; error?: string } | null>(null);

  const runAgentLookupTest = async () => {
    setAgentLookupStatus('running');
    try {
      const agent = await oracle.getAgent(XIBALBA_TEST_AGENT_ID);
      setAgentLookupResult({ tier: agent.verification_tier });
      setAgentLookupStatus('passed');
      void reportTestResult({ testName: 'oracle_agent_lookup', status: 'passed', detail: `tier=${agent.verification_tier}` });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setAgentLookupResult({ error: message });
      setAgentLookupStatus('failed');
      void reportTestResult({ testName: 'oracle_agent_lookup', status: 'failed', detail: message });
    }
  };

  const [aisStatus, setAisStatus] = useState<StepStatus>('idle');
  const [aisResult, setAisResult] = useState<{ ais?: number; error?: string } | null>(null);

  const runAisTest = async () => {
    setAisStatus('running');
    try {
      const ais = await oracle.getAis(XIBALBA_TEST_AGENT_ID);
      setAisResult({ ais: ais.ais });
      setAisStatus('passed');
      void reportTestResult({ testName: 'oracle_ais_score', status: 'passed', detail: `ais=${ais.ais}` });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setAisResult({ error: message });
      setAisStatus('failed');
      void reportTestResult({ testName: 'oracle_ais_score', status: 'failed', detail: message });
    }
  };

  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);

  const loadActivity = async () => {
    setActivityLoading(true);
    const [oracleRows, cortexRows, shieldRows] = await Promise.allSettled([
      oracle.getAuditLog(XIBALBA_TEST_AGENT_ID, 20),
      graphMemory.sessionOtel(XIBALBA_SYSTEM_TESTS_SESSION_ID),
      shieldBackend.listTestEvents(),
    ]);

    const rows: ActivityRow[] = [];
    if (oracleRows.status === 'fulfilled') {
      for (const r of oracleRows.value) {
        if (r.event_type !== 'guided_system_test') continue;
        rows.push({ source: 'oracle', testName: r.detail ?? r.event_type, status: r.decision, detail: r.detail, timestamp: r.created_at });
      }
    }
    if (cortexRows.status === 'fulfilled') {
      for (const r of cortexRows.value) {
        if (r.name !== 'guided_system_test') continue;
        const attrs = r.attributes as { test_name?: string; status?: string; detail?: string };
        rows.push({ source: 'cortex', testName: attrs.test_name ?? r.name, status: attrs.status ?? 'unknown', detail: attrs.detail ?? null, timestamp: r.created_at });
      }
    }
    if (shieldRows.status === 'fulfilled') {
      for (const r of shieldRows.value.test_events) {
        rows.push({ source: 'shield', testName: r.test_name, status: r.status, detail: r.detail, timestamp: r.recorded_at });
      }
    }

    rows.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    setActivity(rows);
    setActivityLoading(false);
  };

  const testableStatuses = [shieldStatus, kernelStatus, memoryStatus, agentLookupStatus, aisStatus];
  const passedCount = testableStatuses.filter((s) => s === 'passed').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <Panel title="Guided System Test" icon={<ShieldCheck size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: '0 0 var(--space-2)' }}>
          Verifies Shield, Cortex/Memory, the Kernel/Adapter bridge, and the Oracle's own agent
          registry and AIS scoring pipeline, with real requests against real backends. Each step
          below is disabled until its service shows online in the checklist. Every result also
          fans out to Oracle's audit_log, Cortex's otel_events, and Shield's test_events, tagged
          with the same real identity (<code>xibalba.integrity</code>) -- see "Recent test
          activity" below. The BCC/Oracle intent-gating pipeline is not yet wireable from a
          browser (it needs a server-side signer) and is shown disabled rather than faked.
        </p>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--theme-accent)' }}>
          {passedCount} / {testableStatuses.length} testable checks passing
        </div>
      </Panel>

      <Panel title="Service health" icon={<Radio size={16} />}>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          {services.map((s) => (
            <div
              key={s.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--glass-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: '0.8rem',
              }}
            >
              <StatusIcon status={s.status === 'online' ? 'passed' : s.status === 'offline' ? 'failed' : 'running'} />
              {s.label}
            </div>
          ))}
        </div>
        {services
          .filter((s) => s.status === 'offline' && s.detail)
          .map((s) => (
            <div key={s.key} style={{ color: 'var(--danger, #e5484d)', fontSize: '0.75rem', marginTop: 'var(--space-2)' }}>
              {s.detail}
            </div>
          ))}
      </Panel>

      <ActionStep
        icon={<ShieldCheck size={16} />}
        title="Shield"
        description="Seeds 4 canned policy decisions through the real Shield backend + DB, proving the backend and its persistence actually work."
        status={shieldStatus}
        disabledReason={svc('shield')?.status !== 'online' ? 'Shield backend is offline -- see the service health panel above.' : undefined}
        onRun={() => void runShieldTest()}
      >
        {shieldResult && (
          <>
            {shieldResult.ok ? (
              <Row label="Seeded decisions" value={shieldResult.seededDecisions} />
            ) : (
              <Row label="Error" value={shieldResult.error} />
            )}
          </>
        )}
      </ActionStep>

      <ActionStep
        icon={<Cpu size={16} />}
        title="Kernel / adapter bridge"
        description="Submits two real signed UserOperations against the kernel-bridge testbed: one within budget (expect ALLOW) and one over the kernel's own per-op budget (expect DENY)."
        status={kernelStatus}
        disabledReason={svc('kernel')?.status !== 'online' ? 'Kernel RPC is offline -- see the service health panel above.' : undefined}
        onRun={() => void runKernelTest()}
      >
        {kernelResult && (
          <>
            {kernelResult.error ? (
              <Row label="Error" value={kernelResult.error} />
            ) : (
              <>
                <Row label="Matched case (0.1 ETH)" value={kernelResult.matchedSuccess ? 'ALLOW (expected)' : 'DENY (unexpected)'} />
                <Row
                  label="Kernel-exceeding case (1.5 ETH)"
                  value={kernelResult.kernelExceedingSuccess === false ? 'DENY (expected)' : 'ALLOW (unexpected)'}
                />
              </>
            )}
          </>
        )}
      </ActionStep>

      <ActionStep
        icon={<Database size={16} />}
        title="Memory / Cortex"
        description="Writes a synthetic exchange through the real GraphStore, then reads it back by session id -- proves the write→read round-trip works."
        status={memoryStatus}
        disabledReason={svc('memory')?.status !== 'online' ? 'Cortex local_api is offline -- see the service health panel above.' : undefined}
        onRun={() => void runMemoryTest()}
      >
        {memoryResult && (
          <>
            {memoryResult.error ? (
              <Row label="Error" value={memoryResult.error} />
            ) : (
              <>
                <Row label="Exchange id" value={memoryResult.exchangeId} />
                <Row label="Read back" value={memoryResult.readBack ? 'yes' : 'no'} />
              </>
            )}
          </>
        )}
      </ActionStep>

      <ActionStep
        icon={<IdCard size={16} />}
        title="Oracle agent lookup"
        description={`Resolves ${XIBALBA_TEST_AGENT_ID} via the real Oracle registry -- confirms the identity every test on this page is attributed to actually exists and is live.`}
        status={agentLookupStatus}
        disabledReason={svc('oracle')?.status !== 'online' ? 'Oracle is offline -- see the service health panel above.' : undefined}
        onRun={() => void runAgentLookupTest()}
      >
        {agentLookupResult && (
          <>
            {agentLookupResult.error ? (
              <Row label="Error" value={agentLookupResult.error} />
            ) : (
              <Row label="Verification tier" value={agentLookupResult.tier} />
            )}
          </>
        )}
      </ActionStep>

      <ActionStep
        icon={<Gauge size={16} />}
        title="Oracle AIS score"
        description="Reads the real, geometric-mean Agent Integrity Score for the same identity -- confirms the scoring pipeline (entropy/grounding/sacrifice/compliance) is actually live, not just the registry."
        status={aisStatus}
        disabledReason={svc('oracle')?.status !== 'online' ? 'Oracle is offline -- see the service health panel above.' : undefined}
        onRun={() => void runAisTest()}
      >
        {aisResult && (
          <>
            {aisResult.error ? <Row label="Error" value={aisResult.error} /> : <Row label="AIS" value={aisResult.ais} />}
          </>
        )}
      </ActionStep>

      <Panel title="BCC / Oracle pipeline" icon={<Radio size={16} />} action={<StatusIcon status="idle" />}>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
          Not yet available from the dashboard -- signing a real BCC commitment needs a private
          key, which must never live in browser JS. This is the working, non-experimental
          intent-gating pipeline (distinct from the Kernel bridge above); wiring it in needs a
          small server-side signer first.
        </p>
      </Panel>

      <Panel
        title="Recent test activity"
        icon={<History size={16} />}
        action={
          <button
            type="button"
            onClick={() => void loadActivity()}
            disabled={activityLoading}
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'transparent', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '0.3rem 0.7rem', color: 'var(--text-primary)', fontSize: '0.75rem', cursor: 'pointer' }}
          >
            <RefreshCw size={12} className={activityLoading ? 'spin' : ''} />
            Refresh
          </button>
        }
      >
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 var(--space-3)' }}>
          The same test runs, read back independently from all three systems' own logs --
          proof a result here is genuinely durable and cross-system, not just this page's React
          state.
        </p>
        {activity.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            No activity loaded yet -- click Refresh, or run a test above first.
          </div>
        ) : (
          activity.map((row, i) => (
            <Row
              key={`${row.source}-${i}`}
              label={`[${row.source}] ${row.testName}`}
              value={`${row.status} · ${new Date(row.timestamp).toLocaleTimeString()}`}
            />
          ))
        )}
      </Panel>
    </div>
  );
}
