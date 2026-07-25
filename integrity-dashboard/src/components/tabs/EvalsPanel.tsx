import { useState, useEffect, useMemo } from 'react';
import { BarChart3, AlertTriangle, CheckCircle, Clock, TrendingDown, Layers, Activity } from 'lucide-react';
import { motion } from 'framer-motion';
import { oracle } from '../../services/oracle';
import { useDashboard } from '../../context/useDashboard';

// ─── Types ───────────────────────────────────────────────────────────────────

interface EvalStep {
  id?: string;
  type?: string;
  event_type?: string;
  confidence?: number;
  grounding_delta?: number;
  duration_ms?: number;
  depth?: number;
  timestamp?: number;
  time?: string;
  name?: string;
  tool_name?: string;
  message?: string;
  recoverable?: boolean;
}

interface EvalSummary {
  totalSteps: number;
  thoughts: number;
  toolCalls: number;
  errors: number;
  avgConfidence: number;
  maxDrift: number;
  totalDuration: number;
  driftTimeline: { index: number; delta: number; type: string; time: string }[];
  toolSuccessRate: number;
  depthDistribution: { depth: number; count: number }[];
  driftEvents: { stepId: string; type: string; delta: number; time: string }[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function computeEvalSummary(steps: EvalStep[]): EvalSummary {
  let thoughts = 0;
  let toolCalls = 0;
  let errors = 0;
  let totalConf = 0;
  let confCount = 0;
  let maxDrift = 0;
  let totalDuration = 0;
  let toolSuccess = 0;
  let toolTotal = 0;
  const depthMap = new Map<number, number>();
  const driftTimeline: EvalSummary['driftTimeline'] = [];
  const driftEvents: EvalSummary['driftEvents'] = [];

  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    const t = s.type || s.event_type || '';

    if (t === 'thought') thoughts++;
    else if (t === 'tool' || t === 'tool_call') {
      toolCalls++;
      toolTotal++;
      // Assume success if not an error type
      toolSuccess++;
    } else if (t === 'error') {
      errors++;
      if (toolTotal > 0) toolSuccess--; // last tool likely failed
    }

    if (s.confidence != null) {
      totalConf += s.confidence;
      confCount++;
    }
    if (s.grounding_delta != null) {
      if (s.grounding_delta > maxDrift) maxDrift = s.grounding_delta;
      driftTimeline.push({
        index: i,
        delta: s.grounding_delta,
        type: t,
        time: s.time || (s.timestamp ? new Date(s.timestamp * 1000).toLocaleTimeString() : `step-${i}`),
      });
      if (s.grounding_delta > 0.5) {
        driftEvents.push({
          stepId: s.id || `step-${i}`,
          type: t,
          delta: s.grounding_delta,
          time: s.time || (s.timestamp ? new Date(s.timestamp * 1000).toLocaleTimeString() : ''),
        });
      }
    }
    if (s.duration_ms != null) totalDuration += s.duration_ms;

    const d = s.depth ?? 0;
    depthMap.set(d, (depthMap.get(d) || 0) + 1);
  }

  const depthDistribution = Array.from(depthMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([depth, count]) => ({ depth, count }));

  return {
    totalSteps: steps.length,
    thoughts,
    toolCalls,
    errors,
    avgConfidence: confCount > 0 ? totalConf / confCount : 0,
    maxDrift,
    totalDuration,
    driftTimeline,
    toolSuccessRate: toolTotal > 0 ? Math.max(0, toolSuccess) / toolTotal : 1,
    depthDistribution: depthDistribution.length > 0 ? depthDistribution : [{ depth: 0, count: steps.length }],
    driftEvents,
  };
}

// ─── Score Card ──────────────────────────────────────────────────────────────

function ScoreCard({ label, value, sub, color, icon }: { label: string; value: string; sub?: string; color: string; icon: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        flex: '1 1 140px',
        padding: '16px',
        background: 'rgba(10, 10, 15, 0.7)',
        backdropFilter: 'blur(12px)',
        borderRadius: '14px',
        border: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
          {label}
        </span>
        <div style={{ color, opacity: 0.7 }}>{icon}</div>
      </div>
      <div style={{ fontSize: '1.4rem', fontWeight: 700, fontFamily: 'monospace', color, lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)' }}>
          {sub}
        </span>
      )}
    </motion.div>
  );
}

