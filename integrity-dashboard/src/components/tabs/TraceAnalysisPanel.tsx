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
            color: span.run_type === 'tool' ? 'var(--gold)' : 'var(--primary)' 
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
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [isRewinding, setIsRewinding] = useState(false);
  const [rewindSpan, setRewindSpan] = useState<Span | null>(null);

  // Mock data for demonstration
  const mockSession: Session = {
    session_id: "sess_v7_9921",
    overall_risk_score: 0.45,
    traces: [{
      trace_id: "tr_root_1",
      spans: [
        { span_id: "s1", trace_id: "tr_root_1", parent_id: null, name: "ReflectiveAgent.run", run_type: "chain", start_time: "2026-07-05T10:00:00Z", end_time: "2026-07-05T10:00:05Z", attributes: { "integrity.input": "Task: Audit Wallet" }, status: "success", duration: 5.0, prompt_tokens: 100, completion_tokens: 50, total_tokens: 150, total_cost: 0.002, feedback_stats: {} },
        { span_id: "s2", trace_id: "tr_root_1", parent_id: "s1", name: "ReflectiveAgent.reflect", run_type: "chain", start_time: "2026-07-05T10:00:01Z", end_time: "2026-07-05T10:00:03Z", attributes: { "integrity.output": "Hypothesis: Use AuditTool" }, status: "success", duration: 2.0, prompt_tokens: 50, completion_tokens: 100, total_tokens: 150, total_cost: 0.001, feedback_stats: {} },
        { span_id: "s3", trace_id: "tr_root_1", parent_id: "s1", name: "AuditTool.execute", run_type: "tool", start_time: "2026-07-05T10:00:03Z", end_time: "2026-07-05T10:00:04Z", attributes: { "integrity.output": "Balance: 10 ETH" }, status: "success", duration: 1.0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, total_cost: 0, feedback_stats: {} },
      ]
    }]
  };

  useEffect(() => { setSelectedSession(mockSession); }, []);

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
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--gold)' }}>
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
