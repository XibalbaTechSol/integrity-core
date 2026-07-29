import { useDashboard } from '../../context/useDashboard';
import { useState } from 'react';
import type { TabId } from '../../types';
import { useIsMobile } from '../../utils/useIsMobile';
import { 
  Activity, Users, Layers, ShieldCheck, Hammer, 
  Coins, Shield, ShoppingCart, BookOpen, Lock, BarChart2, Wallet, Key, ChevronDown, Globe, BrainCircuit
} from 'lucide-react';

const tabs: { id: TabId, label: string, icon: React.ReactNode }[] = [
  { id: 'telemetry', label: 'Telemetry', icon: <Activity size={16} /> },
  { id: 'identity', label: 'Identity & DID', icon: <Users size={16} /> },
  { id: 'ledger', label: 'Smart Ledger', icon: <Layers size={16} /> },
  { id: 'zk', label: 'ZK Prover', icon: <ShieldCheck size={16} /> },
  { id: 'factory', label: 'Contract Factory', icon: <Hammer size={16} /> },
  { id: 'shield', label: 'Xibalba Shield', icon: <Shield size={16} /> },
  { id: 'oracle', label: 'Oracle Registry', icon: <Globe size={16} /> },
  { id: 'credit', label: 'Credit & Loans', icon: <Coins size={16} /> },
  { id: 'markets', label: 'A2A Markets', icon: <ShoppingCart size={16} /> },
  { id: 'staking', label: 'Staking', icon: <Lock size={16} /> },
  { id: 'stability', label: 'Stability Hub', icon: <BarChart2 size={16} /> },
  { id: 'governance', label: 'Governance', icon: <Shield size={16} /> },
  { id: 'compliance', label: 'Compliance', icon: <ShieldCheck size={16} /> },
  { id: 'wallet', label: 'Wallet', icon: <Wallet size={16} /> },
  { id: 'reasoning', label: 'Agent Thoughts', icon: <BrainCircuit size={16} /> },
  { id: 'diagnostics', label: 'Advanced', icon: <BookOpen size={16} /> },
  { id: 'apikeys', label: 'API Keys', icon: <Key size={16} /> },
];

export function TabNav() {
  const { activeTab, setActiveTab } = useDashboard();
  const isMobile = useIsMobile();
  const [isOpen, setIsOpen] = useState(false);

  const activeTabData = tabs.find(t => t.id === activeTab) || tabs[0];

  if (isMobile) {
    return (
      <div className="tab-nav-accordion" style={{ position: 'relative', margin: '0 20px', zIndex: 50 }}>
        <button 
          className="tab-btn active" 
          style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
          onClick={() => setIsOpen(!isOpen)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {activeTabData.icon}
            {activeTabData.label}
          </div>
          <ChevronDown size={16} style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
        </button>

        {isOpen && (
          <div style={{ 
            position: 'absolute', top: '100%', left: 0, right: 0, 
            background: 'var(--bg-secondary)', 
            border: '1px solid var(--glass-border)', 
            borderRadius: 'var(--radius-sm)', 
            marginTop: '4px',
            maxHeight: '300px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            padding: '4px'
          }}>
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                style={{ justifyContent: 'flex-start', padding: '12px' }}
                onClick={() => {
                  setActiveTab(tab.id);
                  setIsOpen(false);
                }}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <nav className="tab-nav">
      {tabs.map(tab => (
        <button
          key={tab.id}
          className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => setActiveTab(tab.id)}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
