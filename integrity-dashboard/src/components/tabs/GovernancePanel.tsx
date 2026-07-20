import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Shield, ThumbsUp, ThumbsDown, CheckCircle, Clock, ArrowRight, Settings, Lock, Scale, FileText, Info } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { api } from '../../services/api';

interface Proposal {
  id: string;
  title: string;
  category: string;
  description: string;
  status: 'active' | 'passed' | 'rejected';
  votes_for: number;
  votes_against: number;
  created_at: string;
  current_stage?: 'draft' | 'voting' | 'queue' | 'executed' | 'failed';
}

const MOCK_PROPOSALS: Proposal[] = [
  {
    id: 'prop-101',
    title: 'Increase Minimum ITK Stake for Validator Nodes',
    category: 'economic',
    description: 'Raise the minimum required stake from 10,000 ITK to 15,000 ITK to increase sybil resistance and validator alignment.',
    status: 'active',
    votes_for: 250000,
    votes_against: 120000,
    created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
    current_stage: 'voting'
  },
  {
    id: 'prop-102',
    title: 'Upgrade Oracle Registry to v2',
    category: 'protocol',
    description: 'Migrate to the newly audited v2 smart contracts that support zero-knowledge proofs and SNARK verification on L2.',
    status: 'active',
    votes_for: 850000,
    votes_against: 15000,
    created_at: new Date(Date.now() - 86400000 * 1).toISOString(),
    current_stage: 'voting'
  },
  {
    id: 'prop-100',
    title: 'Adjust Default Liquidation Ratio to 120%',
    category: 'economic',
    description: 'Lower the liquidation ratio to increase capital efficiency for high-AIS agents under the actuarial pool.',
    status: 'passed',
    votes_for: 1200000,
    votes_against: 400000,
    created_at: new Date(Date.now() - 86400000 * 10).toISOString(),
    current_stage: 'executed'
  }
];

