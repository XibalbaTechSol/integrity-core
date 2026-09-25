import re

with open("src/layouts/MainAppLayout.tsx", "r") as f:
    layout = f.read()

# Make all pages use the exact same flex layout wrapper without "isProtocol" exceptions
# Actually, the easiest way to inject the protocol shell globally:
layout_new = """import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { Sidebar } from '../components/Sidebar';
import { AppHeader } from '../components/AppHeader';
import { useDashboard } from '../context/DashboardContext';
import '../pages/ProtocolDashboardPage.css';

export default function MainAppLayout() {
  const { layoutMode } = useDashboard();
  const location = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [location.pathname]);

  return (
    <div className="protocol-app" style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
      {layoutMode === 'sidebar' && <Sidebar />}
      <main className="protocol-main" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <AppHeader />
        <div className="protocol-content" style={{ flex: 1 }}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
"""
with open("src/layouts/MainAppLayout.tsx", "w") as f:
    f.write(layout_new)

with open("src/components/AppHeader.tsx", "w") as f:
    f.write("""import { useLocation } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';

const short = (value?: string | null, start = 10, end = 8) => {
  if (!value) return 'Unavailable';
  if (value.length <= start + end + 1) return value;
  return `${value.slice(0, start)}…${value.slice(-end)}`;
};

export function AppHeader() {
  const location = useLocation();
  const { agents, selectedAgent, setSelectedAgent, agentsLoading } = useDashboard();
  
  // Very basic tab titles for the header
  const tabTitles: Record<string, string> = {
    'dashboard': 'Protocol overview',
    'identity': 'Identity & Trust',
    'contracts': 'Deployed contracts',
    'treasury': 'Treasury Control',
    'financials': 'Financials',
    'intelligence': 'Intelligence',
    'correlation': 'Correlation',
    'prediction-markets': 'Prediction Markets',
    'health': 'System Health',
    'kernel': 'Kernel Policy',
    'knowledge': 'Knowledge & Memory',
    'licence': 'Licence',
    'wiki': 'Wiki',
    'settings': 'Settings'
  };
  
  const routeTab = location.pathname.slice(1) || 'dashboard';

  return (
    <header className="protocol-topbar">
      <div>
        <span className="protocol-kicker">Integrity protocol backbone</span>
        <h1>{tabTitles[routeTab] || 'Dashboard'}</h1>
      </div>
      <div className="protocol-top-actions">
        <label>Selected agent
          <select aria-label="Selected agent" value={selectedAgent?.id || ''} onChange={event => { const next = agents.find(agent => agent.id === event.target.value); if (next) setSelectedAgent(next); }}>
            <option value="">{agentsLoading ? 'Loading agents…' : 'No agent selected'}</option>
            {agents.map(agent => <option key={agent.id} value={agent.id}>{agent.alias || agent.name || short(agent.id)}</option>)}
          </select>
        </label>
        <button className="icon-button" aria-label="Refresh data"><RefreshCw size={16} /></button>
        <span className="wallet-connection"><i />Wallet offline</span>
      </div>
    </header>
  );
}
""")

# Now strip the <aside> and <header> from ProtocolDashboardPage.tsx
with open("src/pages/ProtocolDashboardPage.tsx", "r") as f:
    dashboard = f.read()

# Replace <div className="protocol-app"> with just a fragment or div
dashboard = re.sub(r'<div className="protocol-app">\s*<aside className="protocol-sidebar">.*?</aside>\s*<main className="protocol-main">\s*<header className="protocol-topbar">.*?</header>', '<div className="protocol-app-inner" style={{display:"contents"}}>', dashboard, flags=re.DOTALL)
dashboard = dashboard.replace('</main>\n  </div>;', '</div>;')
dashboard = dashboard.replace('</main>\r\n  </div>;', '</div>;')

with open("src/pages/ProtocolDashboardPage.tsx", "w") as f:
    f.write(dashboard)

print("Patched MainAppLayout, AppHeader, and ProtocolDashboardPage")
