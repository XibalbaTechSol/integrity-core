import { useDashboard } from '../../context/useDashboard';
import { PlusCircle, Database, ShieldCheck } from 'lucide-react';
import { StatusBadge } from '../shared/StatusBadge';

export function Sidebar() {
  const { agents, selectedAgent, selectAgent, isLoading, setActiveTab } = useDashboard();

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
          <img src="/integrity/XibalbaSolutionsLogo.png" alt="Xibalba" style={{ height: '32px' }} />
          <div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>Xibalba <span style={{ color: 'var(--text-muted)' }}>Solutions</span></div>
            <div style={{ fontSize: '0.7rem', color: 'var(--primary)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Integrity Protocol</div>
          </div>
        </div>
        
        <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Fleet Command</h2>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', opacity: 0.7 }}>Sovereign Agent Roster</div>
      </div>
      
      <div className="sidebar-content">
        {isLoading ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>Scanning Network...</div>
        ) : agents.length === 0 ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Database size={24} opacity={0.5} />
            <div>No Agents Found</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {agents.map(agent => (
              <div 
                key={agent.eth_address}
                onClick={() => selectAgent(agent.eth_address)}
                style={{
                  padding: 'var(--space-3)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: selectedAgent?.eth_address === agent.eth_address ? 'var(--surface-hover)' : 'transparent',
                  border: `1px solid ${selectedAgent?.eth_address === agent.eth_address ? 'rgba(201, 168, 76, 0.4)' : 'transparent'}`,
                  transition: 'all var(--transition-fast)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-1)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <div style={{ 
                      width: '8px', height: '8px', borderRadius: '50%', 
                      background: agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)',
                      boxShadow: `0 0 8px ${agent.current_ais >= 500 ? 'var(--success)' : 'var(--danger)'}`
                    }} />
                    <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{agent.alias || 'Unnamed'}</span>
                  </div>
                  <StatusBadge ais={agent.current_ais} />
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  <div className="mono">{agent.eth_address.substring(0, 10)}...</div>
                  {agent.tee_verified && <ShieldCheck size={14} color="var(--primary)" />}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      <div className="sidebar-footer">
        <button 
          className="btn btn-primary" 
          style={{ width: '100%' }}
          onClick={() => setActiveTab('identity')}
        >
          <PlusCircle size={16} /> Register New Agent
        </button>
      </div>
    </aside>
  );
}
