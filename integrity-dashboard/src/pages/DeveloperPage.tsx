import React, { useState } from 'react';
import { FactoryPanel } from '../components/ide/FactoryPanel';
import { TraceAnalysisPanel } from '../components/observability/TraceAnalysisPanel';
import { SandboxConsole } from '../components/ui/SandboxConsole';
import { SubTabs } from '../components/ui/SubTabs';
import { Code, Activity, Terminal, GitBranch } from 'lucide-react';

export const DeveloperPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ide' | 'trace' | 'sandbox'>('ide');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
      
      {/* Subtabs Navigation */}
      <SubTabs 
        tabs={[
          { id: 'ide', label: 'IDE / Smart Contracts', icon: <Code size={16} /> },
          { id: 'trace', label: 'Trace Analysis', icon: <Activity size={16} /> },
          { id: 'sandbox', label: 'Sandbox Console', icon: <Terminal size={16} /> }
        ]} 
        activeTab={activeTab} 
        setActiveTab={setActiveTab as any} 
      />

      {/* Main Content Area - Takes up remaining height */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-color)' }}>
        {activeTab === 'ide' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <FactoryPanel />
          </div>
        )}
        
        {activeTab === 'trace' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '1.5rem' }}>
            <TraceAnalysisPanel />
          </div>
        )}
        
        {activeTab === 'sandbox' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '1.5rem' }}>
            <SandboxConsole />
          </div>
        )}
      </div>
    </div>
  );
};
