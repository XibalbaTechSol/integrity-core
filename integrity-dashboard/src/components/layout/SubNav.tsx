import React from 'react';
import { useDashboard } from '../../context/useDashboard';
import {
  FileCode, Shield, Database, Layers,
  Wallet, Lock, DollarSign, ShoppingCart, BarChart2,
  User, Key, FileText, Activity, AlertTriangle, Brain, GitBranch
} from 'lucide-react';
import type { TabId } from '../../types';

interface SubTab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const SUB_TABS_CONFIG: Record<string, SubTab[]> = {
  contracts: [
    { id: 'factory', label: 'Factory', icon: <FileCode size={14} /> },
    { id: 'zk',      label: 'ZK Prover', icon: <Shield size={14} /> },
    { id: 'oracle',  label: 'Oracle', icon: <Database size={14} /> },
    { id: 'ledger',  label: 'Ledger', icon: <Layers size={14} /> },
  ],
  finance: [
    { id: 'wallet',    label: 'Wallet',    icon: <Wallet       size={14} /> },
    { id: 'staking',   label: 'Staking',   icon: <Lock         size={14} /> },
    { id: 'credit',    label: 'Credit',    icon: <DollarSign   size={14} /> },
    { id: 'markets',   label: 'Markets',   icon: <ShoppingCart size={14} /> },
    { id: 'stability', label: 'Stability', icon: <BarChart2    size={14} /> },
  ],
  identity: [
    { id: 'identity', label: 'Identity & DID', icon: <User size={14} /> },
  ],
  shield: [
    { id: 'governance', label: 'Smart BAAs', icon: <FileText size={14} /> },
    { id: 'shield', label: 'PHI Access Gates', icon: <Lock size={14} /> },
    { id: 'compliance', label: 'Audit & Compliance', icon: <Activity size={14} /> },
    { id: 'quarantine', label: 'Quarantine Zone', icon: <AlertTriangle size={14} /> },
  ]
};

export function SubNav() {
  const { activeTab, setActiveTab } = useDashboard();

  let activeGroup: string | null = null;
  let tabsToRender: SubTab[] = [];

  for (const [group, tabs] of Object.entries(SUB_TABS_CONFIG)) {
    if (tabs.some(t => t.id === activeTab)) {
      activeGroup = group;
      tabsToRender = tabs;
      break;
    }
  }

  // If there are no subtabs to render for the current route, we return null
  if (!activeGroup || tabsToRender.length === 0) {
    return null;
  }

  return (
    <div style={{
      display: 'flex',
      gap: '12px',
      padding: '12px 24px',
      background: 'rgba(12, 16, 23, 0.6)',
      borderBottom: '1px solid var(--glass-border)',
      backdropFilter: 'blur(10px)',
      overflowX: 'auto',
      WebkitOverflowScrolling: 'touch',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)'
    }}>
      {tabsToRender.map(tab => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: '999px',
              fontSize: '0.8rem',
              fontWeight: isActive ? 600 : 500,
              cursor: 'pointer',
              background: isActive ? 'var(--gold-muted)' : 'transparent',
              border: isActive ? '1px solid var(--gold)' : '1px solid transparent',
              color: isActive ? 'var(--gold)' : 'var(--text-muted)',
              transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              whiteSpace: 'nowrap',
              outline: 'none',
              boxShadow: isActive ? '0 0 10px rgba(201, 168, 76, 0.15)' : 'none'
            }}
            onMouseOver={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = 'var(--text-primary)';
                e.currentTarget.style.background = 'var(--surface-hover)';
              }
            }}
            onMouseOut={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = 'var(--text-muted)';
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
