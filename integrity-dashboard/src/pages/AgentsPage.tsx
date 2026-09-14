import { useEffect, useMemo, useState } from 'react';
import { BadgeCheck, KeyRound, ShieldQuestion, UserRoundCog, Users, WalletCards } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import { FleetWalletOverview } from '../components/ui/FleetWalletOverview';
import { IdentityPanel } from '../components/tabs/IdentityPanel';
import { IntegrityRadar } from '../components/shared/IntegrityRadar';
import { oracle, type UnregisteredAgentDto } from '../services/oracle';

// Shortens a DID for display, matching integrity_sdk.agent_identity._short_did exactly so a
// DID reads the same way here as it does in Cortex's and Shield's own UIs.
function shortDid(did: string): string {
  return did.length <= 24 ? did : `${did.slice(0, 14)}…${did.slice(-8)}`;
}

function shortAddress(address: string): string {
  return address.length <= 12 ? address : `${address.slice(0, 6)}…${address.slice(-4)}`;
}

type AgentTab = 'fleet' | 'identity';

const TABS: ControlTab<AgentTab>[] = [
  { id: 'fleet', label: 'Agent fleet', icon: Users },
  { id: 'identity', label: 'Identity & verification', icon: KeyRound },
];

export default function AgentsPage() {
  const { agents, selectedAgent, setSelectedAgent, agentsLoading } = useDashboard();
  const [tab, setTab] = useState<AgentTab>('fleet');
  const verified = useMemo(() => agents.filter((agent) => agent.verification_tier > 0).length, [agents]);

  // The "off-chain but known" half of the on-chain/off-chain identity standard (2026-09-13,
  // same contract Cortex/Shield use via integrity_sdk.agent_identity): DIDs seen in telemetry
  // or the audit log that were never registered here. Every `agents` entry above is on-chain
  // by construction (it came from the oracle's own registered-agents list) -- this panel is
  // the only place that distinction becomes visible rather than implicit.
  const [unregistered, setUnregistered] = useState<UnregisteredAgentDto[]>([]);
  useEffect(() => {
    let active = true;
    oracle.getUnregisteredAgents().then((rows) => { if (active) setUnregistered(rows); }).catch(() => { if (active) setUnregistered([]); });
    return () => { active = false; };
  }, []);

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
                      <strong>{agent.alias || agent.name || shortDid(agent.id)}</strong>
                      <code title={agent.id}>{agent.id}</code>
                      {/* Every entry here came from the oracle's registered-agents list, so
                          on-chain is always true -- shown explicitly rather than left implicit,
                          per the identity standard. */}
                      <div className="agent-control-meta"><span className="control-state good">On-chain</span><span><BadgeCheck size={13} /> Tier {agent.verification_tier}</span><span>AIS {agent.current_ais?.toFixed(0) ?? '—'}</span><span>{agent.staked_itk?.toLocaleString() ?? '—'} ITK staked</span></div>
                      {agent.controller && <div className="agent-control-meta"><span title={agent.controller}><WalletCards size={13} /> {shortAddress(agent.controller)}</span></div>}
                    </button>
                  );
                })}
              </div>
            )}
          </section>
          {unregistered.length > 0 && (
            <section className="control-section">
              <div className="control-section-heading"><div><span className="control-eyebrow">Known, unregistered</span><h2>Off-chain agents</h2></div><span className="control-count">{unregistered.length} total</span></div>
              <p className="control-hint">DIDs with real telemetry or audit evidence that have never been registered with this oracle -- shown so their status is explicit, not silently absent from the registry above.</p>
              <div className="agent-card-grid">
                {unregistered.map((row) => (
                  <div className="agent-control-card" key={row.agent_id}>
                    <div className="agent-control-card-top"><span className="agent-avatar"><ShieldQuestion size={17} /></span><span className="control-state offline">Off-chain</span></div>
                    <strong>{shortDid(row.agent_id)}</strong>
                    <code title={row.agent_id}>{row.agent_id}</code>
                    <div className="agent-control-meta"><span>First seen via {row.source}</span><span>{new Date(row.first_seen).toLocaleDateString()}</span></div>
                  </div>
                ))}
              </div>
            </section>
          )}
          {selectedAgent && <section className="control-section agent-intelligence-section"><div className="control-section-heading"><div><span className="control-eyebrow">Behavioral intelligence</span><h2>Selected agent integrity & risk vectors</h2></div><button onClick={() => setTab('identity')}>Inspect identity</button></div><div className="agent-radar-layout"><div><h3>{selectedAgent.alias || selectedAgent.name || 'Selected agent'}</h3><code>{selectedAgent.id}</code><p>The same live AIS vectors used by policy and capital gates are presented here beside identity management. Toggle the graph between integrity and risk views.</p></div><IntegrityRadar agent={selectedAgent} /></div></section>}
        </div>
      ) : (
        <div className="control-page-body"><IdentityPanel /></div>
      )}
    </div>
  );
}
