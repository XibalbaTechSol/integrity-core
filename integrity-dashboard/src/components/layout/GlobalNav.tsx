import { useDashboard } from '../../context/useDashboard';
import { Activity, DollarSign, Code2, Brain, Key, Shield } from 'lucide-react';
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
  { label: 'Contracts',    icon: <Code2 size={16} />,      activeTabs: ['factory', 'zk', 'oracle', 'ledger'], defaultTab: 'factory' },
  { label: 'Finance',      icon: <DollarSign size={16} />, activeTabs: ['wallet', 'staking', 'credit', 'markets', 'stability'], defaultTab: 'wallet' },
  { label: 'Xibalba Shield', icon: <Shield size={16} />,   activeTabs: ['governance', 'shield', 'compliance'], defaultTab: 'shield' },
  { label: 'Identity',     icon: <Key size={16} />,        activeTabs: ['identity', 'apikeys'], defaultTab: 'identity' },
];

export function GlobalNav() {
  const { activeTab, setActiveTab } = useDashboard();

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
      {/* Brand mark */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginRight: '24px',
        paddingRight: '24px',
        borderRight: '1px solid var(--glass-border)',
        flexShrink: 0,
      }}>
        <img src="/integrity/xibalba_logo.png" alt="Xibalba Solutions Logo" style={{ height: '24px', width: 'auto' }} />
        <span style={{ fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
          Integrity
        </span>
      </div>

      {/* Nav links / buttons */}
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
    </nav>
  );
}
