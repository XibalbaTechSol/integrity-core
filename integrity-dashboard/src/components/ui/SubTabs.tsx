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
    <div className="sub-tabs-container developer-tabs" role="tablist" aria-label="Developer tools">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          aria-pressed={activeTab === tab.id}
          onClick={() => setActiveTab(tab.id as any)}
          style={{
            padding: '0.7rem 1rem',
            background: activeTab === tab.id ? 'var(--bg-color)' : 'transparent',
            border: '1px solid transparent',
            borderRadius: '5px',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            cursor: 'pointer',
            color: activeTab === tab.id ? 'var(--theme-accent, var(--primary, #fff))' : 'var(--text-secondary)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            minHeight: '38px'
          }}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