// ─── DriftSparkline ──────────────────────────────────────────────────────────

function DriftSparkline({ data }: { data: EvalSummary['driftTimeline'] }) {
  if (data.length === 0) {
    return (
      <div style={{ height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem' }}>
        No grounding delta data
      </div>
    );
  }

  const maxDelta = Math.max(...data.map(d => d.delta), 1);
  const w = 100;
  const h = 60;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height: '60px', overflow: 'visible' }}>
      {/* Red zone above 0.5 */}
      <rect
        x="0"
        y="0"
        width={w}
        height={h * (1 - 0.5 / maxDelta)}
        fill="rgba(239, 68, 68, 0.06)"
      />
      {/* Threshold line */}
      <line
        x1="0"
        y1={h * (1 - 0.5 / maxDelta)}
        x2={w}
        y2={h * (1 - 0.5 / maxDelta)}
        stroke="rgba(239, 68, 68, 0.3)"
        strokeWidth="0.5"
        strokeDasharray="3,2"
      />
      {/* Data line */}
      <polyline
        fill="none"
        stroke="#f59e0b"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={data.map((d, i) => {
          const x = data.length === 1 ? w / 2 : (i / (data.length - 1)) * w;
          const y = h - (d.delta / maxDelta) * h;
          return `${x},${y}`;
        }).join(' ')}
      />
      {/* Dots for drift events */}
      {data.filter(d => d.delta > 0.5).map((d, i) => {
        const idx = data.indexOf(d);
        const x = data.length === 1 ? w / 2 : (idx / (data.length - 1)) * w;
        const y = h - (d.delta / maxDelta) * h;
        return <circle key={i} cx={x} cy={y} r="2" fill="#ef4444" />;
      })}
    </svg>
  );
}

// ─── RadialProgress ──────────────────────────────────────────────────────────

function RadialProgress({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - value);
  const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
      <svg width="90" height="90" viewBox="0 0 90 90">
        <circle cx="45" cy="45" r={radius} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6" />
        <circle
          cx="45"
          cy="45"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 45 45)"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text x="45" y="45" textAnchor="middle" dominantBaseline="central" fill={color} fontSize="16" fontWeight="700" fontFamily="monospace">
          {pct}%
        </text>
      </svg>
      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
        {label}
      </span>
    </div>
  );
}

// ─── DepthChart ──────────────────────────────────────────────────────────────

function DepthChart({ data }: { data: EvalSummary['depthDistribution'] }) {
  const maxCount = Math.max(...data.map(d => d.count), 1);

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '60px', padding: '0 4px' }}>
      {data.map(d => (
        <div key={d.depth} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, gap: '4px' }}>
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: `${Math.max((d.count / maxCount) * 48, 4)}px` }}
            transition={{ duration: 0.4, delay: d.depth * 0.08 }}
            style={{
              width: '100%',
              maxWidth: '24px',
              background: 'linear-gradient(to top, #8b5cf640, #8b5cf6)',
              borderRadius: '4px 4px 0 0',
            }}
          />
          <span style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>
            d{d.depth}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── EvalsPanel ──────────────────────────────────────────────────────────────

