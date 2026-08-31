import React, { useState } from 'react';
import { FactoryPanel } from '../components/ide/FactoryPanel';
import { TraceAnalysisPanel } from '../components/observability/TraceAnalysisPanel';
import { SandboxConsole } from '../components/ui/SandboxConsole';
import { SubTabs } from '../components/ui/SubTabs';
import { GuidedSystemTest } from '../components/developer/GuidedSystemTest';
import { Code, Activity, Terminal, ShieldCheck, Circle } from 'lucide-react';

export const DeveloperPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ide' | 'trace' | 'sandbox' | 'systest'>('ide');

  return (
    <div className="developer-page" style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0, overflow: 'hidden' }}>
      <header className="developer-workspace-header">
        <div>
          <div className="developer-eyebrow">Engineering workspace</div>
          <h1>Developer</h1>
          <p>Build, inspect, and validate agent-owned contracts.</p>
        </div>
        <div className="developer-environment" aria-label="Developer environment">
          <Circle size={8} fill="currentColor" />
          <span>Base Sepolia</span>
          <span className="developer-environment-divider" />
          <span>Local workspace</span>
        </div>
      </header>

      {/* Workspace navigation */}
      <SubTabs 
        tabs={[
          { id: 'ide', label: 'IDE / Smart Contracts', icon: <Code size={16} /> },
          { id: 'trace', label: 'Trace Analysis', icon: <Activity size={16} /> },
          { id: 'sandbox', label: 'Sandbox Console', icon: <Terminal size={16} /> },
          { id: 'systest', label: 'Guided System Test', icon: <ShieldCheck size={16} /> }
        ]}
        activeTab={activeTab} 
        setActiveTab={setActiveTab as any} 
      />

      {/* Main Content Area - Takes up remaining height */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-color)' }}>
        {activeTab === 'ide' && (
          <div id="developer-panel-ide" role="tabpanel" aria-label="IDE / Smart Contracts" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <FactoryPanel />
          </div>
        )}
        
        {activeTab === 'trace' && (
          <div id="developer-panel-trace" role="tabpanel" aria-label="Trace Analysis" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '1.5rem' }}>
            <TraceAnalysisPanel />
          </div>
        )}
        
        {activeTab === 'sandbox' && (
          <div id="developer-panel-sandbox" role="tabpanel" aria-label="Sandbox Console" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '1.5rem' }}>
            <SandboxConsole />
          </div>
        )}

        {activeTab === 'systest' && (
          <div id="developer-panel-systest" role="tabpanel" aria-label="Guided System Test" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '1.5rem' }}>
            <GuidedSystemTest />
          </div>
        )}
      </div>
    </div>
  );
};
