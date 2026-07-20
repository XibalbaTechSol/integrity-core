import { useState } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { PlusCircle, Database, ShieldCheck, ChevronLeft, ChevronRight } from 'lucide-react';
import { StatusBadge } from '../shared/StatusBadge';

export function Sidebar() {
  const { agents, selectedAgent, selectAgent, isLoading, setActiveTab, walletAddress } = useDashboard();
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header" style={{ padding: isCollapsed ? 'var(--space-4) auto' : 'var(--space-6)', justifyContent: isCollapsed ? 'center' : 'space-between', flexDirection: isCollapsed ? 'column' : 'row', gap: isCollapsed ? '12px' : '0' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: isCollapsed ? 'center' : 'flex-start', gap: '4px' }}>
          <img src="/integrity/xibalba_logo.png" alt="Xibalba" style={{ height: '32px' }} />
          {!isCollapsed && (
            <div style={{ fontSize: '0.65rem', color: 'var(--gold)', letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 }}>
              Integrity Protocol
            </div>
          )}
        </div>
        <button 
          onClick={() => setIsCollapsed(!isCollapsed)} 
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!isCollapsed}
        >
          {isCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
      
      {!isCollapsed && (
        <div style={{ padding: '0 var(--space-6) var(--space-4)' }}>
          <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {walletAddress ? 'Sovereign Fleet' : 'Public Nodes'}
          </h2>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', opacity: 0.7 }}>
            {walletAddress ? 'My Delegated Agents' : 'Network Roster (Read-Only)'}
          </div>
        </div>
      )}
      
      <div className="sidebar-content" style={{ padding: isCollapsed ? 'var(--space-4) 8px' : 'var(--space-4)' }}>
        {isLoading ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>{isCollapsed ? '...' : 'Scanning Network...'}</div>
        ) : agents.length === 0 ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Database size={24} opacity={0.5} />
            {!isCollapsed && <div>No Agents Found</div>}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {[...agents].sort((a, b) => (b.alias?.toLowerCase().includes('xibalba') ? 1 : 0) - (a.alias?.toLowerCase().includes('xibalba') ? 1 : 0)).map(agent => (
              <div 
                key={agent.eth_address}
                onClick={() => selectAgent(agent.eth_address)}
                title={isCollapsed ? `${agent.alias} (${agent.current_ais} AIS)` : undefined}
                style={{
                  padding: isCollapsed ? '12px 0' : 'var(--space-3)',
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  flexDirection: isCollapsed ? 'column' : 'row',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: selectedAgent?.eth_address === agent.eth_address ? 'var(--surface-hover)' : 'transparent',
                  border: `1px solid ${selectedAgent?.eth_address === agent.eth_address ? 'rgba(201, 168, 76, 0.4)' : (agent.alias?.toLowerCase().includes('xibalba') ? 'rgba(212, 175, 55, 0.2)' : 'transparent')}`,
                  transition: 'all var(--transition-fast)',
                  borderLeft: (selectedAgent?.eth_address === agent.eth_address || agent.alias?.toLowerCase().includes('xibalba')) && !isCollapsed ? '3px solid var(--gold)' : undefined
                }}
              >
                {isCollapsed ? (
                  <div style={{ 
                    width: '12px', height: '12px', borderRadius: '50%', 
                    background: agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)',
                    boxShadow: `0 0 8px ${agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)'}`
                  }} />
                ) : (
                  <div style={{ flex: 1, width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-1)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                        <div style={{ 
                          width: '8px', height: '8px', borderRadius: '50%', 
                          background: agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)',
                          boxShadow: `0 0 8px ${agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)'}`
                        }} />
                        <span style={{ fontWeight: 600, fontSize: '0.875rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '110px' }}>{agent.alias || 'Unnamed'}</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                        <StatusBadge ais={agent.current_ais} />
                        <span style={{ fontSize: '0.6rem', color: 'var(--gold)', fontWeight: 600, marginTop: '2px', textTransform: 'uppercase' }}>
                          {agent.verification_tier === 3 ? 'Inst.' : agent.verification_tier === 2 ? 'Linked' : 'Sov.'}
                        </span>
                      </div>
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <div className="mono">{agent.eth_address.substring(0, 10)}...</div>
                      {agent.tee_verified && <ShieldCheck size={14} color="var(--gold)" />}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      
      <div className="sidebar-footer" style={{ padding: isCollapsed ? 'var(--space-4) auto' : 'var(--space-4)', display: 'flex', justifyContent: 'center' }}>
        <button 
          className="btn btn-primary" 
          style={{ width: '100%', padding: isCollapsed ? '12px 0' : '16px 36px', display: 'flex', justifyContent: 'center' }}
          onClick={() => setActiveTab('identity')}
          title={isCollapsed ? "Register New Agent" : undefined}
        >
          <PlusCircle size={16} /> {!isCollapsed && 'Register New Agent'}
        </button>
      </div>
    </aside>
  );
}
