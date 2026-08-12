// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronRight, 
  ChevronDown, 
  Play, 
  RotateCcw, 
  Pause, 
  Edit3, 
  GitBranch,
  Zap,
  AlertCircle,
  CheckCircle2,
  XCircle
} from 'lucide-react';
import { Panel } from '../shared/Panel';
import { useDashboard } from '../../context/DashboardContext';
import { oracle, type SpanTreeNode } from '../../services/oracle';

// --- Map the oracle's real OTel span tree onto this panel's Span/Session shape.
// The renderer is unchanged; only the data source is (mock -> real getTraceTree).
function runTypeFromKind(kind: string, name: string): Span['run_type'] {
  const n = name.toLowerCase();
  if (n.includes('llm') || n.includes('completion') || n.includes('chat') || n.includes('generat')) return 'llm';
  if (n.includes('tool') || kind === 'SPAN_KIND_CLIENT') return 'tool';
  if (n.includes('retriev') || n.includes('search') || n.includes('embed')) return 'retriever';
  return 'chain';
}
function statusFromCode(code: string): Span['status'] {
  if (code === 'STATUS_CODE_ERROR') return 'error';
  if (code === 'STATUS_CODE_OK') return 'success';
  return 'pending';
}
function numAttr(attrs: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const v = attrs[k];
    if (typeof v === 'number') return v;
    if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return Number(v);
  }
  return undefined;
}
function mapSpan(node: SpanTreeNode, traceId: string, parentId: string | null): Span {
  const a = node.attributes || {};
  return {
    span_id: node.span_id,
    trace_id: traceId,
    parent_id: parentId,
    name: node.name,
    run_type: runTypeFromKind(node.kind, node.name),
    start_time: node.start_time,
    end_time: node.end_time,
    attributes: a,
    status: statusFromCode(node.status_code),
    duration: node.duration_ms / 1000,
    prompt_tokens: numAttr(a, ['llm.prompt_tokens', 'gen_ai.usage.prompt_tokens', 'prompt_tokens']),
    completion_tokens: numAttr(a, ['llm.completion_tokens', 'gen_ai.usage.completion_tokens', 'completion_tokens']),
    total_tokens: numAttr(a, ['llm.total_tokens', 'gen_ai.usage.total_tokens', 'total_tokens']),
    total_cost: numAttr(a, ['llm.cost', 'gen_ai.usage.cost', 'total_cost']),
  };
}
function flattenSpans(nodes: SpanTreeNode[], traceId: string, parentId: string | null): Span[] {
  const out: Span[] = [];
  for (const n of nodes) {
    out.push(mapSpan(n, traceId, parentId));
    const children = (n as { children?: SpanTreeNode[] }).children;
    if (children && children.length) out.push(...flattenSpans(children, traceId, n.span_id));
  }
  return out;
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface Span {
  span_id: string;
  trace_id: string;
  parent_id: string | null;
  name: string;
  run_type: 'llm' | 'chain' | 'tool' | 'retriever';
  start_time: string;
  end_time: string;
  attributes: Record<string, any>;
  status: 'success' | 'error' | 'pending';
  duration: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  total_cost?: number;
  feedback_stats?: Record<string, any>;
}

interface Session {
  session_id: string;
  traces: {
    trace_id: string;
    spans: Span[];
  }[];
  overall_risk_score: number;
}

interface TraceNode {
  span: Span;
  children: TraceNode[];
  isExpanded: boolean;
}

// ─── Components ──────────────────────────────────────────────────────────────

const RiskBadge = ({ score }: { score: number }) => {
  const color = score > 0.7 ? 'var(--error)' : score > 0.3 ? 'var(--warning)' : 'var(--success)';
  const label = score > 0.7 ? 'HIGH RISK' : score > 0.3 ? 'MODERATE' : 'NOMINAL';
  
  return (
    <span style={{
      fontSize: '0.6rem',
      fontWeight: 800,
      padding: '2px 6px',
      borderRadius: '4px',
      background: `color-mix(in srgb, ${color} 20%, transparent)`,
      border: `1px solid ${color}`,
      color: color,
      textTransform: 'uppercase',
    }}>
      {label} ({Math.round(score * 100)}%)
    </span>
  );
};

const TraceTreeNode = ({ node, depth = 0, onTimeTravel }: { node: TraceNode, depth: number, onTimeTravel: (span: Span) => void }) => {
  const [expanded, setExpanded] = useState(true);
  const { span } = node;

  return (
    <div style={{ marginLeft: depth > 0 ? '20px' : '0', marginTop: '4px' }}>
      <div 
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px', 
          padding: '8px', 
          background: 'rgba(255,255,255,0.03)', 
          border: '1px solid var(--glass-border)', 
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          transition: 'all 0.2s'
        }}
        onClick={() => setExpanded(!expanded)}
      >
        {node.children.length > 0 ? (
          expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        ) : <div style={{ width: 14 }} />}
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1 }}>
          <span style={{ 
            fontSize: '0.7rem', 
            fontWeight: 700, 
            color: span.run_type === 'tool' ? 'var(--theme-accent)' : 'var(--primary)' 
          }}>
            {span.run_type.toUpperCase()}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'white', fontFamily: 'monospace' }}>{span.name}</span>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{span.duration.toFixed(3)}s</span>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            onClick={(e) => { e.stopPropagation(); onTimeTravel(span); }}
            style={{ 
              background: 'transparent', 
              border: '1px solid var(--glass-border)', 
              color: 'var(--text-muted)', 
              padding: '2px 6px', 
              borderRadius: '4px', 
              fontSize: '0.6rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            <RotateCcw size={10} /> Rewind
          </button>
          {span.status === 'error' ? <XCircle size={14} color="var(--error)" /> : <CheckCircle2 size={14} color="var(--success)" />}
        </div>
      </div>
      
      {expanded && node.children.length > 0 && (
        <div style={{ borderLeft: '1px solid var(--glass-border)', marginLeft: '7px' }}>
          {node.children.map(child => (
            <TraceTreeNode key={child.span.span_id} node={child} depth={depth + 1} onTimeTravel={onTimeTravel} />
          ))}
        </div>
      )}
    </div>
  );
};

