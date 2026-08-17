import React from 'react';

export interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface SubTabsProps {
  tabs: TabItem[];
  activeTab: string;
  setActiveTab: (id: string) => void;
}

export function SubTabs({ tabs, activeTab, setActiveTab }: SubTabsProps) {
  return (
    <div className="sub-tabs-container" style={{ display: 'flex', gap: '0.5rem', padding: '1rem 1rem 0 1rem', background: 'var(--surface-color)', borderBottom: '1px solid var(--border-color)', overflowX: 'auto' }}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id as any)}
          style={{
            padding: '0.75rem 1.5rem',
            background: activeTab === tab.id ? 'var(--bg-color)' : 'transparent',
            border: '1px solid var(--border-color)',
            borderBottom: activeTab === tab.id ? 'none' : '1px solid var(--border-color)',
            borderRadius: '8px 8px 0 0',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            cursor: 'pointer',
            color: activeTab === tab.id ? 'var(--theme-accent, var(--primary, #fff))' : 'var(--text-secondary)',
            fontWeight: 600,
            whiteSpace: 'nowrap'
          }}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
