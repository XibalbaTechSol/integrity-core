import { useState, useEffect, useCallback } from 'react';
import { BrainCircuit, Wrench, Zap, Users, Globe, FileEdit, Activity, ChevronDown, ChevronRight } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { oracle, RecentTraceDto, SpanTreeNode } from '../services/oracle';

function getSpanMeta(span: SpanTreeNode) {
  const kind = (span.kind || '').toUpperCase();
  switch (kind) {
    case 'THOUGHT': return { icon: <BrainCircuit size={13} />, accent: 'var(--text-primary)', label: 'Reasoning' };
    case 'TOOL':    return { icon: <Wrench size={13} />,      accent: 'var(--text-primary)', label: 'Tool' };
    case 'MCP':     return { icon: <Zap size={13} />,         accent: 'var(--text-primary)', label: 'MCP' };
    case 'A2A':     return { icon: <Users size={13} />,       accent: 'var(--text-primary)', label: 'Agent-to-Agent' };
    case 'API':     return { icon: <Globe size={13} />,       accent: 'var(--text-primary)', label: 'External API' };
    case 'MUTATION': return { icon: <FileEdit size={13} />,    accent: 'var(--text-primary)', label: 'Mutation' };
    default:        return { icon: <Activity size={13} />,    accent: 'var(--text-primary)', label: span.kind || 'Span' };
  }
}

function SpanDebugger({ span, onClose }: { span: SpanTreeNode, onClose: () => void }) {
  return (
    <div style={{
      position: 'absolute', right: 0, top: 0, bottom: 0, width: '400px',
      background: 'var(--surface-color)',
      borderLeft: '1px solid var(--border-color)', zIndex: 10,
      display: 'flex', flexDirection: 'column', boxShadow: '-5px 0 15px rgba(0,0,0,0.5)'
    }}>
      <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Span Detail</span>
          <h3 style={{ margin: 0, fontSize: '1.1rem' }}>{span.name}</h3>
        </div>
        <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', cursor: 'pointer' }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div style={{ padding: '1rem', background: 'var(--bg-color)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Duration</span>
            <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{span.duration_ms}ms</div>
          </div>
          <div style={{ padding: '1rem', background: 'var(--bg-color)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Status</span>
            <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{span.status_code || 'UNSET'}</div>
          </div>
        </div>

        <div>
          <label style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '0.5rem' }}>Attributes</label>
          <div style={{ padding: '1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.85rem', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(span.attributes ?? {}, null, 2)}
          </div>
        </div>
      </div>
    </div>
  );
}

function SpanNodeComponent({ span, depth, selectedSpanId, onSelectSpan }: { span: SpanTreeNode, depth: number, selectedSpanId: string | null, onSelectSpan: (id: string | null) => void }) {
  const [isOpen, setIsOpen] = useState(depth < 1);
  const meta = getSpanMeta(span);
  const children = span.children || [];
  const isSelected = span.span_id === selectedSpanId;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', position: 'relative' }}>
      <div
        onClick={() => onSelectSpan(isSelected ? null : span.span_id)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0.75rem',
          borderRadius: '4px', cursor: 'pointer', marginBottom: '0.25rem',
          background: isSelected ? 'var(--bg-color)' : 'transparent',
          border: `1px solid ${isSelected ? 'var(--text-primary)' : 'transparent'}`,
          transition: 'all 0.2s'
        }}
      >
        {children.length > 0 && (
          <div onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }} style={{ color: 'var(--text-secondary)', display: 'flex' }}>
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: meta.accent }}>
          {meta.icon}
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {span.name}
            </span>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{meta.label}</span>
          </div>
        </div>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{span.duration_ms}ms</span>
      </div>

      {children.length > 0 && isOpen && (
        <div style={{ paddingLeft: '1.25rem', borderLeft: '1px solid var(--border-color)', marginLeft: '0.5rem' }}>
          {children.map(child => (
            <SpanNodeComponent key={child.span_id} span={child} depth={depth + 1} selectedSpanId={selectedSpanId} onSelectSpan={onSelectSpan} />
          ))}
        </div>
      )}
    </div>
  );
}

function findSpan(nodes: SpanTreeNode[], spanId: string): SpanTreeNode | null {
  for (const node of nodes) {
    if (node.span_id === spanId) return node;
    const found = findSpan(node.children || [], spanId);
    if (found) return found;
  }
  return null;
}

export function COTPlatform() {
  const { selectedAgent } = useDashboard();
  const [traces, setTraces] = useState<RecentTraceDto[]>([]);
  const [activeTrace, setActiveTrace] = useState<RecentTraceDto | null>(null);
  const [roots, setRoots] = useState<SpanTreeNode[]>([]);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedAgent) { setTraces([]); setActiveTrace(null); return; }
    oracle.getRecentTraces(selectedAgent.eth_address, 25)
      .then(t => { setTraces(t); setActiveTrace(t[0] || null); })
      .catch(() => { setTraces([]); setActiveTrace(null); });
  }, [selectedAgent]);

  const loadTree = useCallback((traceId: string) => {
    oracle.getTraceTree(traceId).then(tree => setRoots(tree.roots)).catch(() => setRoots([]));
  }, []);

  useEffect(() => {
    if (activeTrace) loadTree(activeTrace.trace_id);
    else setRoots([]);
  }, [activeTrace, loadTree]);

  const selectedSpan = selectedSpanId ? findSpan(roots, selectedSpanId) : null;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '250px 1fr', gap: '1.5rem', height: '500px', position: 'relative' }}>
      <div style={{ background: 'var(--surface-color)', border: '1px solid var(--border-color)', borderRadius: '8px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase' }}>Trace Explorer</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0.75rem' }}>
          {traces.length === 0 && (
            <div style={{ padding: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>No traces recorded for this agent yet.</div>
          )}
          {traces.map(trace => (
            <div
              key={trace.trace_id}
              onClick={() => { setActiveTrace(trace); setSelectedSpanId(null); }}
              style={{
                padding: '0.75rem', borderRadius: '4px', cursor: 'pointer', marginBottom: '0.5rem',
                background: activeTrace?.trace_id === trace.trace_id ? 'var(--bg-color)' : 'transparent',
                border: `1px solid ${activeTrace?.trace_id === trace.trace_id ? 'var(--text-primary)' : 'var(--border-color)'}`
              }}
            >
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>{trace.name}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{new Date(trace.start_time).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ background: 'var(--surface-color)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.5rem', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {activeTrace ? (
          <>
            <div style={{ marginBottom: '1.5rem' }}>
              <h2 style={{ margin: '0 0 0.25rem 0', fontSize: '1.25rem' }}>{activeTrace.name}</h2>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Trace ID: {activeTrace.trace_id}</span>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, paddingRight: '0.5rem' }}>
              {roots.map(span => (
                <SpanNodeComponent key={span.span_id} span={span} depth={0} selectedSpanId={selectedSpanId} onSelectSpan={setSelectedSpanId} />
              ))}
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
            Select a trace to view
          </div>
        )}
      </div>

      {selectedSpan && (
        <SpanDebugger span={selectedSpan} onClose={() => setSelectedSpanId(null)} />
      )}
    </div>
  );
}
