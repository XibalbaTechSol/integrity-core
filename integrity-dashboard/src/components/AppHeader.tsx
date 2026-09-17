import { useLocation } from 'react-router-dom';
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
    'system': 'System Administration',
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