export function TraceAnalysisPanel() {
  const { selectedAgent } = useDashboard();
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [isRewinding, setIsRewinding] = useState(false);
  const [rewindSpan, setRewindSpan] = useState<Span | null>(null);

  // Real chain-of-thought: the selected agent's most recent OTel trace, fetched
  // from the oracle (getRecentTraces -> getTraceTree) and flattened into this
  // panel's Span/Session shape. overall_risk_score is derived from the real
  // error-span ratio rather than a fixed number.
  useEffect(() => {
    let cancelled = false;
    if (!selectedAgent) {
      setSelectedSession(null);
      return;
    }
    (async () => {
      try {
        const recent = await oracle.getRecentTraces(selectedAgent.eth_address, 1);
        if (!recent.length) {
          if (!cancelled) setSelectedSession(null);
          return;
        }
        const tree = await oracle.getTraceTree(recent[0].trace_id);
        const spans = flattenSpans(tree.roots, tree.trace_id, null);
        const errorCount = spans.filter((s) => s.status === 'error').length;
        if (!cancelled) {
          setSelectedSession({
            session_id: tree.trace_id,
            overall_risk_score: spans.length ? errorCount / spans.length : 0,
            traces: [{ trace_id: tree.trace_id, spans }],
          });
        }
      } catch {
        if (!cancelled) setSelectedSession(null);
      }
    })();
    return () => {
      cancelled = true;
    };
      // Depend on the DID string, not the agent OBJECT: DashboardProvider re-polls every
    // 15s and mapOracleAgent builds a fresh object each time, so an object dep re-runs
    // this effect (and re-arms its interval) on every poll even when the agent is
    // unchanged. Same fix as TokenWallet's.
  }, [selectedAgent?.eth_address]);

  const handleTimeTravel = (span: Span) => {
    setRewindSpan(span);
    setIsRewinding(true);
  };

  const buildTree = (spans: Span[]) => {
    const map: Record<string, TraceNode> = {};
    const roots: TraceNode[] = [];

    spans.forEach(s => {
      map[s.span_id] = { span: s, children: [], isExpanded: true };
    });

    spans.forEach(s => {
      if (s.parent_id && map[s.parent_id]) {
        map[s.parent_id].children.push(map[s.span_id]);
      } else {
        roots.push(map[s.span_id]);
      }
    });

    return roots;
  };

  if (!selectedSession) return <div style={{ padding: '20px', color: 'var(--text-muted)' }}>Loading session...</div>;

  const traceTree = buildTree(selectedSession.traces[0].spans);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Session Header */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        padding: 'var(--space-4)', 
        background: 'var(--bg-secondary)', 
        border: '1px solid var(--glass-border)', 
        borderRadius: 'var(--radius-md)' 
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>SESSION:</span>
          <span className="mono" style={{ fontSize: '0.9rem', fontWeight: 700 }}>{selectedSession.session_id}</span>
        </div>
        <RiskBadge score={selectedSession.overall_risk_score} />
      </div>

      <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
        {/* Left: The Trace Tree */}
        <Panel title="Execution Trajectory" icon={<GitBranch size={18} />}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {traceTree.map(node => (
              <TraceTreeNode key={node.span.span_id} node={node} depth={0} onTimeTravel={handleTimeTravel} />
            ))}
          </div>
        </Panel>

        {/* Right: Inspector & Time Travel */}
        <Panel title="Step Inspector" icon={<Edit3 size={18} />}>
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: 'var(--space-4)',
            minHeight: '300px',
            padding: 'var(--space-4)',
            background: 'rgba(0,0,0,0.2)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--glass-border)'
          }}>
            {rewindSpan ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--theme-accent)' }}>
                  <RotateCcw size={16} />
                  <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>TIME TRAVEL ACTIVE</span>
                </div>
                
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  You have rewound the agent to: <span className="mono" style={{ color: 'white' }}>{rewindSpan.name}</span>
                </div>

                <div className="form-group">
                  <label className="form-label">Modify Input State</label>
                  <textarea 
                    className="input" 
                    style={{ height: '120px', fontFamily: 'monospace', fontSize: '0.8rem' }}
                    defaultValue={JSON.stringify(rewindSpan.attributes['integrity.input'], null, 2)}
                  />
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button 
                    className="btn btn-primary" 
                    style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
                    onClick={() => setIsRewinding(false)}
                  >
                    <Play size={14} /> Fork Execution
                  </button>
                  <button 
                    className="btn btn-ghost" 
                    style={{ flex: 1 }}
                    onClick={() => setRewindSpan(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center', 
                justifyContent: 'center', 
                height: '100%', 
                color: 'var(--text-muted)', 
                textAlign: 'center',
                gap: '12px'
              }}>
                <div style={{ 
                  width: '48px', 
                  height: '48px', 
                  borderRadius: '50%', 
                  background: 'var(--bg-secondary)', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  border: '1px solid var(--glass-border)' 
                }}>
                  <Zap size={24} />
                </div>
                <p style={{ fontSize: '0.85rem' }}>Select a span in the trajectory<br/>to inspect or rewind state.</p>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
