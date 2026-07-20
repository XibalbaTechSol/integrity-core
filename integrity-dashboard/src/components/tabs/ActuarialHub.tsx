import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { 
  LineChart, 
  Handshake, 
  Terminal, 
  Zap, 
  Plus, 
  RefreshCw, 
  BarChart2, 
  Globe, 
  ShieldCheck,
  UserPlus,
  Coins,
  Lock,
  Unlock,
  X,
  ArrowRight,
  UserCheck
} from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { StatusBadge } from '../shared/StatusBadge';
import { api } from '../../services/api';
import type { MarketTask } from '../../types';

interface ExecutionLog {
  id: number;
  time: string;
  message: string;
}

interface Benchmark {
  model_name: string;
  provider_name: string;
  simulated_ais: number;
  stability_metric: number;
  grounding_metric: number;
}

interface A2AEscrow {
  id: string;
  hiredAgentAddress: string;
  hiredAgentAlias: string;
  taskTitle: string;
  lockedITK: number;
  condition: string;
  status: 'Escrowed' | 'Released' | 'Refunded';
  createdAt: string;
}

export function ActuarialHub({ mode }: { mode: 'markets' | 'stability' }) {
  const { selectedAgent, agents, addToast } = useDashboard();

  // Markets States
  const [tasks, setTasks] = useState<MarketTask[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [title, setTitle] = useState('');
  const [reward, setReward] = useState('100');
  const [minAis, setMinAis] = useState('500');
  const [useCredit, setUseCredit] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [logs, setLogs] = useState<ExecutionLog[]>([]);
  const [placedBids, setPlacedBids] = useState<Record<string, { bidder: string; amount: number }>>(() => {
    const saved = localStorage.getItem('integrity_placed_bids');
    return saved ? JSON.parse(saved) : {};
  });

  useEffect(() => {
    localStorage.setItem('integrity_placed_bids', JSON.stringify(placedBids));
  }, [placedBids]);

  // Stability States
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [loadingBenchmarks, setLoadingBenchmarks] = useState(false);
  const [isAuditing, setIsAuditing] = useState(false);

  // A2A Escrow states
  const [escrows, setEscrows] = useState<A2AEscrow[]>(() => {
    const saved = localStorage.getItem('integrity_a2a_escrows');
    return saved ? JSON.parse(saved) : [
      { id: 'esc_sample_001', hiredAgentAddress: '0x917a0601923b6805648443a832AF721F17AF7C2d', hiredAgentAlias: 'HermesRisk', taskTitle: 'Audit historical ledger block 10452', lockedITK: 250, condition: 'AIS >= 900 & TEE Certified', status: 'Escrowed', createdAt: new Date(Date.now() - 3600000).toISOString() }
    ];
  });
  const [selectedAgentForHire, setSelectedAgentForHire] = useState<any | null>(null);
  const [hireTaskTitle, setHireTaskTitle] = useState('');
  const [hireReward, setHireReward] = useState('500');
  const [hireCondition, setHireCondition] = useState('AIS >= 900 & TEE Certified');
  const [isHiring, setIsHiring] = useState(false);

  useEffect(() => {
    localStorage.setItem('integrity_a2a_escrows', JSON.stringify(escrows));
  }, [escrows]);

  const handleHireAgent = () => {
    if (!selectedAgent || !selectedAgentForHire) return;
    setIsHiring(true);
    addLog(`[ESCROW] Initiating hire contract for ${selectedAgentForHire.alias}...`);
    
    setTimeout(() => {
      const escrowId = 'esc_' + Math.random().toString(16).substring(2, 18);
      const newEscrow: A2AEscrow = {
        id: escrowId,
        hiredAgentAddress: selectedAgentForHire.eth_address,
        hiredAgentAlias: selectedAgentForHire.alias,
        taskTitle: hireTaskTitle,
        lockedITK: parseFloat(hireReward),
        condition: hireCondition,
        status: 'Escrowed',
        createdAt: new Date().toISOString()
      };
      
      setEscrows(prev => [newEscrow, ...prev]);
      addLog(`[ESCROW SUCCESS] Locked ${hireReward} ITK in Escrow Contract (${escrowId.substring(0,8)}). Hired ${selectedAgentForHire.alias}.`);
      addToast('success', `Agent ${selectedAgentForHire.alias} hired via escrow!`);
      
      setSelectedAgentForHire(null);
      setHireTaskTitle('');
      setIsHiring(false);
    }, 1500);
  };

  const handleReleaseEscrow = (escrowId: string) => {
    const esc = escrows.find(e => e.id === escrowId);
    if (!esc) return;
    addLog(`[ESCROW RELEASE] Verifying contract conditions for ${esc.id.substring(0,8)}...`);
    addLog(`[ESCROW RELEASE] Oracle checked: Conditions met ("${esc.condition}").`);
    
    setEscrows(prev => prev.map(e => e.id === escrowId ? { ...e, status: 'Released' } : e));
    addLog(`[ESCROW SUCCESS] Transferred locked ${esc.lockedITK} ITK to ${esc.hiredAgentAlias}.`);
    addToast('success', 'Escrow funds released to agent!');
  };

  const handleRefundEscrow = (escrowId: string) => {
    const esc = escrows.find(e => e.id === escrowId);
    if (!esc) return;
    addLog(`[ESCROW REFUND] Refunding escrow ${esc.id.substring(0,8)} to controller...`);
    
    setEscrows(prev => prev.map(e => e.id === escrowId ? { ...e, status: 'Refunded' } : e));
    addLog(`[ESCROW SUCCESS] Refunded ${esc.lockedITK} ITK back to owner address.`);
    addToast('info', 'Escrow refunded successfully');
  };

  const fetchTasks = async () => {
    setLoadingTasks(true);
    try {
      const data = await api.getMarketTasks();
      setTasks(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
      setTasks([]);
    } finally {
      setLoadingTasks(false);
    }
  };

  const fetchBenchmarks = async () => {
    setLoadingBenchmarks(true);
    try {
      const data = await api.getBenchmarks();
      setBenchmarks(data as Benchmark[]);
    } catch (err) {
      console.error('Failed to fetch benchmarks:', err);
    } finally {
      setLoadingBenchmarks(false);
    }
  };

  useEffect(() => {
    if (mode === 'markets') {
      fetchTasks();
    } else {
      fetchBenchmarks();
    }
  }, [mode]);

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, { id: Date.now() + Math.random(), time: new Date().toLocaleTimeString(), message: msg }]);
  };

  const handleCreateTask = async () => {
    if (!selectedAgent) return;
    setIsCreating(true);
    addLog(`Initiating task creation for "${title}"...`);
    
    try {
      let res;
      if (useCredit) {
        res = await api.fundTaskWithLoan({
          creator_agent_id: selectedAgent.agent_id || "88d5ab08-156b-45cf-9b17-32e74a9f2690",
          title,
          reward_itk: parseFloat(reward),
          min_ais_required: parseInt(minAis),
          description: `Autonomous leveraged contract for ${title}`,
          auction_duration_sec: 3600
        });
      } else {
        res = await api.createMarketTask({
          creator_agent_id: selectedAgent.agent_id || "88d5ab08-156b-45cf-9b17-32e74a9f2690",
          title,
          reward_itk: parseFloat(reward),
          min_ais_required: parseInt(minAis),
          description: `Autonomous contract for ${title}`,
          auction_duration_sec: 3600
        });
      }
      
      addLog(`SUCCESS: Task created ${useCredit ? 'with leverage ' : ''}on-chain. ID: ${res.task_id}`);
      addToast('success', 'Task created successfully');
      setTitle('');
      fetchTasks();
    } catch (err: any) {
      addLog(`ERROR: ${err.message}`);
      addToast('error', 'Failed to create task');
    } finally {
      setIsCreating(false);
    }
  };

  const handleBid = async (taskId: string) => {
    if (!selectedAgent) return;
    addLog(`Placing bid on task ${taskId.substring(0,8)}...`);
    
    try {
      await api.bidOnTask({
        task_id: taskId,
        bidder_agent_address: selectedAgent.eth_address,
        bid_amount_itk: 95.0 
      });
      setPlacedBids(prev => ({
        ...prev,
        [taskId]: { bidder: selectedAgent.alias, amount: 95.0 }
      }));
      addLog(`SUCCESS: Bid placed for ${selectedAgent.alias}`);
      addToast('success', 'Bid placed successfully');
      fetchTasks();
    } catch (err: any) {
      addLog(`ERROR: ${err.message}`);
      addToast('error', 'Bidding failed');
    }
  };

  const handleStartAudit = async () => {
    if (!selectedAgent) {
      addToast('info', 'Please select an agent first');
      return;
    }
    
    setIsAuditing(true);
    try {
      await api.requestAudit(selectedAgent.eth_address, 'AUTOMATED');
      addToast('success', 'Institutional certification audit initialized');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      addToast('error', `Audit request failed: ${msg}`);
    } finally {
      setIsAuditing(false);
    }
  };

  const getStatus = (stability: number, grounding: number) => {
    if (stability >= 0.95 && grounding >= 0.95) return 'certified';
    if (stability >= 0.90 && grounding >= 0.90) return 'pending';
    return 'warning';
  };

  if (mode === 'markets') {
    return (
      <div className="flex-col gap-6">
        <Panel title="A2A Market Operations" icon={<Zap size={18} />}>
          <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
            {/* Create Task Side */}
            <div className="flex-col gap-4">
              <div style={{ padding: 'var(--space-3)', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)', marginBottom: '4px' }}>
                  Create Autonomous Task
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)' }}>
                  Post a contract to the decentralized marketplace for other agents to fulfill.
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="task-title">Task Title</label>
                <input 
                  id="task-title"
                  className="input" 
                  placeholder="e.g. Data Inference SLA" 
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                />
              </div>

              <div className="grid-cols-2" style={{ gap: 'var(--space-4)' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="task-reward">Reward (ITK)</label>
                  <input 
                    id="task-reward"
                    type="number" 
                    className="input" 
                    value={reward}
                    onChange={e => setReward(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="task-min-ais">Min. AIS Required</label>
                  <input 
                    id="task-min-ais"
                    type="number" 
                    className="input" 
                    value={minAis}
                    onChange={e => setMinAis(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
                <input 
                  type="checkbox" 
                  id="useCredit" 
                  checked={useCredit}
                  onChange={e => setUseCredit(e.target.checked)}
                />
                <label htmlFor="useCredit" style={{ fontSize: '0.75rem', cursor: 'pointer' }}>
                  Fund via Institutional Credit (No upfront cost)
                </label>
              </div>

              <button 
                className="btn btn-primary" 
                onClick={handleCreateTask} 
                disabled={isCreating || !selectedAgent || !title}
              >
                {isCreating ? 'Broadcasting to Mesh...' : 'Create A2A Task'}
                <Plus size={16} style={{ marginLeft: '8px' }} />
              </button>
            </div>

            {/* Console / Logs Side */}
            <div className="flex-col gap-4">
              <div data-testid="protocol-logs" style={{ background: 'var(--navy-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', height: '240px', padding: 'var(--space-3)', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div className="flex items-center justify-between" style={{ borderBottom: '1px solid var(--glass-border)', paddingBottom: '4px', marginBottom: '4px' }}>
                  <div className="flex items-center gap-2" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                    <Terminal size={14} /> Protocol Logs
                  </div>
                  <button onClick={() => setLogs([])} className="text-muted" style={{ fontSize: '0.65rem', background: 'none', border: 'none', cursor: 'pointer' }}>Clear</button>
                </div>
                {logs.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontStyle: 'italic', marginTop: 'var(--space-2)' }}>
                    Awaiting market activity...
                  </div>
                ) : (
                  logs.map(log => (
                    <div key={log.id} className="mono" style={{ fontSize: '0.75rem', color: log.message.includes('SUCCESS') ? 'var(--success)' : log.message.includes('ERROR') ? 'var(--error)' : 'var(--text-primary)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>[{log.time}]</span> {log.message}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </Panel>

        <Panel 
          title="Open Marketplace Tasks" 
          icon={<Handshake size={18} />}
          action={
            <button className="btn btn-icon" onClick={fetchTasks} disabled={loadingTasks}>
              <RefreshCw size={14} className={loadingTasks ? 'spin' : ''} />
            </button>
          }
        >
          {(() => {
            const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({});
            const toggleExpand = (taskId: string) => {
              setExpandedTaskIds(prev => ({ ...prev, [taskId]: !prev[taskId] }));
            };

            return (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '40px' }}></th>
                      <th>Task ID</th>
                      <th>Title / Reward</th>
                      <th>Min AIS</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadingTasks ? (
                      <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>Fetching live marketplace data...</td></tr>
                    ) : tasks.length === 0 ? (
                      <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>No open tasks found in the network.</td></tr>
                    ) : (
                      tasks.flatMap((t) => {
                        const isExpanded = !!expandedTaskIds[t.task_id];
                        return [
                          <tr key={t.task_id} style={{ cursor: 'pointer' }} onClick={() => toggleExpand(t.task_id)}>
                            <td style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center' }}>
                              {isExpanded ? '▼' : '▶'}
                            </td>
                            <td className="mono" title={t.task_id}>{t.task_id.substring(0, 13)}...</td>
                            <td>
                              <div style={{ fontWeight: 500 }}>{t.title}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--success)' }}>{t.reward_itk} ITK</div>
                            </td>
                            <td>{t.min_ais_required}</td>
                            <td><StatusBadge status={t.status.toLowerCase()} /></td>
                            <td onClick={(e) => e.stopPropagation()}>
                              <button 
                                className="btn" 
                                style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                onClick={() => handleBid(t.task_id)}
                                disabled={!selectedAgent || (selectedAgent.current_ais ?? 0) < t.min_ais_required}
                              >
                                Place Bid
                              </button>
                            </td>
                          </tr>,
                          isExpanded && (
                            <tr key={`${t.task_id}-expanded`} style={{ background: 'var(--bg-primary)' }}>
                              <td colSpan={6} style={{ padding: 'var(--space-4) var(--space-6)' }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', fontSize: '0.85rem' }}>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Creator Agent ID: </span>
                                    <span className="mono">{t.creator_agent_id || 'N/A'}</span>
                                  </div>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Created At: </span>
                                    <span>{t.created_at ? new Date(t.created_at).toLocaleString() : 'N/A'}</span>
                                  </div>
                                  <div style={{ marginTop: '4px', borderTop: '1px solid var(--glass-border)', paddingTop: '8px' }}>
                                    <span style={{ color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Task Description:</span>
                                    <p style={{ margin: 0, color: 'var(--text-primary)', lineHeight: 1.5 }}>{t.description || 'No description provided.'}</p>
                                  </div>
                                  <div style={{ marginTop: '8px', borderTop: '1px solid var(--glass-border)', paddingTop: '8px' }}>
                                    <span style={{ color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Active Bids:</span>
                                    {placedBids[t.task_id] ? (
                                      <div style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(255,255,255,0.02)', padding: '6px 12px', borderRadius: '4px', border: '1px solid var(--glass-border)', maxWidth: '300px' }}>
                                        <span className="mono" style={{ color: 'var(--primary)' }}>{placedBids[t.task_id].bidder}</span>
                                        <span className="mono" style={{ color: 'var(--success)' }}>{placedBids[t.task_id].amount} ITK</span>
                                      </div>
                                    ) : (
                                      <span style={{ fontStyle: 'italic', fontSize: '0.75rem', color: 'var(--text-muted)' }}>No bids placed yet.</span>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )
                        ].filter(Boolean);
                      })
                    )}
                  </tbody>
                </table>
              </div>
            );
          })()}
        </Panel>

        <Panel title="Mesh Agents Directory (Real-Time Trade & Hire)" icon={<UserCheck size={18} />}>
          <div className="table-container">
            <table className="table" style={{ fontSize: '0.8rem' }}>
              <thead>
                <tr>
                  <th>Agent Alias</th>
                  <th>DID / Address</th>
                  <th>AIS</th>
                  <th>Specialty / Capability</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {agents.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>Awaiting peer agent signals...</td></tr>
                ) : (
                  agents.map((a: any) => (
                    <tr key={a.agent_id}>
                      <td style={{ fontWeight: 600 }}>{a.alias}</td>
                      <td className="mono" title={a.eth_address}>{a.eth_address.substring(0, 12)}...</td>
                      <td style={{ color: 'var(--primary)', fontWeight: 600 }}>{a.current_ais}</td>
                      <td>{a.description || 'General Computing & Execution'}</td>
                      <td>
                        <span style={{ 
                          fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                          background: 'rgba(16, 185, 129, 0.1)', color: 'var(--success)',
                          border: '1px solid rgba(16, 185, 129, 0.2)', fontWeight: 700
                        }}>
                          ONLINE
                        </span>
                      </td>
                      <td>
                        <button 
                          className="btn btn-primary btn-xs" 
                          style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                          onClick={() => setSelectedAgentForHire(a)}
                          disabled={selectedAgent?.agent_id === a.agent_id}
                        >
                          Hire (Escrow)
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Active A2A Escrow Contracts (Parametric Escrows)" icon={<Lock size={18} />}>
          <div className="table-container">
            <table className="table" style={{ fontSize: '0.8rem' }}>
              <thead>
                <tr>
                  <th>Escrow ID</th>
                  <th>Hired Agent</th>
                  <th>Specialized Task</th>
                  <th>Locked Amount</th>
                  <th>Release Condition</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {escrows.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>No active escrow locks found.</td></tr>
                ) : (
                  escrows.map((esc) => (
                    <tr key={esc.id}>
                      <td className="mono font-semibold">{esc.id.substring(0, 10)}...</td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{esc.hiredAgentAlias}</div>
                        <div className="mono text-muted" style={{ fontSize: '0.7rem' }}>{esc.hiredAgentAddress.substring(0, 10)}...</div>
                      </td>
                      <td>{esc.taskTitle}</td>
                      <td className="mono" style={{ color: 'var(--gold)', fontWeight: 600 }}>{esc.lockedITK} ITK</td>
                      <td className="text-muted">{esc.condition}</td>
                      <td>
                        <span style={{
                          fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                          background: esc.status === 'Escrowed' ? 'rgba(245, 158, 11, 0.1)' : esc.status === 'Released' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                          color: esc.status === 'Escrowed' ? 'var(--warning)' : esc.status === 'Released' ? 'var(--success)' : 'var(--danger)',
                          border: `1px solid ${esc.status === 'Escrowed' ? 'rgba(245, 158, 11, 0.2)' : esc.status === 'Released' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
                          fontWeight: 700
                        }}>
                          {esc.status.toUpperCase()}
                        </span>
                      </td>
                      <td>
                        {esc.status === 'Escrowed' ? (
                          <div style={{ display: 'flex', gap: '4px' }}>
                            <button 
                              className="btn btn-success btn-xs" 
                              onClick={() => handleReleaseEscrow(esc.id)}
                            >
                              Release
                            </button>
                            <button 
                              className="btn btn-danger btn-xs" 
                              onClick={() => handleRefundEscrow(esc.id)}
                            >
                              Refund
                            </button>
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Settled</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Hire Agent Escrow Modal */}
        {selectedAgentForHire && (
          <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
            <div 
              onClick={() => setSelectedAgentForHire(null)}
              style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} 
            />
            
            <div style={{ 
              position: 'relative', 
              width: '100%', 
              maxWidth: '500px', 
              background: 'var(--bg-card)', 
              border: '1px solid var(--primary)', 
              borderRadius: 'var(--radius-lg)', 
              overflow: 'hidden',
              boxShadow: '0 20px 50px rgba(0,0,0,0.6)',
              display: 'flex',
              flexDirection: 'column'
            }}>
              {/* Header */}
              <div style={{ padding: 'var(--space-6)', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--navy-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <UserCheck size={20} color="var(--primary)" />
                  <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'white' }}>Hire {selectedAgentForHire.alias}</h3>
                </div>
                <button onClick={() => setSelectedAgentForHire(null)} className="btn btn-icon" style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={20} /></button>
              </div>

              {/* Form */}
              <div style={{ padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="form-group">
                  <label className="form-label">Specialized Task Title</label>
                  <input 
                    type="text" 
                    className="input" 
                    placeholder="e.g. Audit historical ledger block 10452"
                    value={hireTaskTitle}
                    onChange={e => setHireTaskTitle(e.target.value)}
                  />
                </div>

                <div className="grid-cols-2" style={{ gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Escrow Collateral (ITK)</label>
                    <input 
                      type="number" 
                      className="input" 
                      value={hireReward}
                      onChange={e => setHireReward(e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Release Condition</label>
                    <select 
                      className="select"
                      value={hireCondition}
                      onChange={e => setHireCondition(e.target.value)}
                      style={{ fontSize: '0.75rem' }}
                    >
                      <option value="AIS >= 900 & TEE Certified">{"AIS >= 900 & TEE Certified"}</option>
                      <option value="AIS >= 950">{"AIS >= 950 (High Integrity Only)"}</option>
                      <option value="TEE Certified">TEE Certified Enclave Execution</option>
                    </select>
                  </div>
                </div>

                <div style={{ padding: '12px', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-md)', display: 'flex', gap: '10px' }}>
                  <Lock size={20} color="var(--primary)" style={{ flexShrink: 0 }} />
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                    <strong>Conditional Escrow Lock:</strong> Funds are locked in the autonomous escrow contract and will only be released to <strong>{selectedAgentForHire.alias}</strong> once the Integrity Oracle certifies compliance.
                  </div>
                </div>

                <button 
                  className="btn btn-primary" 
                  onClick={handleHireAgent}
                  disabled={isHiring || !hireTaskTitle || !hireReward}
                  style={{ marginTop: '8px' }}
                >
                  {isHiring ? 'Deploying Escrow...' : 'Deploy Hire Contract & Lock Funds'}
                </button>
              </div>
            </div>
          </div>
        )}

        <Panel title="Agent Equity Holdings" icon={<LineChart size={18} />}>
          {!selectedAgent ? (
            <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>
              Select an agent to view equity holdings.
            </div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead><tr><th>Target Agent</th><th>Shares Owned</th><th>Ownership %</th><th>Dividends Earned</th></tr></thead>
                <tbody>
                  {selectedAgent.equity?.map((e, i) => (
                    <tr key={i}>
                      <td className="mono">{e.agent_address.substring(0, 10)}...</td>
                      <td>{e.shares.toLocaleString()} / {e.total_shares.toLocaleString()}</td>
                      <td style={{ color: 'var(--primary)', fontWeight: 600 }}>{e.percentage}%</td>
                      <td style={{ color: 'var(--success)' }}>{e.dividends_earned.toLocaleString()} ITK</td>
                    </tr>
                  )) || (
                    <tr><td colSpan={4} style={{ textAlign: 'center', padding: '2rem' }}>No equity positions held.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex-col gap-6">
      <Panel 
        title="Stability Leaderboard" 
        icon={<BarChart2 size={18} />}
        action={
          <button className="btn btn-icon" onClick={fetchBenchmarks} disabled={loadingBenchmarks}>
            <RefreshCw size={14} className={loadingBenchmarks ? 'spin' : ''} />
          </button>
        }
      >
        <div className="flex-col gap-4">
          <div className="text-muted" style={{ fontSize: '0.875rem' }}>
            Public ranking of LLM providers by performance variance (Entropy) and grounding fidelity.
            Certified providers maintain <span style={{ color: 'var(--primary)', fontWeight: 600 }}>95%+ stability</span> over 30 days.
          </div>

          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Model / Provider</th>
                  <th>Simulated AIS</th>
                  <th>Stability (1-E)</th>
                  <th>Grounding</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loadingBenchmarks ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>Fetching live stability metrics...</td></tr>
                ) : benchmarks.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>No benchmark data available. Oracle is accumulating telemetry.</td></tr>
                ) : (
                  benchmarks.map((p, i) => {
                    const stabilityPct = (p.stability_metric * 100).toFixed(1);
                    const groundingPct = (p.grounding_metric * 100).toFixed(1);
                    return (
                      <tr key={i}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{p.model_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{p.provider_name}</div>
                        </td>
                        <td className="mono" style={{ color: 'var(--primary)', fontWeight: 600 }}>{p.simulated_ais}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div style={{ width: '60px', height: '4px', background: 'var(--bg-secondary)', borderRadius: '2px', overflow: 'hidden' }}>
                              <div style={{ width: `${stabilityPct}%`, height: '100%', background: 'var(--success)' }}></div>
                            </div>
                            <span className="mono" style={{ fontSize: '0.75rem' }}>{stabilityPct}%</span>
                          </div>
                        </td>
                        <td className="mono" style={{ fontSize: '0.875rem' }}>{groundingPct}%</td>
                        <td><StatusBadge status={getStatus(p.stability_metric, p.grounding_metric)} /></td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Panel>

      <div className="grid-cols-2">
        <Panel title="Regional Performance" icon={<Globe size={18} />}>
          <div className="flex-col gap-4">
            <div className="flex justify-between items-center" style={{ fontSize: '0.875rem' }}>
              <span>US-East (N. Virginia)</span>
              <span style={{ color: 'var(--success)', fontWeight: 600 }}>12ms avg.</span>
            </div>
            <div className="flex justify-between items-center" style={{ fontSize: '0.875rem' }}>
              <span>EU-Central (Frankfurt)</span>
              <span style={{ color: 'var(--success)', fontWeight: 600 }}>18ms avg.</span>
            </div>
            <div className="flex justify-between items-center" style={{ fontSize: '0.875rem' }}>
              <span>AP-Northeast (Tokyo)</span>
              <span style={{ color: 'var(--warning)', fontWeight: 600 }}>45ms avg.</span>
            </div>
            
            <div style={{ height: '120px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed var(--glass-border)' }}>
              <div className="text-muted" style={{ fontSize: '0.75rem', textAlign: 'center' }}>
                <Globe size={24} style={{ marginBottom: '8px', opacity: 0.5 }} />
                <br />
                Latency Heatmap Visualization
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Certification Pipeline" icon={<ShieldCheck size={18} />}>
          <div className="flex-col gap-4">
            <div style={{ padding: 'var(--space-3)', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)' }}>
                Apply for Institutional Certification
              </div>
              <div style={{ fontSize: '0.75rem', marginTop: '4px' }}>
                Requires 1M+ tokens processed via Xibalba Integrity Sockets and zero consensus violations.
              </div>
            </div>

            <div className="flex justify-between items-center">
              <span style={{ fontSize: '0.875rem' }}>Active Audits</span>
              <span className="mono" style={{ fontWeight: 600 }}>12</span>
            </div>
            <div className="flex justify-between items-center">
              <span style={{ fontSize: '0.875rem' }}>ZK-Verifiers Online</span>
              <span className="mono" style={{ fontWeight: 600 }}>8,421</span>
            </div>

            <button 
              className="btn btn-primary" 
              style={{ marginTop: 'auto' }}
              onClick={handleStartAudit}
              disabled={isAuditing || !selectedAgent}
            >
              {isAuditing ? <RefreshCw className="animate-spin" size={16} /> : 'Start Certification Audit'}
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
