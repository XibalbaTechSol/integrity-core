import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { BrainCircuit, Wrench, FileEdit, AlertTriangle, ShieldCheck, Activity, ChevronDown, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { oracle } from '../../services/oracle';
import { useDashboard } from '../../context/useDashboard';

const MOCK_TRAJECTORIES = [
  {
    id: 'traj_01',
    intent: 'Analyze and summarize patient blood test results.',
    status: 'Validating',
    score: 950,
    steps: [
      { id: 's1', type: 'thought', message: 'I need to retrieve the blood test document and parse the CBC values.', time: '10:02:45' },
      { id: 's2', type: 'tool', name: 'read_document', args: '{ doc_id: "lab_0991" }', time: '10:02:46' },
      { id: 's3', type: 'mutation', file: '/tmp/analysis_buffer.txt', diff: '+ High WBC count detected', time: '10:02:48' },
      { id: 's4', type: 'thought', message: 'Values extracted successfully. Now summarizing for the physician.', time: '10:02:49' }
    ]
  }
];

function HierarchicalStepNode({ step, idx }: { step: any; idx: number }) {
  const [isOpen, setIsOpen] = useState(false);

  // Determine children nodes based on step type
  const children = [];
  if (step.type === 'tool' || step.event_type === 'tool_call') {
    children.push({
      id: `${step.id || idx}-name`,
      label: 'Tool Method',
      value: step.name || step.tool_name,
      accent: 'var(--gold)',
    });
    if (step.args || step.arguments) {
      children.push({
        id: `${step.id || idx}-args`,
        label: 'Arguments',
        value: typeof step.args === 'string' ? step.args : JSON.stringify(step.args || step.arguments, null, 2),
        isMono: true,
      });
    }
  } else if (step.type === 'mutation' || step.event_type === 'file_mutation') {
    children.push({
      id: `${step.id || idx}-file`,
      label: 'Target Resource',
      value: step.file || step.file_path,
      accent: 'var(--info)',
    });
    if (step.diff) {
      children.push({
        id: `${step.id || idx}-diff`,
        label: 'Diff Output',
        value: step.diff,
        isMono: true,
        accent: 'var(--success)',
      });
    }
  } else if (step.type === 'thought' || step.event_type === 'thought') {
    if (step.message && step.message.length > 80) {
      children.push({
        id: `${step.id || idx}-detail`,
        label: 'Detailed Cognition Trace',
        value: step.message,
      });
    }
  } else if (step.type === 'alert' || step.event_type === 'error') {
    children.push({
      id: `${step.id || idx}-err`,
      label: 'Error Signature',
      value: step.message || step.error,
      accent: 'var(--danger)',
    });
  }

  const hasChildren = children.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div 
        onClick={() => hasChildren && setIsOpen(!isOpen)}
        style={{
          padding: '12px',
          background: 'var(--bg-primary)',
          borderLeft: `3px solid ${
            step.type === 'thought' || step.event_type === 'thought' ? 'var(--accent)' :
            step.type === 'tool' || step.event_type === 'tool_call' ? 'var(--gold)' :
            step.type === 'mutation' || step.event_type === 'file_mutation' ? 'var(--info)' : 'var(--danger)'
          }`,
          borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
          fontSize: '0.875rem',
          cursor: hasChildren ? 'pointer' : 'default',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          transition: 'background 0.2s',
        }}
        onMouseEnter={e => { if (hasChildren) e.currentTarget.style.background = 'var(--surface-hover)'; }}
        onMouseLeave={e => { if (hasChildren) e.currentTarget.style.background = 'var(--bg-primary)'; }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="flex justify-between" style={{ marginBottom: '6px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            <span className="flex items-center" style={{ gap: '6px', textTransform: 'uppercase' }}>
              {(step.type === 'thought' || step.event_type === 'thought') && <BrainCircuit size={12} />}
              {(step.type === 'tool' || step.event_type === 'tool_call') && <Wrench size={12} />}
              {(step.type === 'mutation' || step.event_type === 'file_mutation') && <FileEdit size={12} />}
              {(step.type === 'alert' || step.event_type === 'error') && <AlertTriangle size={12} />}
              {step.type || step.event_type}
            </span>
            <span>{step.time || new Date(step.timestamp * 1000).toLocaleTimeString()}</span>
          </div>
          
          <div style={{ color: 'var(--text-primary)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {step.type === 'thought' || step.event_type === 'thought'
              ? step.message
              : step.type === 'tool' || step.event_type === 'tool_call'
              ? `Executed ${step.name || step.tool_name}`
              : step.type === 'mutation' || step.event_type === 'file_mutation'
              ? `Mutated file: ${step.file || step.file_path}`
              : step.message || step.error
            }
          </div>
        </div>
        {hasChildren && (
          <div style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>
            {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </div>
        )}
      </div>

      <AnimatePresence>
        {isOpen && hasChildren && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{
              overflow: 'hidden',
              paddingLeft: '16px',
              borderLeft: '1px dashed var(--glass-border)',
              marginLeft: '8px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              marginTop: '4px',
            }}
          >
            {children.map(child => (
              <div 
                key={child.id}
                style={{
                  padding: '8px 12px',
                  background: 'rgba(255,255,255,0.01)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid rgba(255,255,255,0.02)',
                  fontSize: '0.8rem',
                }}
              >
                <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: '2px' }}>
                  {child.label}
                </div>
                <div style={{ 
                  color: child.accent || 'var(--text-primary)', 
                  fontFamily: child.isMono ? 'monospace' : 'inherit',
                  whiteSpace: child.isMono ? 'pre-wrap' : 'normal',
                  wordBreak: 'break-all'
                }}>
                  {child.value}
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function TrajectoryPanel() {
  const { selectedAgent } = useDashboard();
  const [trajectories, setTrajectories] = useState<any[]>(MOCK_TRAJECTORIES);
  const [activeTraj, setActiveTraj] = useState<any>(MOCK_TRAJECTORIES[0]);

  // Filter trajectories for the selected agent
  const filteredTrajectories = selectedAgent
    ? trajectories.filter(t => 
        t.agent_address?.toLowerCase() === selectedAgent.eth_address?.toLowerCase() || 
        t.agent_id === selectedAgent.agent_id ||
        t.agent_id === selectedAgent.alias
      )
    : trajectories;

  const displayTrajectories = filteredTrajectories.length > 0 ? filteredTrajectories : [
    {
      id: `traj_${selectedAgent?.eth_address?.substring(0, 6) || 'sys'}_03`,
      intent: selectedAgent?.alias?.toLowerCase().includes('xibalba') 
        ? 'Orchestrate global deployment and analyze cross-chain state.' 
        : 'Analyze and summarize telemetry data streams.',
      status: 'Validating',
      score: selectedAgent?.current_ais || 950,
      steps: [
        { id: 's1', type: 'thought', message: `Initializing operational matrix for agent ${selectedAgent?.alias || 'Unknown'}.`, time: new Date(Date.now() - 4000).toLocaleTimeString() },
        { id: 's2', type: 'tool', name: 'fetch_state', args: '{ target: "oracle_node_1" }', time: new Date(Date.now() - 3000).toLocaleTimeString() },
        { id: 's3', type: 'mutation', file: '/var/log/integrity.log', diff: '+ Synchronization complete.', time: new Date(Date.now() - 2000).toLocaleTimeString() },
        { id: 's4', type: 'thought', message: 'State verified. Proceeding with execution pipeline.', time: new Date(Date.now() - 1000).toLocaleTimeString() }
      ]
    },
    {
      id: `traj_${selectedAgent?.eth_address?.substring(0, 6) || 'sys'}_02`,
      intent: selectedAgent?.alias?.toLowerCase().includes('xibalba') 
        ? 'Run quant trading backtest strategy against Base Sepolia orderbook.' 
        : 'Perform adversarial evaluation on newly deployed SLA contract.',
      status: 'Passed',
      score: selectedAgent?.current_ais ? selectedAgent.current_ais - 5 : 945,
      steps: [
        { id: 's1', type: 'thought', message: `Loading market data / contract ABI for target.`, time: new Date(Date.now() - 14000).toLocaleTimeString() },
        { id: 's2', type: 'tool', name: 'query_orderbook', args: '{ pair: "ITK/USDC" }', time: new Date(Date.now() - 13000).toLocaleTimeString() },
        { id: 's3', type: 'thought', message: 'Data fetched. Analyzing liquidity depth...', time: new Date(Date.now() - 11000).toLocaleTimeString() },
        { id: 's4', type: 'tool', name: 'execute_trade', args: '{ amount: "10000 ITK", type: "limit" }', time: new Date(Date.now() - 10000).toLocaleTimeString() },
        { id: 's5', type: 'mutation', file: 'portfolio_state.json', diff: '+ 10,000 ITK allocated to strategy.', time: new Date(Date.now() - 8000).toLocaleTimeString() },
      ]
    },
    {
      id: `traj_${selectedAgent?.eth_address?.substring(0, 6) || 'sys'}_01`,
      intent: selectedAgent?.alias?.toLowerCase().includes('xibalba') 
        ? 'Detect anomalies in Shield BAA compliance logs.' 
        : 'Optimize gas usage for on-chain identity verification.',
      status: 'Passed',
      score: selectedAgent?.current_ais ? selectedAgent.current_ais + 2 : 952,
      steps: [
        { id: 's1', type: 'thought', message: `Scanning recent transaction telemetry...`, time: new Date(Date.now() - 25000).toLocaleTimeString() },
        { id: 's2', type: 'tool', name: 'read_logs', args: '{ limit: 100 }', time: new Date(Date.now() - 24000).toLocaleTimeString() },
        { id: 's3', type: 'alert', message: 'Minor deviation detected in gas bounds.', time: new Date(Date.now() - 22000).toLocaleTimeString() },
        { id: 's4', type: 'thought', message: 'Adjusting parameters to maintain SLA.', time: new Date(Date.now() - 20000).toLocaleTimeString() },
        { id: 's5', type: 'mutation', file: 'config/bounds.json', diff: '~ gas_limit: 50000 -> 48000', time: new Date(Date.now() - 18000).toLocaleTimeString() },
      ]
    }
  ];

  // Auto-select the first matching trajectory when activeTraj is not in the filtered list
  useEffect(() => {
    if (displayTrajectories.length > 0) {
      const activeStillValid = displayTrajectories.some(t => t.id === activeTraj?.id);
      if (!activeStillValid) {
        setActiveTraj(displayTrajectories[0]);
      }
    }
  }, [selectedAgent, trajectories]);

  useEffect(() => {
    // Real trajectories = the selected agent's OTel traces (getRecentTraces), each trace's
    // span tree (getTraceTree) becoming its reasoning steps. The reasoning-content telemetry
    // the old /v1/telemetry/latest expected doesn't exist on the oracle; spans are the real
    // structural trajectory.
    const mapStepType = (n: string) => {
      const s = (n || '').toLowerCase();
      if (s.includes('tool')) return 'tool';
      if (s.includes('bcc') || s.includes('anchor') || s.includes('mutation')) return 'mutation';
      if (s.includes('policy') || s.includes('api') || s.includes('retrieve')) return 'api';
      return 'thought';
    };
    const fetchTrajectories = async () => {
      if (!selectedAgent) { setTrajectories([]); return; }
      try {
        const recent = await oracle.getRecentTraces(selectedAgent.eth_address, 12);
        const mapped = await Promise.all(recent.map(async (t) => {
          let steps: any[] = [];
          try {
            const tree: any = await oracle.getTraceTree(t.trace_id);
            const flat: any[] = [];
            const walk = (nodes: any[]) => { for (const nd of nodes || []) { flat.push(nd); if (nd.children?.length) walk(nd.children); } };
            walk(tree.roots || []);
            steps = flat.map((s) => ({ id: s.span_id, type: mapStepType(s.name), message: s.name, time: new Date(s.start_time).toLocaleTimeString() }));
          } catch { /* leave steps empty */ }
          return {
            id: t.trace_id.slice(0, 12),
            intent: t.name,
            status: 'Passed',
            score: Math.round(selectedAgent.current_ais || 0),
            agent_id: selectedAgent.agent_id,
            agent_address: selectedAgent.eth_address,
            steps,
            issue: null,
            raw: t,
          };
        }));
        setTrajectories(mapped);
      } catch (err) {
        console.error("Failed to fetch live trajectories", err);
      }
    };
    fetchTrajectories();
    const interval = setInterval(fetchTrajectories, 5000);
    return () => clearInterval(interval);
  }, [selectedAgent]);

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-3" style={{ gap: 'var(--space-6)' }}>
        
        {/* Left Column: Trajectory List */}
        <div className="flex-col gap-6">
          <Panel title="Active Intent Trajectories" icon={<BrainCircuit size={18} />}>
            <div className="flex-col gap-3">
              {displayTrajectories.map((traj) => (
                <div 
                  key={traj.id}
                  onClick={() => setActiveTraj(traj)}
                  style={{
                    padding: 'var(--space-3)',
                    background: activeTraj?.id === traj.id ? 'var(--bg-secondary)' : 'transparent',
                    border: `1px solid ${activeTraj?.id === traj.id ? 'var(--gold)' : 'var(--glass-border)'}`,
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                >
                  <div className="flex justify-between" style={{ marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{traj.id}</span>
                    <span style={{ fontSize: '0.75rem', color: traj.status === 'Drift Detected' ? 'var(--danger)' : 'var(--success)' }}>
                      {traj.status}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 500, lineHeight: 1.4 }}>
                    {traj.intent}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          
          <Panel title="BCC Evaluation Score" icon={<ShieldCheck size={18} />}>
            <div style={{ textAlign: 'center', padding: 'var(--space-4) 0' }}>
              <div style={{ 
                fontSize: '3rem', 
                fontFamily: 'serif', 
                color: (activeTraj?.score || 0) > 800 ? 'var(--success)' : 'var(--danger)',
                textShadow: '0 0 20px rgba(var(--gold-rgb), 0.2)'
              }}>
                {activeTraj?.score || 0}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '8px' }}>
                Alignment Integrity Score (AIS)
              </div>
            </div>
          </Panel>
        </div>

        {/* Right Column: Thought Trace */}
        <div className="col-span-2 flex-col gap-6">
          <Panel title="Live Agent Cognition & Telemetry Trace" icon={<Activity size={18} />}>
            <div style={{ 
              background: 'rgba(0,0,0,0.4)', 
              borderRadius: 'var(--radius-md)', 
              padding: 'var(--space-4)',
              minHeight: '400px',
              fontFamily: 'monospace',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              <AnimatePresence mode="wait">
                {activeTraj && (
                <motion.div
                  key={activeTraj.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
                >
                  <div style={{ padding: '16px', background: 'rgba(212,175,55,0.05)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(212,175,55,0.2)', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div>
                        <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--gold)', letterSpacing: '0.1em', fontWeight: 800 }}>Primary Intent</span>
                        <div style={{ fontSize: '1rem', color: 'var(--text-primary)', marginTop: '4px' }}>{activeTraj.intent}</div>
                      </div>
                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '12px' }}>
                        <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: activeTraj.score > 800 ? 'var(--success)' : 'var(--danger)', letterSpacing: '0.1em', fontWeight: 800 }}>Actual Outcome</span>
                        <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                          {activeTraj.status === 'Passed' ? 'Successfully Executed & Verified' : activeTraj.status} (AIS: {activeTraj.score})
                        </div>
                        {activeTraj.status !== 'Passed' && activeTraj.status !== 'Validating' && (
                           <div style={{ marginTop: '12px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--radius-sm)' }}>
                             <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--danger)', letterSpacing: '0.1em', fontWeight: 800, marginBottom: '6px' }}><AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px' }} /> Failure Diagnostics</div>
                             <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                               {activeTraj.issue || 'Diagnostic telemetry indicates deviation from established SLA bounds. Manual audit recommended.'}
                             </div>
                             <div style={{ marginTop: '8px' }}>
                               <button className="btn btn-outline" onClick={() => alert("Raw Telemetry Trace (Mock):\n\n" + JSON.stringify(activeTraj.raw || {}, null, 2))} style={{ fontSize: '0.7rem', padding: '6px 12px', border: '1px solid rgba(239,68,68,0.5)', color: 'var(--danger)', background: 'transparent', borderRadius: '4px', cursor: 'pointer' }}>View Raw Stack Trace</button>
                             </div>
                           </div>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', borderBottom: '1px solid var(--glass-border)', paddingBottom: '8px', marginBottom: '8px' }}>Timestamped Execution History (Expand to explore details)</div>
                  {(activeTraj.steps || []).map((step: any, idx: number) => (
                    <HierarchicalStepNode key={step.id || idx} step={step} idx={idx} />
                  ))}
                </motion.div>
                )}
              </AnimatePresence>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
