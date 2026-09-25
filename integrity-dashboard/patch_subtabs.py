with open("src/components/ui/SubTabs.tsx", "w") as f:
    f.write("""import React from 'react';

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
    <div className="protocol-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={`protocol-tab ${activeTab === tab.id ? 'active' : ''}`}
        >
          {tab.icon}
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  );
}
""")

with open("src/index.css", "a") as f:
    f.write("""
/* Unified Protocol SubTabs */
.protocol-tabs {
  display: flex;
  gap: 12px;
  border-bottom: 1px solid var(--protocol-line, #213246);
  margin-bottom: 16px;
  overflow-x: auto;
}
.protocol-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  color: var(--protocol-muted, #8ea1b4);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.protocol-tab:hover {
  color: var(--protocol-text, #eef5fb);
}
.protocol-tab.active {
  color: var(--protocol-blue, #36a7ff);
  border-bottom-color: var(--protocol-blue, #36a7ff);
}
""")
print("Patched SubTabs")