export function EvalsPanel() {
  const { selectedAgent } = useDashboard();
  const [steps, setSteps] = useState<EvalStep[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      if (!selectedAgent) { setSteps([]); setLoading(false); return; }
      try {
        // Real LLM-as-judge evaluations for the selected agent (oracle.getTraces returns
        // the judge_evaluations rows), mapped onto the panel's EvalStep shape.
        const evals = await oracle.getTraces(selectedAgent.eth_address);
        if (cancelled) return;
        const allSteps: EvalStep[] = evals.map((ev) => ({
          id: ev.id,
          type: ev.verdict === 'PASS' ? 'thought' : 'error',
          event_type: ev.verdict,
          confidence: ev.score ?? undefined,
          message: ev.rationale_summary ?? undefined,
          name: ev.judge_model,
          recoverable: ev.verdict === 'PASS',
          time: new Date(ev.created_at).toLocaleTimeString(),
          timestamp: Math.round(new Date(ev.created_at).getTime() / 1000),
        }));
        if (!cancelled) setSteps(allSteps);
      } catch {
        // silently ignore fetch errors
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedAgent]);

  const summary = useMemo(() => computeEvalSummary(steps), [steps]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px', color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}>
        Loading eval data…
      </div>
    );
  }

  if (steps.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px', color: 'rgba(255,255,255,0.35)', fontSize: '0.85rem' }}>
        No telemetry data available for evaluation
      </div>
    );
  }

  const durationLabel = summary.totalDuration >= 1000
    ? `${(summary.totalDuration / 1000).toFixed(1)}s`
    : `${summary.totalDuration}ms`;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
    >
      {/* Score Cards */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
        <ScoreCard label="Total Steps"    value={String(summary.totalSteps)}                    color="#8b5cf6" icon={<Layers size={14} />} />
        <ScoreCard label="Thoughts"       value={String(summary.thoughts)}                      color="#a78bfa" icon={<Activity size={14} />} />
        <ScoreCard label="Tool Calls"     value={String(summary.toolCalls)}                     color="#f59e0b" icon={<CheckCircle size={14} />} />
        <ScoreCard label="Errors"         value={String(summary.errors)}                        color={summary.errors > 0 ? '#ef4444' : '#10b981'} icon={<AlertTriangle size={14} />} />
        <ScoreCard label="Avg Confidence" value={`${(summary.avgConfidence * 100).toFixed(1)}%`} color={summary.avgConfidence > 0.8 ? '#10b981' : '#f59e0b'} icon={<TrendingDown size={14} />} sub="across all steps" />
        <ScoreCard label="Max Drift"      value={summary.maxDrift.toFixed(3)}                   color={summary.maxDrift > 0.5 ? '#ef4444' : '#10b981'} icon={<AlertTriangle size={14} />} sub={summary.maxDrift > 0.5 ? '⚠ above threshold' : 'within bounds'} />
        <ScoreCard label="Total Duration" value={durationLabel}                                 color="#3b82f6" icon={<Clock size={14} />} />
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '16px' }}>
        {/* Drift Timeline */}
        <div style={{
          padding: '16px',
          background: 'rgba(10, 10, 15, 0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '14px',
          border: '1px solid rgba(255,255,255,0.05)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <TrendingDown size={14} color="#f59e0b" />
            <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
              Drift Timeline
            </span>
          </div>
          <DriftSparkline data={summary.driftTimeline} />
        </div>

        {/* Tool Success Rate */}
        <div style={{
          padding: '16px',
          background: 'rgba(10, 10, 15, 0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '14px',
          border: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <RadialProgress value={summary.toolSuccessRate} label="Tool Success" />
        </div>

        {/* Depth Distribution */}
        <div style={{
          padding: '16px',
          background: 'rgba(10, 10, 15, 0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '14px',
          border: '1px solid rgba(255,255,255,0.05)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <BarChart3 size={14} color="#8b5cf6" />
            <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
              Depth Dist.
            </span>
          </div>
          <DepthChart data={summary.depthDistribution} />
        </div>
      </div>

      {/* Drift Events Table */}
      {summary.driftEvents.length > 0 && (
        <div style={{
          padding: '16px',
          background: 'rgba(10, 10, 15, 0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '14px',
          border: '1px solid rgba(239, 68, 68, 0.15)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <AlertTriangle size={14} color="#ef4444" />
            <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#f87171', fontWeight: 600 }}>
              Drift Events ({summary.driftEvents.length})
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
              <thead>
                <tr>
                  {['Step ID', 'Type', 'Delta', 'Time'].map(h => (
                    <th
                      key={h}
                      style={{
                        padding: '8px 12px',
                        textAlign: 'left',
                        borderBottom: '1px solid rgba(255,255,255,0.08)',
                        color: 'rgba(255,255,255,0.4)',
                        fontWeight: 600,
                        fontSize: '0.65rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.driftEvents.map((evt, i) => (
                  <tr key={i}>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)', fontFamily: 'monospace', color: 'rgba(255,255,255,0.6)', fontSize: '0.72rem' }}>
                      {evt.stepId}
                    </td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '6px',
                        background: 'rgba(239, 68, 68, 0.12)',
                        color: '#f87171',
                        fontSize: '0.68rem',
                        fontWeight: 600,
                      }}>
                        {evt.type}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)', fontFamily: 'monospace', color: '#f87171', fontWeight: 700 }}>
                      {evt.delta.toFixed(3)}
                    </td>
                    <td style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)', fontFamily: 'monospace', color: 'rgba(255,255,255,0.4)', fontSize: '0.72rem' }}>
                      {evt.time}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </motion.div>
  );
}
