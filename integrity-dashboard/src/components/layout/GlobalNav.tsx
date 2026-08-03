import React, { useState } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { Activity, DollarSign, Code2, Brain, Key, Shield, AlertTriangle, Server, RefreshCw, Wallet } from 'lucide-react';
import type { TabId } from '../../types';

interface NavItem {
  label: string;
  icon: React.ReactNode;
  activeTabs: TabId[];
  defaultTab: TabId;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Intelligence', icon: <Activity size={16} />,   activeTabs: ['telemetry'], defaultTab: 'telemetry' },
  { label: 'Cognition',    icon: <Brain size={16} />,      activeTabs: ['cognition', 'reasoning', 'diagnostics'], defaultTab: 'reasoning' },
  { label: 'Contracts',    icon: <Code2 size={16} />,      activeTabs: ['map', 'factory', 'zk', 'oracle', 'ledger'], defaultTab: 'map' },
  { label: 'Finance',      icon: <DollarSign size={16} />, activeTabs: ['wallet', 'staking', 'credit', 'markets', 'stability'], defaultTab: 'wallet' },
  { label: 'Xibalba Shield', icon: <Shield size={16} />,   activeTabs: ['governance', 'shield', 'compliance', 'quarantine'], defaultTab: 'shield' },
  { label: 'Identity',     icon: <Key size={16} />,        activeTabs: ['identity'], defaultTab: 'identity' },
  { label: 'Settings',     icon: <Server size={16} />,     activeTabs: ['settings'], defaultTab: 'settings' },
];

export function GlobalNav() {
  const { activeTab, setActiveTab, walletAddress, connectWallet, fetchData, isBackendOffline } = useDashboard();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <nav style={{
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
      padding: '8px 24px',
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--glass-border)',
      overflowX: 'auto',
    }}>


      {/* Nav links / buttons */}
      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
        {NAV_ITEMS.map(({ label, icon, activeTabs, defaultTab }) => {
          const isActive = activeTabs.includes(activeTab);
          return (
            <button
              key={label}
              onClick={() => setActiveTab(defaultTab)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 16px',
                borderRadius: '999px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
                background: isActive ? 'var(--primary)' : 'transparent',
                color: isActive ? '#000' : 'var(--text-muted)',
                border: `1px solid ${isActive ? 'var(--primary)' : 'transparent'}`,
                outline: 'none',
              }}
            >
              {icon}
              {label}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', flexWrap: 'wrap', justifyContent: 'flex-end', flex: 1, marginLeft: 'auto' }}>
        {isBackendOffline && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--danger-dim)', color: 'var(--danger)', padding: '4px 8px', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
            <AlertTriangle size={14} /> ORACLE OFFLINE
          </div>
        )}
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 600, color: isBackendOffline ? 'var(--danger)' : 'var(--success)', whiteSpace: 'nowrap' }}>
          <Server size={14} /> {isBackendOffline ? 'DISCONNECTED' : 'DATABASE ONLINE'}
        </div>

        <button className="btn btn-ghost" onClick={handleRefresh} disabled={isRefreshing} style={{ padding: '4px 8px' }}>
          <RefreshCw size={16} className={isRefreshing ? 'animate-spin' : ''} /> Sync
        </button>

        <button 
          className={`btn ${walletAddress ? 'btn-success' : 'btn-primary'}`} 
          onClick={connectWallet}
          style={{ minWidth: '140px' }}
        >
          <Wallet size={16} />
          {walletAddress ? `${walletAddress.substring(0, 6)}...${walletAddress.substring(38)}` : 'Connect Wallet'}
        </button>
      </div>
    </nav>
  );
}
