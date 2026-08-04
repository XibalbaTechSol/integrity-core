import { useState } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { PlusCircle, Database, ShieldCheck, ChevronLeft, ChevronRight, User, Settings, LogIn, LogOut, MoreVertical, Bot, Cpu, Zap, Fingerprint, Box, Hexagon, Activity, Network } from 'lucide-react';
import { StatusBadge } from '../shared/StatusBadge';

const AGENT_ICONS = [Bot, Cpu, Zap, Fingerprint, Box, Hexagon, Activity, Network];

function getAgentIcon(address: string, ais: number) {
  const index = address ? address.charCodeAt(address.length - 1) % AGENT_ICONS.length : 0;
  const Icon = AGENT_ICONS[index];
  const color = ais >= 500 ? 'var(--success)' : 'var(--danger)';
  return <Icon size={14} color={color} style={{ filter: `drop-shadow(0 0 4px ${color})` }} />;
}

export function Sidebar() {
  const { agents, selectedAgent, selectAgent, isLoading, isBackendOffline, setActiveTab, walletAddress, user, signIn, signUp, signOut } = useDashboard();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header" style={{ padding: isCollapsed ? 'var(--space-4) auto' : 'var(--space-6)', position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: isCollapsed ? 'column' : 'row', gap: isCollapsed ? '12px' : '0' }}>
        <div 
          onClick={() => window.location.hash = '#/integrity/telemetry'}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', cursor: 'pointer', width: '100%' }}
        >
          <img src={isCollapsed ? "/integrity/favicon.png" : "/integrity/xibalba_logo.png"} alt="Xibalba" style={{ height: '32px' }} />
        </div>
        <button 
          onClick={() => setIsCollapsed(!isCollapsed)} 
          style={{ 
            background: 'none', 
            border: 'none', 
            color: 'var(--text-muted)', 
            cursor: 'pointer', 
            padding: '4px',
            position: isCollapsed ? 'static' : 'absolute',
            right: isCollapsed ? 'auto' : '16px'
          }}
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
      
      <div style={{ padding: isCollapsed ? '0 8px var(--space-4)' : '0 var(--space-6) var(--space-4)' }}>
        <button 
          className="btn btn-outline" 
          style={{ width: '100%', padding: isCollapsed ? '12px 0' : '12px', display: 'flex', justifyContent: 'center' }}
          onClick={() => setActiveTab('identity')}
          title={isCollapsed ? "Register New Agent" : undefined}
        >
          <PlusCircle size={16} /> {!isCollapsed && 'Register New Agent'}
        </button>
      </div>
      
      <div className="sidebar-content" style={{ padding: isCollapsed ? 'var(--space-4) 8px' : 'var(--space-4)' }}>
        {isLoading ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>{isCollapsed ? '...' : 'Scanning Network...'}</div>
        ) : agents.length === 0 ? (
          <div style={{ padding: 'var(--space-4)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Database size={24} opacity={0.5} />
            {!isCollapsed && <div>{isBackendOffline ? "Oracle Offline" : "No Agents Found"}</div>}
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
                  getAgentIcon(agent.eth_address, agent.current_ais)
                ) : (
                  <div style={{ flex: 1, width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-1)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                        {getAgentIcon(agent.eth_address, agent.current_ais)}
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
      
      <div className="sidebar-footer" style={{ padding: isCollapsed ? 'var(--space-4) auto' : 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: '8px' }}>

        {user ? (
          <div style={{ position: 'relative' }}>
            <button 
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', width: '100%', padding: '8px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}
              onClick={() => setIsMenuOpen(!isMenuOpen)}
            >
              <div style={{ width: '32px', height: '32px', background: 'linear-gradient(135deg, var(--gold) 0%, #a48130 100%)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--navy-deep)', fontWeight: 'bold', fontSize: '14px', boxShadow: '0 2px 8px rgba(0,0,0,0.2)', overflow: 'hidden' }}>
                {user.photoURL ? (
                  <img src={user.photoURL} alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <User size={18} style={{ color: 'var(--navy-deep)' }} />
                )}
              </div>
            </button>
            {isMenuOpen && (
              <div style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, width: '100%', background: 'var(--glass-surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '8px', display: 'flex', flexDirection: 'column', gap: '4px', zIndex: 10, backdropFilter: 'blur(10px)' }}>
                <button className="btn btn-outline" style={{ width: '100%', padding: '8px', justifyContent: 'flex-start', border: 'none' }} onClick={() => { setActiveTab('profile'); setIsMenuOpen(false); }}>
                  <User size={14} /> Profile
                </button>
                <button className="btn btn-outline" style={{ width: '100%', padding: '8px', justifyContent: 'flex-start', border: 'none' }} onClick={() => { setActiveTab('settings'); setIsMenuOpen(false); }}>
                  <Settings size={14} /> Settings
                </button>
                <button className="btn btn-outline" style={{ width: '100%', padding: '8px', justifyContent: 'flex-start', border: 'none', color: 'var(--danger)' }} onClick={() => { signOut(); setIsMenuOpen(false); }}>
                  <LogOut size={14} /> Sign Out
                </button>
              </div>
            )}
          </div>
        ) : (
          <button 
            className="btn btn-primary" 
            style={{ width: '100%', padding: isCollapsed ? '12px 0' : '12px', display: 'flex', justifyContent: 'center' }}
            onClick={() => {
              window.location.hash = '#/auth';
            }}
            title={isCollapsed ? "Sign In" : undefined}
          >
            <LogIn size={16} /> {!isCollapsed && 'Sign In'}
          </button>
        )}
      </div>
    </aside>
  );
}
