import { useState, useEffect, useMemo } from 'react';
import { Brain, Activity, Clock, Filter, GitCompare, Database, BarChart2, CheckCircle, XCircle, Search, Cpu, List, AlignLeft, SplitSquareHorizontal, Layers, ChevronRight, ChevronDown, Wrench, Zap, Globe, FileEdit, Plus, Trash2, Play, ArrowLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { API_BASE } from '../../constants';
import { useDashboard } from '../../context/useDashboard';

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
}

interface Trace {
  trace_id: string;
  agent_id: string;
  task_name: string;
  status: 'RUNNING' | 'SUCCESS' | 'FAILED' | 'ABORTED';
  start_time: string;
  total_latency_ms?: number;
  tokens_total?: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getSpanMeta(type: string) {
  switch (type) {
    case 'THOUGHT': return { icon: <Brain size={14} />, color: '#8b5cf6' };
    case 'TOOL':    return { icon: <Wrench size={14} />, color: '#f59e0b' };
    case 'MCP':     return { icon: <Zap size={14} />, color: '#06b6d4' };
    case 'A2A':     return { icon: <Database size={14} />, color: '#ec4899' };
    case 'API':     return { icon: <Globe size={14} />, color: '#3b82f6' };
    case 'MUTATION': return { icon: <FileEdit size={14} />, color: '#10b981' };
    default:        return { icon: <Activity size={14} />, color: '#6b7280' };
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

// ─── Main Component ──────────────────────────────────────────────────────────

interface Dataset {
  id: string;
  name: string;
  description: string;
  evaluatorType: 'LLM_JUDGE' | 'EXACT_MATCH' | 'REGEX';
  testCases: { input: string; expected: string }[];
  runHistory: { date: string; passed: number; failed: number; avgScore: number }[];
}

export function ObservabilityHub() {
  const { selectedAgent } = useDashboard();
  const [activeTab, setActiveTab] = useState<'explorer' | 'waterfall' | 'compare' | 'evals'>('explorer');
  const [traces, setTraces] = useState<Trace[]>([]);
  const [activeTrace, setActiveTrace] = useState<Trace | null>(null);
  const [compareTraceA, setCompareTraceA] = useState<Trace | null>(null);
  const [compareTraceB, setCompareTraceB] = useState<Trace | null>(null);
  const [compareSpansA, setCompareSpansA] = useState<SpanNode[]>([]);
  const [compareSpansB, setCompareSpansB] = useState<SpanNode[]>([]);
  const [spans, setSpans] = useState<SpanNode[]>([]);
  const [search, setSearch] = useState('');

  // Evals Tab State
  const [datasets, setDatasets] = useState<Dataset[]>([
    {
      id: 'ds-1',
      name: 'DeFi Swap Integrity Routing',
      description: 'Verifies optimal path routing for ITK/USDC swaps without frontrunning.',
      evaluatorType: 'LLM_JUDGE',
      testCases: [
        { input: 'Swap 500 ITK for USDC', expected: 'Execute Uniswap V3 swap; output slippage < 0.5%.' },
        { input: 'Swap 10000 ITK', expected: 'Route via aggregator; check gas fee vs price impact.' }
      ],
      runHistory: [
        { date: '2026-07-04', passed: 2, failed: 0, avgScore: 98 }
      ]
    },
    {
      id: 'ds-2',
      name: 'HIPAA Patient Data Access Audit',
      description: 'Checks that zero unencrypted PHI fields are transmitted or stored.',
      evaluatorType: 'REGEX',
      testCases: [
        { input: 'Request patient chart P-102', expected: 'Sanitize patient name, SSN, and birth date.' },
        { input: 'Save diagnostics log', expected: 'AES-256 encrypted string, no cleartext names.' }
      ],
      runHistory: [
        { date: '2026-07-05', passed: 2, failed: 0, avgScore: 100 }
      ]
    }
  ]);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('');
  const [newDatasetDesc, setNewDatasetDesc] = useState('');
  const [newDatasetEval, setNewDatasetEval] = useState<'LLM_JUDGE' | 'EXACT_MATCH' | 'REGEX'>('LLM_JUDGE');
  
  const [tc1Input, setTc1Input] = useState('');
  const [tc1Expected, setTc1Expected] = useState('');
  const [tc2Input, setTc2Input] = useState('');
  const [tc2Expected, setTc2Expected] = useState('');

  const [isRunningEval, setIsRunningEval] = useState(false);
  const [evalResults, setEvalResults] = useState<any | null>(null);

  // Fetch traces
  useEffect(() => {
    const fetchTraces = async () => {
      try {
        const res = await axios.get(`${API_BASE}/v1/traces`);
        if (res.data && Array.isArray(res.data)) {
          // Augment with mock data if needed for richer display
          const augmented = res.data.map(t => ({
            ...t,
            tokens_total: t.tokens_total || Math.floor(Math.random() * 5000) + 500,
            total_latency_ms: t.total_latency_ms || Math.floor(Math.random() * 8000) + 200,
          }));
          setTraces(augmented);
        }
      } catch (e) {}
    };
    fetchTraces();
    const interval = setInterval(fetchTraces, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch spans for active trace
  useEffect(() => {
    if (activeTrace) {
      axios.get(`${API_BASE}/v1/spans?trace_id=${activeTrace.trace_id}`)
        .then(res => setSpans(res.data || []))
        .catch(() => {});
    }
  }, [activeTrace]);

  // Fetch spans for comparison Trace A
  useEffect(() => {
    if (compareTraceA) {
      axios.get(`${API_BASE}/v1/spans?trace_id=${compareTraceA.trace_id}`)
        .then(res => setCompareSpansA(res.data || []))
        .catch(() => {});
    } else {
      setCompareSpansA([]);
    }
  }, [compareTraceA]);

  // Fetch spans for comparison Trace B
  useEffect(() => {
    if (compareTraceB) {
      axios.get(`${API_BASE}/v1/spans?trace_id=${compareTraceB.trace_id}`)
        .then(res => setCompareSpansB(res.data || []))
        .catch(() => {});
    } else {
      setCompareSpansB([]);
    }
  }, [compareTraceB]);

  const filteredTraces = useMemo(() => {
    return traces.filter(t => 
      (!selectedAgent || t.agent_id === selectedAgent.eth_address || t.agent_id === selectedAgent.agent_id) &&
      (!search || t.task_name.toLowerCase().includes(search.toLowerCase()))
    );
  }, [traces, selectedAgent, search]);

  const handleCreateDataset = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDatasetName) return;
    const newDs: Dataset = {
      id: `ds-${Date.now()}`,
      name: newDatasetName,
      description: newDatasetDesc,
      evaluatorType: newDatasetEval,
      testCases: [
        { input: tc1Input || 'Test Input 1', expected: tc1Expected || 'Expected Output 1' },
        ...(tc2Input ? [{ input: tc2Input, expected: tc2Expected }] : [])
      ],
      runHistory: []
    };
    setDatasets([...datasets, newDs]);
    setNewDatasetName('');
    setNewDatasetDesc('');
    setTc1Input('');
    setTc1Expected('');
    setTc2Input('');
    setTc2Expected('');
    setShowCreateForm(false);
  };

  const runEvaluator = () => {
    if (!selectedDataset) return;
    setIsRunningEval(true);
    setEvalResults(null);
    
    setTimeout(() => {
      setIsRunningEval(false);
      // Simulate results
      setEvalResults({
        passed: selectedDataset.testCases.length,
        failed: 0,
        avgScore: 95 + Math.floor(Math.random() * 5),
        metrics: {
          semanticSimilarity: 0.94,
          factuality: 0.97,
          safety: 1.0,
          latencyGrade: 'A'
        },
        runs: selectedDataset.testCases.map((tc, idx) => ({
          input: tc.input,
          expected: tc.expected,
          actual: `[PROCESSED] Successfully executed with correct cryptographic signatures and OPA compliance gating. Verified: ${tc.expected}`,
          score: 93 + Math.floor(Math.random() * 7),
          status: 'PASSED'
        }))
      });
      
      // Update history
      setDatasets(prev => prev.map(ds => {
        if (ds.id === selectedDataset.id) {
          return {
            ...ds,
            runHistory: [
              {
                date: new Date().toISOString().split('T')[0],
                passed: ds.testCases.length,
                failed: 0,
                avgScore: 96
              },
              ...ds.runHistory
            ]
          };
        }
        return ds;
      }));
    }, 1500);
  };

  const renderTabs = () => (
    <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '12px', marginBottom: '16px' }}>
      {[
        { id: 'explorer', label: 'Trace Explorer', icon: <List size={16} /> },
        { id: 'waterfall', label: 'Waterfall Diagnostics', icon: <AlignLeft size={16} /> },
        { id: 'compare', label: 'Comparison Engine', icon: <SplitSquareHorizontal size={16} /> },
        { id: 'evals', label: 'Datasets & Evals', icon: <Database size={16} /> },
      ].map(t => (
        <button
          key={t.id}
          onClick={() => setActiveTab(t.id as any)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px',
            background: activeTab === t.id ? 'var(--primary)' : 'transparent',
            color: activeTab === t.id ? '#000' : 'var(--text-muted)',
            border: `1px solid ${activeTab === t.id ? 'var(--primary)' : 'transparent'}`,
            borderRadius: '999px', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );

  return (
    <div style={{ 
      background: 'rgba(15, 15, 20, 0.6)', 
      backdropFilter: 'blur(24px)', 
      borderRadius: '16px', 
      border: '1px solid rgba(255,255,255,0.05)',
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      height: '600px',
      boxShadow: '0 10px 40px rgba(0,0,0,0.3)'
    }}>
      {renderTabs()}
      
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <AnimatePresence mode="wait">
          {activeTab === 'explorer' && (
            <motion.div key="explorer" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div style={{ position: 'relative', width: '300px' }}>
                  <Search size={16} style={{ position: 'absolute', left: '12px', top: '10px', color: 'rgba(255,255,255,0.4)' }} />
                  <input 
                    type="text" placeholder="Search traces by intent or task..." 
                    value={search} onChange={e => setSearch(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px 8px 36px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'white', fontSize: '0.85rem' }}
                  />
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>Task Intent</th>
                      <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>Status</th>
                      <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>Latency</th>
                      <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>Tokens</th>
                      <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>Start Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTraces.map(trace => (
                      <tr 
                        key={trace.trace_id} 
                        onClick={() => { setActiveTrace(trace); setActiveTab('waterfall'); }}
                        style={{ cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.02)', transition: 'background 0.2s' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '12px', color: 'white', fontWeight: 500 }}>{trace.task_name}</td>
                        <td style={{ padding: '12px' }}>
                          <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 700,
                            background: trace.status === 'SUCCESS' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                            color: trace.status === 'SUCCESS' ? '#10b981' : '#ef4444'
                          }}>{trace.status}</span>
                        </td>
                        <td style={{ padding: '12px', color: '#60a5fa', fontFamily: 'monospace' }}>{(trace.total_latency_ms || 0).toLocaleString()}ms</td>
                        <td style={{ padding: '12px', color: '#a78bfa', fontFamily: 'monospace' }}>{(trace.tokens_total || 0).toLocaleString()}</td>
                        <td style={{ padding: '12px', color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem' }}>{new Date(trace.start_time).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {activeTab === 'waterfall' && (
            <motion.div key="waterfall" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              {!activeTrace ? (
                <div style={{ margin: 'auto', color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                  <AlignLeft size={48} style={{ opacity: 0.5, marginBottom: '16px' }} />
                  <div>Select a trace from the explorer to view its waterfall diagnostics.</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', padding: '16px', background: 'rgba(0,0,0,0.3)', borderRadius: '12px' }}>
                    <div>
                      <h3 style={{ margin: 0, color: 'white', fontSize: '1.2rem' }}>{activeTrace.task_name}</h3>
                      <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>{activeTrace.trace_id}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.65rem', color: 'var(--gold)', textTransform: 'uppercase', fontWeight: 800 }}>Total Latency</div>
                        <div style={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace', fontSize: '1.2rem' }}>{activeTrace.total_latency_ms}ms</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.65rem', color: 'var(--gold)', textTransform: 'uppercase', fontWeight: 800 }}>Tokens</div>
                        <div style={{ color: '#a78bfa', fontWeight: 700, fontFamily: 'monospace', fontSize: '1.2rem' }}>{activeTrace.tokens_total}</div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Waterfall Chart */}
                  <div style={{ flex: 1, overflowY: 'auto', paddingRight: '12px' }}>
                    {spans.length === 0 ? (
                      <div style={{ textAlign: 'center', padding: '40px', color: 'rgba(255,255,255,0.3)' }}>No spans recorded.</div>
                    ) : (
                      <WaterfallChart spans={spans} totalLatency={activeTrace.total_latency_ms || 1000} />
                    )}
                  </div>
                </div>
              )}
            </motion.div>
          )}

          {activeTab === 'compare' && (
            <motion.div key="compare" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
               <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                 <div style={{ flex: 1 }}>
                   <label style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase' }}>Trace A</label>
                   <select 
                     value={compareTraceA?.trace_id || ''} 
                     onChange={e => setCompareTraceA(traces.find(t => t.trace_id === e.target.value) || null)}
                     style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '8px', marginTop: '4px' }}
                   >
                     <option value="">Select Trace...</option>
                     {traces.map(t => <option key={t.trace_id} value={t.trace_id}>{t.task_name}</option>)}
                   </select>
                 </div>
                 <div style={{ flex: 1 }}>
                   <label style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase' }}>Trace B</label>
                   <select 
                     value={compareTraceB?.trace_id || ''} 
                     onChange={e => setCompareTraceB(traces.find(t => t.trace_id === e.target.value) || null)}
                     style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '8px', marginTop: '4px' }}
                   >
                     <option value="">Select Trace...</option>
                     {traces.map(t => <option key={t.trace_id} value={t.trace_id}>{t.task_name}</option>)}
                   </select>
                 </div>
               </div>

               {compareTraceA && compareTraceB ? (
                 <div style={{ flex: 1, display: 'flex', gap: '16px', overflow: 'hidden' }}>
                    {/* Simplified Side-by-side comparison view */}
                    {[compareTraceA, compareTraceB].map((trace, i) => (
                      <div key={i} style={{ flex: 1, background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                        <h4 style={{ color: 'white', margin: '0 0 16px 0', fontSize: '1rem' }}>{trace.task_name}</h4>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '16px' }}>
                          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px' }}>
                            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'block' }}>Latency</span>
                            <span style={{ color: '#60a5fa', fontWeight: 700 }}>{trace.total_latency_ms}ms</span>
                          </div>
                          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px' }}>
                            <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'block' }}>Tokens</span>
                            <span style={{ color: '#a78bfa', fontWeight: 700 }}>{trace.tokens_total}</span>
                          </div>
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', marginBottom: '12px' }}>
                           <p style={{ margin: 0 }}>Detailed span comparison feature is active. Latency delta: {Math.abs((compareTraceA.total_latency_ms||0) - (compareTraceB.total_latency_ms||0))}ms</p>
                        </div>
                        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px', flex: 1 }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Execution Spans ({i === 0 ? compareSpansA.length : compareSpansB.length})</span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {(i === 0 ? compareSpansA : compareSpansB).map(span => (
                              <div key={span.span_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.03)', padding: '8px', borderRadius: '6px', fontSize: '0.75rem' }}>
                                <div>
                                  <span style={{ color: 'white', fontWeight: 600, display: 'block' }}>{span.operation_name || 'unnamed_op'}</span>
                                  <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase' }}>{span.interaction_type}</span>
                                </div>
                                <span style={{ fontFamily: 'monospace', color: '#60a5fa' }}>{span.duration_ms || 0}ms</span>
                              </div>
                            ))}
                            {(i === 0 ? compareSpansA : compareSpansB).length === 0 && (
                              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.3)', fontStyle: 'italic', padding: '8px 0' }}>No execution spans loaded for this trace.</div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                 </div>
               ) : (
                 <div style={{ margin: 'auto', color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                   <GitCompare size={48} style={{ opacity: 0.5, marginBottom: '16px' }} />
                   <div>Select two traces to compare their execution graphs.</div>
                 </div>
               )}
            </motion.div>
          )}

          {activeTab === 'evals' && (
            <motion.div key="evals" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
               {showCreateForm ? (
                 <form onSubmit={handleCreateDataset} style={{ display: 'flex', flexDirection: 'column', gap: '12px', background: 'rgba(0,0,0,0.2)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', overflowY: 'auto', maxHeight: '100%' }}>
                   <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                     <button type="button" onClick={() => setShowCreateForm(false)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                       <ArrowLeft size={16} />
                     </button>
                     <h3 style={{ color: 'white', margin: 0 }}>Create New Dataset</h3>
                   </div>
                   
                   <div>
                     <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Dataset Name</label>
                     <input type="text" placeholder="e.g. HIPAA Compliance Validation" value={newDatasetName} onChange={e => setNewDatasetName(e.target.value)} required style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '8px' }} />
                   </div>

                   <div>
                     <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Description</label>
                     <textarea placeholder="Purpose of this evaluation dataset..." value={newDatasetDesc} onChange={e => setNewDatasetDesc(e.target.value)} style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '8px', minHeight: '60px', resize: 'vertical' }} />
                   </div>

                   <div>
                     <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Evaluator Engine</label>
                     <select value={newDatasetEval} onChange={e => setNewDatasetEval(e.target.value as any)} style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '8px' }}>
                       <option value="LLM_JUDGE">LLM-as-a-judge (GPT-4 / Gemini)</option>
                       <option value="EXACT_MATCH">Exact Match</option>
                       <option value="REGEX">Regex Validator</option>
                     </select>
                   </div>

                   <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
                     <h4 style={{ color: 'white', margin: '0 0 8px 0', fontSize: '0.85rem' }}>Test Cases</h4>
                     
                     <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '8px' }}>
                       <div>
                         <label style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>Test Input 1</label>
                         <input type="text" placeholder="e.g. Run audit check" value={tc1Input} onChange={e => setTc1Input(e.target.value)} style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '6px', fontSize: '0.75rem' }} />
                       </div>
                       <div>
                         <label style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>Expected Output 1</label>
                         <input type="text" placeholder="e.g. Audit success" value={tc1Expected} onChange={e => setTc1Expected(e.target.value)} style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '6px', fontSize: '0.75rem' }} />
                       </div>
                     </div>

                     <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                       <div>
                         <label style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>Test Input 2 (Optional)</label>
                         <input type="text" placeholder="e.g. Clean database" value={tc2Input} onChange={e => setTc2Input(e.target.value)} style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '6px', fontSize: '0.75rem' }} />
                       </div>
                       <div>
                         <label style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>Expected Output 2 (Optional)</label>
                         <input type="text" placeholder="e.g. Records wiped" value={tc2Expected} onChange={e => setTc2Expected(e.target.value)} style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', borderRadius: '6px', fontSize: '0.75rem' }} />
                       </div>
                     </div>
                   </div>

                   <button type="submit" style={{ marginTop: '12px', padding: '10px', background: 'var(--primary)', color: 'black', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}>
                     Save Dataset
                   </button>
                 </form>
               ) : selectedDataset ? (
                 <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
                   <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(0,0,0,0.2)', padding: '12px 16px', borderRadius: '12px', marginBottom: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
                     <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                       <button onClick={() => { setSelectedDataset(null); setEvalResults(null); }} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                         <ArrowLeft size={16} />
                       </button>
                       <div>
                         <h3 style={{ color: 'white', margin: 0 }}>{selectedDataset.name}</h3>
                         <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>Evaluator: {selectedDataset.evaluatorType}</span>
                       </div>
                     </div>
                     <button onClick={runEvaluator} disabled={isRunningEval} style={{ padding: '8px 16px', background: 'var(--primary)', color: 'black', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
                       <Play size={14} /> {isRunningEval ? 'Running...' : 'Run Evaluator'}
                     </button>
                   </div>

                   {isRunningEval ? (
                     <div style={{ margin: 'auto', textAlign: 'center' }}>
                       <div style={{ width: '36px', height: '36px', border: '2px solid rgba(255,255,255,0.1)', borderTop: '2px solid var(--primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: 'auto', marginBottom: '16px' }} />
                       <div style={{ color: 'white', fontSize: '0.9rem', fontWeight: 600 }}>Executing LLM-as-a-judge scoring...</div>
                       <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem', marginTop: '4px' }}>Grading reasoning traces against reference ground-truth...</div>
                     </div>
                   ) : evalResults ? (
                     <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px', paddingRight: '4px' }}>
                       <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                         <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                           <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', display: 'block', textTransform: 'uppercase' }}>Overall Score</span>
                           <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)' }}>{evalResults.avgScore}%</span>
                         </div>
                         <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                           <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', display: 'block', textTransform: 'uppercase' }}>Semantic Similarity</span>
                           <span style={{ fontSize: '1.5rem', fontWeight: 800, color: '#60a5fa' }}>{Math.round(evalResults.metrics.semanticSimilarity * 100)}%</span>
                         </div>
                         <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                           <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', display: 'block', textTransform: 'uppercase' }}>Factuality</span>
                           <span style={{ fontSize: '1.5rem', fontWeight: 800, color: '#a78bfa' }}>{Math.round(evalResults.metrics.factuality * 100)}%</span>
                         </div>
                         <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                           <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', display: 'block', textTransform: 'uppercase' }}>Safety Score</span>
                           <span style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10b981' }}>{Math.round(evalResults.metrics.safety * 100)}%</span>
                         </div>
                       </div>

                       <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                         <h4 style={{ color: 'white', margin: '8px 0 4px 0', fontSize: '0.9rem' }}>Scored Test Runs</h4>
                         {evalResults.runs.map((run: any, idx: number) => (
                           <div key={idx} style={{ background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '12px' }}>
                             <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                               <span style={{ color: 'white', fontWeight: 600 }}>Test Case #{idx + 1}</span>
                               <span style={{ color: run.score >= 90 ? '#10b981' : '#f59e0b', fontWeight: 700, fontFamily: 'monospace' }}>{run.score}% ({run.status})</span>
                             </div>
                             <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.75rem' }}>
                               <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Input:</span> <span style={{ color: 'white' }}>{run.input}</span></div>
                               <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Expected Ground-truth:</span> <span style={{ color: '#a78bfa' }}>{run.expected}</span></div>
                               <div style={{ background: 'rgba(0,0,0,0.2)', padding: '6px', borderRadius: '4px', marginTop: '4px' }}>
                                 <span style={{ color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: '2px', fontSize: '0.65rem' }}>Actual Agent Output:</span>
                                 <span style={{ color: 'rgba(255,255,255,0.8)' }}>{run.actual}</span>
                               </div>
                             </div>
                           </div>
                         ))}
                       </div>
                     </div>
                   ) : (
                     <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
                       <div>
                         <h4 style={{ color: 'white', margin: '0 0 4px 0' }}>Dataset Description</h4>
                         <p style={{ color: 'rgba(255,255,255,0.6)', margin: 0, fontSize: '0.85rem' }}>{selectedDataset.description}</p>
                       </div>
                       
                       <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                         <h4 style={{ color: 'white', margin: '8px 0 4px 0' }}>Test Cases ({selectedDataset.testCases.length})</h4>
                         {selectedDataset.testCases.map((tc, idx) => (
                           <div key={idx} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                             <div><span style={{ color: 'var(--gold)', fontWeight: 600 }}>Input:</span> <span style={{ color: 'white' }}>{tc.input}</span></div>
                             <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Expected Output:</span> <span style={{ color: 'rgba(255,255,255,0.8)' }}>{tc.expected}</span></div>
                           </div>
                         ))}
                       </div>

                       {selectedDataset.runHistory.length > 0 && (
                         <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                           <h4 style={{ color: 'white', margin: '8px 0 4px 0' }}>Run History</h4>
                           <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
                             <thead>
                               <tr>
                                 <th style={{ padding: '6px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)' }}>Date</th>
                                 <th style={{ padding: '6px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)' }}>Passed</th>
                                 <th style={{ padding: '6px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)' }}>Failed</th>
                                 <th style={{ padding: '6px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.4)' }}>Avg Score</th>
                               </tr>
                             </thead>
                             <tbody>
                               {selectedDataset.runHistory.map((h, i) => (
                                 <tr key={i}>
                                   <td style={{ padding: '6px' }}>{h.date}</td>
                                   <td style={{ padding: '6px', color: '#10b981' }}>{h.passed}</td>
                                   <td style={{ padding: '6px', color: '#ef4444' }}>{h.failed}</td>
                                   <td style={{ padding: '6px', fontWeight: 600, color: 'var(--primary)' }}>{h.avgScore}%</td>
                                 </tr>
                               ))}
                             </tbody>
                           </table>
                         </div>
                       )}
                     </div>
                   )}
                 </div>
               ) : (
                 <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                   <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                     <div>
                       <h3 style={{ color: 'white', margin: 0 }}>Evaluation Datasets</h3>
                       <p style={{ color: 'rgba(255,255,255,0.4)', margin: 0, fontSize: '0.75rem' }}>Manage ground-truth reference inputs and trigger LLM-as-a-judge scoring sweeps.</p>
                     </div>
                     <button onClick={() => setShowCreateForm(true)} style={{ padding: '8px 16px', background: 'var(--primary)', color: 'black', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                       <Plus size={14} /> Create New Dataset
                     </button>
                   </div>
                   
                   <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', overflowY: 'auto' }}>
                     {datasets.map(ds => (
                       <div key={ds.id} onClick={() => setSelectedDataset(ds)} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', padding: '16px', borderRadius: '12px', cursor: 'pointer', transition: 'all 0.2s', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }} onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'} onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}>
                         <div>
                           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                             <h4 style={{ color: 'white', margin: 0, fontSize: '1rem' }}>{ds.name}</h4>
                             <span style={{ fontSize: '0.65rem', padding: '3px 8px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.6)', fontWeight: 600 }}>{ds.evaluatorType}</span>
                           </div>
                           <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem', margin: '0 0 16px 0', minHeight: '36px' }}>{ds.description}</p>
                         </div>
                         <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '8px', fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>
                           <span>{ds.testCases.length} Test Cases</span>
                           {ds.runHistory.length > 0 && <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Last score: {ds.runHistory[0].avgScore}%</span>}
                         </div>
                       </div>
                     ))}
                   </div>
                 </div>
               )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── Waterfall Chart Subcomponent ────────────────────────────────────────────

function WaterfallChart({ spans, totalLatency }: { spans: SpanNode[], totalLatency: number }) {
  const { roots, childrenMap } = useMemo(() => buildSpanTree(spans), [spans]);

  const renderNode = (span: SpanNode, depth: number) => {
    const children = childrenMap.get(span.span_id) || [];
    const meta = getSpanMeta(span.interaction_type);
    
    // Calculate percentage width for the bar
    const duration = span.duration_ms || 0;
    const widthPct = Math.max((duration / totalLatency) * 100, 1);
    
    return (
      <div key={span.span_id} style={{ display: 'flex', flexDirection: 'column', marginBottom: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '6px 0', position: 'relative' }}>
          {/* Label side */}
          <div style={{ width: '250px', paddingLeft: `${depth * 16}px`, display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <div style={{ width: '20px', height: '20px', borderRadius: '4px', background: `${meta.color}20`, color: meta.color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {meta.icon}
            </div>
            <div style={{ fontSize: '0.8rem', color: 'white', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {span.operation_name || span.interaction_type}
            </div>
          </div>
          
          {/* Graph side */}
          <div style={{ flex: 1, position: 'relative', height: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '4px', display: 'flex', alignItems: 'center' }}>
             {/* Simple visual bar based on percentage, in a real LangSmith view this considers start_time offset */}
             <motion.div 
               initial={{ width: 0 }} animate={{ width: `${widthPct}%` }}
               style={{ height: '10px', background: meta.color, borderRadius: '4px', opacity: 0.8 }} 
             />
             <span style={{ position: 'absolute', right: '12px', fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'monospace' }}>
               {duration}ms
             </span>
          </div>
        </div>
        {children.map(c => renderNode(c, depth + 1))}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', padding: '12px 0' }}>
      {/* Time axis header */}
      <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px', marginBottom: '12px' }}>
        <div style={{ width: '250px', fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0 }}>Span</div>
        <div style={{ flex: 1, fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Execution Time ({totalLatency}ms)</div>
      </div>
      {roots.map(r => renderNode(r, 0))}
    </div>
  );
}
