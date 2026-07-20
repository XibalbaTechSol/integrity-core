import React from 'react';
import { useDashboard } from '../../context/useDashboard';
import { Shield, Wallet, Server, RefreshCw, AlertTriangle, Globe, Mail, LogIn, LogOut } from 'lucide-react';

export function Topbar() {
  const { walletAddress, connectWallet, fetchData, isBackendOffline, user, signInWithGoogle, signOut } = useDashboard();
  const [isRefreshing, setIsRefreshing] = React.useState(false);

  const [domain, setDomain] = React.useState('global');

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <div className="topbar" style={{ flexWrap: 'wrap', height: 'auto', padding: '12px 24px', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <select 
          value={domain} 
          onChange={(e) => setDomain(e.target.value)}
          style={{ background: '#0e0e12', border: '1px solid rgba(255,255,255,0.1)', color: 'white', fontSize: '0.75rem', padding: '4px 8px', borderRadius: '4px', outline: 'none', marginRight: '8px' }}
        >
          <option value="global">global</option>
          <option value="shield">shield</option>
          <option value="quant">quant</option>
        </select>
        <img src="/integrity/xibalba_logo.png" alt="Xibalba Solutions Logo" style={{ height: '32px', width: 'auto' }} />
        <div>
          <h1 style={{ fontSize: '1rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Integrity Command Center
          </h1>
          <div className="mono" style={{ fontSize: '0.65rem', color: 'var(--gold)', letterSpacing: '0.1em' }}>
            ORACLE REPUTATION NETWORK v9.0
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', flexWrap: 'wrap', justifyContent: 'flex-end', flex: 1 }}>

        {isBackendOffline && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--danger-dim)', color: 'var(--danger)', padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', fontWeight: 600 }}>
            <AlertTriangle size={14} /> ORACLE DATABASE OFFLINE
          </div>
        )}
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 600, color: isBackendOffline ? 'var(--danger)' : 'var(--success)' }}>
          <Server size={14} /> {isBackendOffline ? 'DISCONNECTED' : 'DATABASE ONLINE'}
        </div>

        <button className="btn btn-ghost" onClick={handleRefresh} disabled={isRefreshing} style={{ padding: '4px 8px' }}>
          <RefreshCw size={16} className={isRefreshing ? 'animate-spin' : ''} /> Sync
        </button>

        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.05)', padding: '4px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gold)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.displayName || user.email}
            </span>
            <button 
              onClick={signOut}
              title="Sign Out"
              style={{ background: 'transparent', border: 'none', color: 'var(--danger)', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <button 
            className="btn btn-ghost" 
            onClick={signInWithGoogle}
            style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <Mail size={14} /> Google Sign In
          </button>
        )}

        <button 
          className={`btn ${walletAddress ? 'btn-success' : 'btn-primary'}`} 
          onClick={connectWallet}
          style={{ minWidth: '140px' }}
        >
          <Wallet size={16} />
          {walletAddress ? `${walletAddress.substring(0, 6)}...${walletAddress.substring(38)}` : 'Connect Wallet'}
        </button>
      </div>
    </div>
  );
}
