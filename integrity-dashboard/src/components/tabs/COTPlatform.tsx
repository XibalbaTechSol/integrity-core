// @ts-nocheck
import { useState, useEffect, useMemo, useCallback } from 'react';
import { BrainCircuit, Wrench, FileEdit, AlertTriangle, ChevronDown, ChevronRight, Target, Terminal, Cpu, Users, XCircle, Search, Play, Pause, RefreshCw, BarChart2, ShieldAlert, CheckCircle, Activity, GitBranch, Zap, Globe } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { oracle } from '../../services/oracle';
import { useDashboard } from '../../context/useDashboard';

// Map a real OTel span name to the panel's interaction taxonomy (the oracle doesn't store
// an explicit interaction_type — it's derived from the span name/component).
function deriveInteraction(name: string): SpanNode['interaction_type'] {
  const n = (name || '').toLowerCase();
  if (n.includes('tool')) return 'TOOL';
  if (n.includes('mcp')) return 'MCP';
  if (n.includes('a2a')) return 'A2A';
  if (n.includes('bcc') || n.includes('mutation') || n.includes('anchor')) return 'MUTATION';
  if (n.includes('policy') || n.includes('api') || n.includes('retrieve') || n.includes('telemetry')) return 'API';
  return 'THOUGHT';
}