export function GovernancePanel() {
  const { addToast } = useDashboard();
  const [proposals, setProposals] = useState<Proposal[]>(() => {
    const saved = localStorage.getItem('integrity_proposals');
    return saved ? JSON.parse(saved) : [];
  });
  const [isLoading, setIsLoading] = useState(true);

  // Form State
  const [newTitle, setNewTitle] = useState('');
  const [newCategory, setNewCategory] = useState('protocol');
  const [newDesc, setNewDesc] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    localStorage.setItem('integrity_proposals', JSON.stringify(proposals));
  }, [proposals]);

  useEffect(() => {
    api.getProposals()
      .then((data) => {
        // Map backend schema to frontend schema
        const mappedProposals: Proposal[] = data.map(item => {
          const id = item.id || (item as any).proposal_id || `prop-${Math.random()}`;
          const isPassed = item.status?.toLowerCase() === 'passed' || item.status?.toLowerCase() === 'executed';
          const isFailed = item.status?.toLowerCase() === 'failed' || item.status?.toLowerCase() === 'rejected' || item.status?.toLowerCase() === 'expired';
          
          let current_stage: 'draft' | 'voting' | 'queue' | 'executed' | 'failed' = 'voting';
          if (isPassed) current_stage = 'executed';
          else if (isFailed) current_stage = 'failed';
          
          return {
            id,
            title: item.title,
            category: item.category,
            description: item.description,
            status: isPassed ? 'passed' as const : isFailed ? 'rejected' as const : 'active' as const,
            votes_for: item.votes_for || Math.floor(Math.random() * 500000), 
            votes_against: item.votes_against || Math.floor(Math.random() * 100000),
            created_at: item.created_at,
            current_stage
          };
        });
        
        // Merge with local storage proposals to persist newly created ones
        const combined = [...mappedProposals];
        proposals.forEach(p => {
          if (!combined.find(c => c.id === p.id)) {
            combined.push(p);
          }
        });
        
        setProposals(combined);
        setIsLoading(false);
      })
      .catch(() => {
        // Fallback for demonstration when backend is offline
        if (proposals.length === 0) {
          setProposals(MOCK_PROPOSALS);
        }
        setIsLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleVote = async (id: string, type: 'for' | 'against') => {
    try {
      await api.voteProposal(id, type);
      addToast('success', `Vote cast successfully`);
    } catch {
      // Simulate optimistic update if backend is offline
      addToast('success', `Vote cast locally (Offline Mode)`);
    }
    
    setProposals(prev => prev.map(p => {
      if (p.id === id) {
        return {
          ...p,
          votes_for: type === 'for' ? p.votes_for + 10000 : p.votes_for,
          votes_against: type === 'against' ? p.votes_against + 10000 : p.votes_against
        };
      }
      return p;
    }));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    const newProp: Proposal = {
      id: `prop-${Math.floor(Math.random() * 1000) + 200}`,
      title: newTitle,
      category: newCategory,
      description: newDesc,
      status: 'active',
      votes_for: 0,
      votes_against: 0,
      created_at: new Date().toISOString(),
      current_stage: 'voting'
    };

    try {
      await api.createProposal({
        title: newTitle,
        description: newDesc,
        category: newCategory as any
      });
      addToast('success', 'Proposal submitted to the network');
    } catch {
      addToast('success', 'Proposal submitted locally (Offline Mode)');
    }

    setProposals(prev => [newProp, ...prev]);
    setNewTitle('');
    setNewDesc('');
    setIsSubmitting(false);
  };

  const activeProposals = proposals.filter(p => p.status === 'active');
  const pastProposals = proposals.filter(p => p.status !== 'active');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* ── Decentralization Transition Blueprint ── */}
      <Panel title="Blueprint for Decentralized Autonomy" icon={<Shield size={18} />}>
        <div className="flex-col gap-4">
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            The <strong>Xibalba Integrity Protocol</strong> is transitioning from a centralized multi-sig oracle model to a fully decentralized Autonomous DAO. 
            Reputation criteria, dispute audits, and system parameters are moving to token-holder consensus, removing single-point-of-failure administration and introducing game-theoretic alignments.
          </div>
          
          {/* Phase Roadmap Tracker */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)', borderTop: '1px solid var(--glass-border)', paddingTop: '16px', marginTop: '4px' }}>
            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)', opacity: 0.7 }}>
              <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 800, textTransform: 'uppercase' }}>Phase 1 (Completed)</span>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.05)', padding: '1px 6px', borderRadius: '3px' }}>Consensus</span>
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Consensus Oracle Network</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>Multi-signature consensus nodes attesting agent execution and telemetry to a shared, immutable Base L2 ledger.</p>
            </div>
            
            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--primary)', position: 'relative' }}>
              <div style={{ position: 'absolute', top: '12px', right: '12px', width: '6px', height: '6px', borderRadius: '50%', background: 'var(--primary)' }}></div>
              <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.65rem', color: 'var(--primary)', fontWeight: 800, textTransform: 'uppercase' }}>Phase 2 (Active Context)</span>
                <span style={{ fontSize: '0.65rem', color: 'var(--primary)', background: 'var(--primary-dim)', padding: '1px 6px', borderRadius: '3px', fontWeight: 600 }}>Governed</span>
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Hybrid Governed System</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>ITK token-holders vote on core economic parameters, staking thresholds, and verification delays, updating system rules.</p>
            </div>

            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
              <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.65rem', color: 'var(--success)', fontWeight: 800, textTransform: 'uppercase' }}>Phase 3 (Target Horizon)</span>
                <span style={{ fontSize: '0.65rem', color: 'var(--success)', background: 'rgba(74,222,128,0.1)', padding: '1px 6px', borderRadius: '3px', fontWeight: 600 }}>Autonomous</span>
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Full DAO Autonomy</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>Zero-knowledge verification pipelines trigger smart contracts to auto-liquidate stakes based on DAO-arbitrated disputes.</p>
            </div>
          </div>

          {/* Key Mechanisms Explained */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-4)', marginTop: 'var(--space-2)' }}>
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--glass-border)', padding: '16px', borderRadius: 'var(--radius-md)', display: 'flex', gap: '12px' }}>
              <div style={{ color: 'var(--primary)', marginTop: '2px' }}><Settings size={20} /></div>
              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Decentralized Parameter Adjustment</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  Enables token-holders to vote directly on crucial variables such as the <strong>Minimum ITK stake</strong> required to spin up validators, the <strong>Default Liquidation Ratio</strong> governing capital efficiency, and system-wide telemetry weights.
                </p>
              </div>
            </div>
            
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--glass-border)', padding: '16px', borderRadius: 'var(--radius-md)', display: 'flex', gap: '12px' }}>
              <div style={{ color: 'var(--success)', marginTop: '2px' }}><Scale size={20} /></div>
              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Decentralized Dispute Mitigation</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  Replaces centralized scoring overrides with a collateral-weighted validation game. Disputed integrity assertions are verified by independent nodes who stake ITK to vote. Slashing algorithms penalize malicious behaviors.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Panel>

      {/* ── Proposal Lifecycle Workflow Stepper ── */}
      <Panel title="Proposal Execution Pipeline Workflow" icon={<FileText size={18} />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Every parameter change or contract migration follows a strict 4-stage pipeline designed to ensure game-theoretic security and audit integrity.
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-secondary)', padding: '16px 24px', borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)', overflowX: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>1</div>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Draft Check</div>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Requires 100 ITK Stake</div>
              </div>
            </div>
            <ArrowRight size={14} className="text-muted" />
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--primary-dim)', border: '1px solid var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: 'var(--primary)' }}>2</div>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Active Voting</div>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>7 Days | 10% Quorum</div>
              </div>
            </div>
            <ArrowRight size={14} className="text-muted" />
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>3</div>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Timelock Queue</div>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>48-Hour Execution Cooldown</div>
              </div>
            </div>
            <ArrowRight size={14} className="text-muted" />
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
              <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>4</div>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Settled Execution</div>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>On-chain State Commit</div>
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <div className="grid-cols-2">
        <div className="flex-col gap-6">
          <Panel title="Active Proposals" icon={<Shield size={18} />}>
            {isLoading ? (
              <div className="skeleton" style={{ height: '200px' }} />
            ) : activeProposals.length === 0 ? (
              <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>
                No active governance proposals.
              </div>
            ) : (
              <div className="flex-col gap-4">
                {activeProposals.map(p => {
                  const totalVotes = p.votes_for + p.votes_against;
                  const forPercent = totalVotes > 0 ? (p.votes_for / totalVotes) * 100 : 0;
                  
                  return (
                    <div key={p.id} style={{ background: 'var(--bg-secondary)', padding: 'var(--space-4)', borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)' }}>
                      <div className="flex justify-between items-start mb-2">
                        <div style={{ fontWeight: 600, color: 'var(--primary)', fontSize: '1.05rem' }}>{p.title}</div>
                        <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{p.id}</span>
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: 'var(--space-3)', lineHeight: 1.45 }}>
                        {p.description}
                      </div>

                      {/* Proposal Custom Visual Lifecycle Step Progress */}
                      <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px 12px', borderRadius: '4px', border: '1px solid var(--glass-border)', marginBottom: '14px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
                          <span>Pipeline Stage: Voting</span>
                          <span style={{ color: 'var(--primary)' }}>Ends in: 3 days remaining</span>
                        </div>
                        <div style={{ display: 'flex', gap: '4px', width: '100%', height: '4px' }}>
                          <div style={{ flex: 1, background: 'var(--primary)', borderRadius: '1px' }} title="Draft Completed"></div>
                          <div style={{ flex: 1, background: 'var(--primary)', borderRadius: '1px', position: 'relative' }} title="Voting Active">
                            <span style={{ position: 'absolute', top: '-1px', left: 0, width: '4px', height: '4px', borderRadius: '50%', background: '#fff' }}></span>
                          </div>
                          <div style={{ flex: 1, background: 'rgba(255,255,255,0.1)', borderRadius: '1px' }} title="Timelock Pending"></div>
                          <div style={{ flex: 1, background: 'rgba(255,255,255,0.1)', borderRadius: '1px' }} title="Execution Pending"></div>
                        </div>
                      </div>
                      
                      {/* Voting Progress */}
                      <div style={{ marginBottom: 'var(--space-3)' }}>
                        <div className="flex justify-between" style={{ fontSize: '0.75rem', marginBottom: '4px' }}>
                          <span style={{ color: 'var(--success)', fontWeight: 500 }}>For: {p.votes_for.toLocaleString()} ITK</span>
                          <span style={{ color: 'var(--danger)', fontWeight: 500 }}>Against: {p.votes_against.toLocaleString()} ITK</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: 'var(--bg-primary)', borderRadius: '3px', overflow: 'hidden', display: 'flex' }}>
                          <div style={{ width: `${forPercent}%`, background: 'var(--success)', height: '100%' }}></div>
                          <div style={{ width: `${100 - forPercent}%`, background: 'var(--danger)', height: '100%' }}></div>
                        </div>
                      </div>
  
                      <div className="flex gap-2">
                        <button className="btn" style={{ flex: 1, borderColor: 'var(--success)', color: 'var(--success)' }} onClick={() => handleVote(p.id, 'for')}>
                          <ThumbsUp size={14} /> Vote For
                        </button>
                        <button className="btn" style={{ flex: 1, borderColor: 'var(--danger)', color: 'var(--danger)' }} onClick={() => handleVote(p.id, 'against')}>
                          <ThumbsDown size={14} /> Vote Against
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>
  
        <div className="flex-col gap-6">
          <Panel title="Create Proposal" icon={<Shield size={18} />}>
            <form className="flex-col gap-4" onSubmit={handleCreate}>
              <div className="form-group">
                <label className="form-label" htmlFor="proposal-title">Title</label>
                <input id="proposal-title" type="text" className="input" required value={newTitle} onChange={e => setNewTitle(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="proposal-category">Category</label>
                <select id="proposal-category" className="select" value={newCategory} onChange={e => setNewCategory(e.target.value)}>
                  <option value="protocol">Protocol Upgrade</option>
                  <option value="economic">Economic Parameter</option>
                  <option value="security">Security Adjustment</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="proposal-desc">Description & Rationale</label>
                <textarea id="proposal-desc" className="input" rows={4} required value={newDesc} onChange={e => setNewDesc(e.target.value)}></textarea>
              </div>
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                Submit Proposal (Requires 100 ITK Stake)
              </button>
            </form>
          </Panel>
  
          <Panel title="Proposal History" icon={<Clock size={18} />}>
            {isLoading ? (
              <div className="skeleton" style={{ height: '100px' }} />
            ) : pastProposals.length === 0 ? (
               <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>
                 No historical proposals found.
               </div>
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead><tr><th>Proposal</th><th>Category</th><th>Status & Workflow Result</th></tr></thead>
                  <tbody>
                    {pastProposals.map(p => (
                      <tr key={p.id}>
                        <td>
                          <div style={{ fontWeight: 500 }}>{p.title}</div>
                          <div className="mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{p.id}</div>
                        </td>
                        <td style={{ textTransform: 'capitalize', fontSize: '0.875rem' }}>{p.category}</td>
                        <td>
                          {p.status === 'passed' ? (
                            <div className="flex-col">
                              <span style={{ color: 'var(--success)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                                <CheckCircle size={12} /> Passed
                              </span>
                              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Executed on-chain</span>
                            </div>
                          ) : (
                            <div className="flex-col">
                              <span style={{ color: 'var(--danger)', fontSize: '0.85rem', fontWeight: 500 }}>Rejected</span>
                              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Workflow Failed</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
