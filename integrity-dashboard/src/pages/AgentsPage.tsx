import { useMemo, useState } from 'react';
import { BadgeCheck, KeyRound, UserRoundCog, Users } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import { FleetWalletOverview } from '../components/ui/FleetWalletOverview';
import { IdentityPanel } from '../components/tabs/IdentityPanel';
import { IntegrityRadar } from '../components/shared/IntegrityRadar';

type AgentTab = 'fleet' | 'identity';

const TABS: ControlTab<AgentTab>[] = [
  { id: 'fleet', label: 'Agent fleet', icon: Users },
  { id: 'identity', label: 'Identity & verification', icon: KeyRound },
];

export default function AgentsPage() {
  const { agents, selectedAgent, setSelectedAgent, agentsLoading } = useDashboard();
  const [tab, setTab] = useState<AgentTab>('fleet');
  const verified = useMemo(() => agents.filter((agent) => agent.verification_tier > 0).length, [agents]);

  return (
    <div className="control-page">
      <ControlHeader
        eyebrow="Fleet control"
        title="Agents & Identity"
        description="Register, select, verify, and inspect every autonomous identity under management."
        actions={<button className="control-primary-action" onClick={() => setTab('identity')}><UserRoundCog size={16} /> Manage identity</button>}
      />
      <ControlTabs tabs={TABS} active={tab} onChange={setTab} label="Agent management views" />

      {tab === 'fleet' ? (
        <div className="control-page-body">
          <div className="control-metric-grid compact">
            <article className="control-metric"><span>Registered agents</span><strong>{agentsLoading ? '—' : agents.length}</strong><small>Oracle-enrolled DIDs</small></article>
            <article className="control-metric"><span>Verified identities</span><strong>{agentsLoading ? '—' : verified}</strong><small>Tier 1 or higher</small></article>
            <article className="control-metric"><span>Selected operator context</span><strong className="metric-text">{selectedAgent?.alias || selectedAgent?.name || 'None'}</strong><small>{selectedAgent ? 'Drives treasury and policy views' : 'Select an agent below'}</small></article>
          </div>

          <FleetWalletOverview />

          <section className="control-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Registry</span><h2>Registered identities</h2></div><span className="control-count">{agents.length} total</span></div>
            {agents.length === 0 ? (
              <div className="control-empty">No registered agents were returned by the Oracle. Open Identity & verification to enroll one.</div>
            ) : (
              <div className="agent-card-grid">
                {agents.map((agent) => {
                  const active = selectedAgent?.id === agent.id;
                  return (
                    <button key={agent.id} className={`agent-control-card${active ? ' selected' : ''}`} onClick={() => setSelectedAgent(agent)}>
                      <div className="agent-control-card-top"><span className="agent-avatar"><Users size={17} /></span>{active && <span className="control-state good">Active context</span>}</div>
                      <strong>{agent.alias || agent.name || 'Unnamed agent'}</strong>
                      <code title={agent.id}>{agent.id}</code>
                      <div className="agent-control-meta"><span><BadgeCheck size={13} /> Tier {agent.verification_tier}</span><span>AIS {agent.current_ais?.toFixed(0) ?? '—'}</span><span>{agent.staked_itk?.toLocaleString() ?? '—'} ITK staked</span></div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
          {selectedAgent && <section className="control-section agent-intelligence-section"><div className="control-section-heading"><div><span className="control-eyebrow">Behavioral intelligence</span><h2>Selected agent integrity & risk vectors</h2></div><button onClick={() => setTab('identity')}>Inspect identity</button></div><div className="agent-radar-layout"><div><h3>{selectedAgent.alias || selectedAgent.name || 'Selected agent'}</h3><code>{selectedAgent.id}</code><p>The same live AIS vectors used by policy and capital gates are presented here beside identity management. Toggle the graph between integrity and risk views.</p></div><IntegrityRadar agent={selectedAgent} /></div></section>}
        </div>
      ) : (
        <div className="control-page-body"><IdentityPanel /></div>
      )}
    </div>
  );
}