// Flatten the oracle's nested TraceTree (roots + children) into the flat SpanNode[] the panel
// rebuilds its tree from, preserving parent links.
function flattenTraceTree(nodes: any[], traceId: string, parent: string | null, out: SpanNode[] = []): SpanNode[] {
  for (const nd of nodes || []) {
    out.push({
      span_id: nd.span_id,
      trace_id: traceId,
      parent_span_id: parent,
      agent_id: nd.agent_id,
      interaction_type: deriveInteraction(nd.name),
      operation_name: nd.name,
      name: nd.name,
      start_time: nd.start_time,
      end_time: nd.end_time,
      duration_ms: nd.duration_ms,
    });
    if (nd.children?.length) flattenTraceTree(nd.children, traceId, nd.span_id, out);
  }
  return out;
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface SpanNode {
  span_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  agent_id: string;
  interaction_type: 'THOUGHT' | 'TOOL' | 'MCP' | 'A2A' | 'API' | 'MUTATION';
  operation_name?: string;
  input_data?: any;
  output_data?: any;
  start_time: string;
  end_time: string;
  duration_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  grounding_score?: number;
  correctness_score?: number;
  semantic_drift?: number;
  // Compatibility fields for legacy data
  message?: string;
  name?: string;
}

interface Trace {
  trace_id: string;
  agent_id: string;
  task_name: string;
  status: 'RUNNING' | 'SUCCESS' | 'FAILED' | 'ABORTED';
  input_payload?: any;
  output_payload?: any;
  total_latency_ms?: number;
  start_time: string;
  end_time?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getSpanMeta(span: SpanNode) {
  const type = span.interaction_type;
  switch (type) {
    case 'THOUGHT': return { icon: <BrainCircuit size={13} />, accent: '#8b5cf6', label: 'Reasoning' };
    case 'TOOL':    return { icon: <Wrench size={13} />,      accent: '#f59e0b', label: 'Tool' };
    case 'MCP':     return { icon: <Zap size={13} />,         accent: '#06b6d4', label: 'MCP' };
    case 'A2A':     return { icon: <Users size={13} />,       accent: '#ec4899', label: 'Agent-to-Agent' };
    case 'API':     return { icon: <Globe size={13} />,       accent: '#3b82f6', label: 'External API' };
    case 'MUTATION': return { icon: <FileEdit size={13} />,    accent: '#10b981', label: 'Mutation' };
    default:        return { icon: <Activity size={13} />,    accent: '#6b7280', label: 'Span' };
  }
}

function buildSpanTree(spans: SpanNode[]) {
  const roots: SpanNode[] = [];
  const childrenMap = new Map<string, SpanNode[]>();

  spans.forEach(span => {
    if (!childrenMap.has(span.span_id)) childrenMap.set(span.span_id, []);
  });

  spans.forEach(span => {
    if (span.parent_span_id && childrenMap.has(span.parent_span_id)) {
      childrenMap.get(span.parent_span_id)!.push(span);
    } else {
      roots.push(span);
    }
  });

  return { roots, childrenMap };
}

// ─── Span Debugger (LangSmith Style) ──────────────────────────────────────────

function SpanDebugger({ span, onClose }: { span: SpanNode, onClose: () => void }) {
  return (
    <div style={{ 
      position: 'fixed', right: 0, top: 0, bottom: 0, width: '500px', 
      background: 'rgba(10, 11, 14, 0.98)', backdropFilter: 'blur(20px)',
      borderLeft: '1px solid rgba(212, 175, 55, 0.3)', zIndex: 2000,
      display: 'flex', flexDirection: 'column', boxShadow: '-10px 0 30px rgba(0,0,0,0.5)'
    }}>
      <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase' }}>Span Detail</span>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', fontFamily: 'monospace' }}>{span.span_id.substring(0, 8)}...</span>
          </div>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'white' }}>{span.operation_name || span.interaction_type}</h3>
        </div>
        <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer' }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Metrics Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Duration</span>
            <div style={{ fontSize: '1.1rem', color: '#60a5fa', fontWeight: 700 }}>{span.duration_ms}ms</div>
          </div>
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Correctness</span>
            <div style={{ fontSize: '1.1rem', color: span.correctness_score && span.correctness_score > 0.8 ? '#10b981' : '#ef4444', fontWeight: 700 }}>
              {span.correctness_score ? (span.correctness_score * 100).toFixed(1) : 'N/A'}%
            </div>
          </div>
        </div>

        {/* Input Section */}
        <div>
          <label style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Input / Prompt</label>
          <div style={{ 
            padding: '12px', background: '#050507', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px',
            color: '#d1d5db', fontSize: '0.8rem', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all'
          }}>
            {typeof span.input_data === 'string' ? span.input_data : JSON.stringify(span.input_data, null, 2)}
          </div>
        </div>

        {/* Output Section */}
        <div>
          <label style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Output / Response</label>
          <div style={{ 
            padding: '12px', background: '#050507', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px',
            color: '#34d399', fontSize: '0.8rem', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all'
          }}>
            {typeof span.output_data === 'string' ? span.output_data : JSON.stringify(span.output_data, null, 2)}
          </div>
        </div>

        {/* Token Usage */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ flex: 1, padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', textAlign: 'center' }}>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'block' }}>Tokens In</span>
            <span style={{ fontSize: '1rem', color: 'white', fontWeight: 700 }}>{span.tokens_in || 0}</span>
          </div>
          <div style={{ flex: 1, padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', textAlign: 'center' }}>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'block' }}>Tokens Out</span>
            <span style={{ fontSize: '1rem', color: 'white', fontWeight: 700 }}>{span.tokens_out || 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Recursive Span Node ─────────────────────────────────────────────────────

function SpanNodeComponent({
  span,
  depth,
  childrenMap,
  selectedSpanId,
  onSelectSpan,
  isLastChild,
}: {
  span: SpanNode;
  depth: number;
  childrenMap: Map<string, SpanNode[]>;
  selectedSpanId: string | null;
  onSelectSpan: (id: string | null) => void;
  isLastChild: boolean;
}) {
  const [isOpen, setIsOpen] = useState(depth < 1);
  const meta = getSpanMeta(span);
  const children = span.span_id ? (childrenMap.get(span.span_id) || []) : [];
  const isSelected = span.span_id === selectedSpanId;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', position: 'relative' }}>
      <div 
        onClick={() => onSelectSpan(isSelected ? null : span.span_id)}
        style={{
          display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px',
          borderRadius: '6px', cursor: 'pointer', marginBottom: '4px',
          background: isSelected ? 'rgba(212, 175, 55, 0.15)' : 'transparent',
          border: `1px solid ${isSelected ? 'var(--gold)' : 'rgba(255,255,255,0.05)'}`,
          transition: 'all 0.2s'
        }}
      >
        {children.length > 0 && (
          <div onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }} style={{ color: 'rgba(255,255,255,0.4)' }}>
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>
        )}
        <div style={{ 
          width: '20px', height: '20px', borderRadius: '4px', background: meta.accent, 
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' 
        }}>
          {meta.icon}
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'white', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {span.operation_name || span.interaction_type}
            </span>
            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase' }}>{meta.label}</span>
          </div>
        </div>
        <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>{span.duration_ms}ms</span>
      </div>

      {children.length > 0 && isOpen && (
        <div style={{ paddingLeft: '20px', borderLeft: '1px solid rgba(255,255,255,0.05)', marginLeft: '10px' }}>
          {children.map((child, idx) => (
            <SpanNodeComponent
              key={child.span_id}
              span={child}
              depth={depth + 1}
              childrenMap={childrenMap}
              selectedSpanId={selectedSpanId}
              onSelectSpan={onSelectSpan}
              isLastChild={idx === children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export function COTPlatform() {
  const { selectedAgent } = useDashboard();
  const [traces, setTraces] = useState<Trace[]>([]);
  const [activeTrace, setActiveTrace] = useState<Trace | null>(null);
  const [spans, setSpans] = useState<SpanNode[]>([]);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [trajSearch, setTrajSearch] = useState('');

  useEffect(() => {
    const fetchTraces = async () => {
      if (!selectedAgent) { setTraces([]); return; }
      try {
        // Real recent OTel traces for the selected agent (the oracle has no global
        // /v1/traces; recent-traces is per-agent). Mapped onto the panel's Trace shape.
        const recent = await oracle.getRecentTraces(selectedAgent.eth_address, 50);
        setTraces(recent.map((t) => ({
          trace_id: t.trace_id,
          agent_id: selectedAgent.agent_id,
          task_name: t.name,
          status: 'SUCCESS' as const,
          start_time: t.start_time,
        })));
      } catch (err) { console.error("Failed to fetch traces", err); }
    };
    fetchTraces();
    const interval = setInterval(fetchTraces, 5000);
    return () => clearInterval(interval);
  }, [selectedAgent]);

  useEffect(() => {
    if (activeTrace) {
      // Real span tree from the oracle, flattened into the panel's SpanNode[].
      oracle.getTraceTree(activeTrace.trace_id)
        .then((tree: any) => setSpans(flattenTraceTree(tree.roots || [], activeTrace.trace_id, null)))
        .catch(err => console.error("Failed to fetch spans", err));
    }
  }, [activeTrace]);

  const filteredTraces = useMemo(() => {
    return traces.filter(t => 
      (!selectedAgent || t.agent_id === selectedAgent.agent_id) &&
      (!trajSearch || t.task_name.toLowerCase().includes(trajSearch.toLowerCase()))
    );
  }, [traces, selectedAgent, trajSearch]);

  const { roots, childrenMap } = useMemo(() => buildSpanTree(spans), [spans]);

  if (traces.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'rgba(255,255,255,0.3)' }}>
        <BrainCircuit size={48} style={{ marginBottom: '16px', opacity: 0.5 }} />
        <h3>No Traces Found</h3>
        <p>Start the Xibalba agent to generate reasoning spans.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '24px', height: 'calc(100vh - 120px)', overflow: 'hidden' }}>
      {/* LEFT: Trace Explorer */}
      <div style={{ 
        background: 'rgba(15, 15, 20, 0.8)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', 
        display: 'flex', flexDirection: 'column', overflow: 'hidden' 
      }}>
        <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Activity size={16} color="var(--gold)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 800, color: 'white', textTransform: 'uppercase' }}>Trace Explorer</span>
          </div>
          <input 
            type="text" placeholder="Search tasks..." value={trajSearch} onChange={e => setTrajSearch(e.target.value)}
            style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white', fontSize: '0.75rem' }}
          />
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
          {filteredTraces.map(trace => (
            <div 
              key={trace.trace_id}
              onClick={() => { setActiveTrace(trace); setSelectedSpanId(null); }}
              style={{ 
                padding: '12px', borderRadius: '12px', cursor: 'pointer', marginBottom: '8px',
                background: activeTrace?.trace_id === trace.trace_id ? 'rgba(212, 175, 55, 0.1)' : 'rgba(255,255,255,0.02)',
                border: `1px solid ${activeTrace?.trace_id === trace.trace_id ? 'var(--gold)' : 'rgba(255,255,255,0.05)'}`,
                transition: 'all 0.2s'
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'white', fontWeight: 500, marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{trace.task_name}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)' }}>{new Date(trace.start_time).toLocaleTimeString()}</span>
                <span style={{ fontSize: '0.6rem', padding: '2px 6px', borderRadius: '4px', background: trace.status === 'SUCCESS' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)', color: trace.status === 'SUCCESS' ? '#10b981' : '#ef4444' }}>{trace.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT: Span Graph & Debugger */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', overflow: 'hidden' }}>
        {activeTrace ? (
          <>
            <div style={{ 
              background: 'rgba(15, 15, 20, 0.8)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', 
              padding: '24px', display: 'flex', flexDirection: 'column', overflow: 'hidden', flex: 1 
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                  <h2 style={{ fontSize: '1.2rem', color: 'white', margin: 0 }}>{activeTrace.task_name}</h2>
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Trace ID: {activeTrace.trace_id}</span>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <div style={{ padding: '8px 12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                    <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'block' }}>Latency</span>
                    <span style={{ fontSize: '0.9rem', color: '#60a5fa', fontWeight: 700 }}>{activeTrace.total_latency_ms}ms</span>
                  </div>
                </div>
              </div>
              
              <div style={{ overflowY: 'auto', flex: 1, paddingRight: '12px' }}>
                {roots.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'rgba(255,255,255,0.3)' }}>No spans recorded for this trace.</div>
                ) : (
                  roots.map((span, idx) => (
                    <SpanNodeComponent
                      key={span.span_id}
                      span={span}
                      depth={0}
                      childrenMap={childrenMap}
                      selectedSpanId={selectedSpanId}
                      onSelectSpan={setSelectedSpanId}
                      isLastChild={idx === roots.length - 1}
                    />
                  ))
                )}
              </div>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'rgba(255,255,255,0.2)', fontSize: '1.2rem' }}>
            Select a trace from the explorer to begin diagnostics
          </div>
        )}
      </div>

      {selectedSpanId && spans.find(s => s.span_id === selectedSpanId) && (
        <SpanDebugger 
          span={spans.find(s => s.span_id === selectedSpanId)!} 
          onClose={() => setSelectedSpanId(null)} 
        />
      )}
    </div>
  );
}
