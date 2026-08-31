import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ethers } from 'ethers';
import { Line, LineChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts';
import {
  Activity, ArrowRight, BadgeCheck, BrainCircuit, CircleDollarSign, Database,
  ExternalLink, Fingerprint, Landmark, Network, RefreshCw, ShieldCheck,
  TriangleAlert, Users, WalletCards,
} from 'lucide-react';
import { useDashboard } from './context/DashboardContext';
import { ControlHeader } from './components/control/ControlHeader';
import { COTPlatform } from './components/COTPlatform';
import { oracle, type AisHistoryPoint, type AisResponse, type AuditLogEntryDto, type IntentOutcomeDto, type StatsDto } from './services/oracle';
import { graphMemory, type GraphMemoryStats, type InvocationCorrelation } from './services/graphMemory';
import { shieldBackend, type ShieldDashboardSummary } from './services/shieldBackend';

type ServiceState = { state: 'checking' | 'online' | 'degraded' | 'offline'; detail: string };
type FleetRow = { id: string; label: string; tier: number; ais: number | null; balance: number | null; staked: number | null; onchain: boolean | null };

const initialService: ServiceState = { state: 'checking', detail: 'Checking connection' };

function fromWei(value?: string | null): number | null {
  if (!value) return null;
  try { return Number(ethers.formatEther(value)); } catch { return null; }
}

function formatItk(value: number | null) {
  return value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function shortId(value: string) {
  return value.length > 30 ? `${value.slice(0, 14)}…${value.slice(-10)}` : value;
}

export default function Dashboard() {
  const { agents, agentsLoading, selectedAgent, setSelectedAgent, stats, walletAddress, connectWallet } = useDashboard();
  const [services, setServices] = useState<Record<'core' | 'shield' | 'cortex', ServiceState>>({ core: initialService, shield: initialService, cortex: initialService });
  const [fleet, setFleet] = useState<FleetRow[]>([]);
  const [protocol, setProtocol] = useState<StatsDto | null>(null);
  const [knowledge, setKnowledge] = useState<GraphMemoryStats | null>(null);
  const [invocations, setInvocations] = useState<InvocationCorrelation[]>([]);
  const [audit, setAudit] = useState<AuditLogEntryDto[]>([]);
  const [reconciliation, setReconciliation] = useState<IntentOutcomeDto[]>([]);
  const [shieldSummary, setShieldSummary] = useState<ShieldDashboardSummary | null>(null);
  const [selectedAis, setSelectedAis] = useState<AisResponse | null>(null);
  const [aisHistory, setAisHistory] = useState<AisHistoryPoint[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    const [coreResult, shieldResult, cortexStatusResult, cortexStatsResult, invocationResult] = await Promise.allSettled([
      oracle.getStats(), shieldBackend.health(), graphMemory.status(), graphMemory.stats(), graphMemory.invocations(8),
    ]);
    setServices({
      core: coreResult.status === 'fulfilled' ? { state: 'online', detail: 'Oracle and on-chain read model responding' } : { state: 'offline', detail: 'Oracle API unavailable' },
      shield: shieldResult.status === 'fulfilled' && shieldResult.value.ok ? { state: 'online', detail: 'Endpoint control plane responding' } : { state: 'offline', detail: 'Shield backend unavailable' },
      cortex: cortexStatusResult.status === 'fulfilled'
        ? { state: cortexStatusResult.value.integrity_check === 'ok' ? 'online' : 'degraded', detail: `${cortexStatusResult.value.memory_count} memories · integrity ${cortexStatusResult.value.integrity_check}` }
        : { state: 'offline', detail: 'Cortex local API unavailable' },
    });
    setProtocol(coreResult.status === 'fulfilled' ? coreResult.value : null);
    setKnowledge(cortexStatsResult.status === 'fulfilled' ? cortexStatsResult.value : null);
    setInvocations(invocationResult.status === 'fulfilled' ? invocationResult.value : []);

    if (agents.length) {
      const rows = await Promise.all(agents.map(async (agent): Promise<FleetRow> => {
        const [wallet, ais, stake, detail] = await Promise.allSettled([
          oracle.getWallet(agent.eth_address), oracle.getAis(agent.eth_address), oracle.getStake(agent.eth_address), oracle.getAgent(agent.eth_address),
        ]);
        return {
          id: agent.id,
          label: agent.alias || agent.name || agent.id,
          tier: agent.verification_tier,
          ais: ais.status === 'fulfilled' ? ais.value.ais : agent.current_ais ?? null,
          balance: wallet.status === 'fulfilled' ? fromWei(wallet.value.itk_balance) : null,
          staked: stake.status === 'fulfilled' ? fromWei(stake.value.total_stake) : agent.staked_itk ?? null,
          onchain: detail.status === 'fulfilled' ? Boolean(detail.value.primitives) : null,
        };
      }));
      setFleet(rows);
    } else setFleet([]);
    setRefreshing(false);
  }, [agents]);

  useEffect(() => { void loadOverview(); }, [loadOverview]);

  useEffect(() => {
    if (!selectedAgent) { setAudit([]); setReconciliation([]); setShieldSummary(null); setSelectedAis(null); setAisHistory([]); return; }
    let active = true;
    Promise.allSettled([
      oracle.getAuditLog(selectedAgent.id, 8), oracle.getReconciliation(selectedAgent.id), shieldBackend.dashboardSummary(selectedAgent.eth_address), oracle.getAis(selectedAgent.id), oracle.getAisHistory(selectedAgent.id, '1h'),
    ]).then(([auditResult, reconciliationResult, shieldResult, aisResult, historyResult]) => {
      if (!active) return;
      setAudit(auditResult.status === 'fulfilled' ? auditResult.value : []);
      setReconciliation(reconciliationResult.status === 'fulfilled' ? reconciliationResult.value : []);
      setShieldSummary(shieldResult.status === 'fulfilled' ? shieldResult.value : null);
      setSelectedAis(aisResult.status === 'fulfilled' ? aisResult.value : null);
      setAisHistory(historyResult.status === 'fulfilled' ? historyResult.value : []);
    });
    return () => { active = false; };
  }, [selectedAgent?.id, selectedAgent?.eth_address]);

  const totalFleetBalance = useMemo(() => fleet.reduce((sum, row) => sum + (row.balance ?? 0), 0), [fleet]);
  const registeredOnchain = fleet.filter((row) => row.onchain).length;
  const deniedActions = audit.filter((entry) => entry.decision.toLowerCase().includes('deny'));
  const unresolved = reconciliation.filter((entry) => entry.status !== 'reconciled');
  const shieldDenials = shieldSummary?.decisions_by_action?.deny ?? shieldSummary?.decisions_by_action?.block ?? 0;
  const pendingActions = deniedActions.length + unresolved.length;
  const onlineServices = Object.values(services).filter((service) => service.state === 'online').length;
  const reconciledCount = reconciliation.filter((entry) => entry.status === 'reconciled').length;
  const aisComponents = selectedAis ? [
    ['Entropy', selectedAis.components.entropy],
    ['Grounding', selectedAis.components.grounding],
    ['Sacrifice', selectedAis.components.sacrifice],
    ['Compliance', selectedAis.components.compliance],
  ] as const : [];

  return (
    <div className="control-page command-center">
      <ControlHeader
        eyebrow="Xibalba control plane"
        title="Command Overview"
        description="One operational view across Integrity Core, Shield enforcement, Cortex knowledge, agent identities, and on-chain capital."
        actions={<><button className="control-secondary-action" onClick={() => void loadOverview()} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spin' : undefined} /> Refresh</button><Link className="control-primary-action" to="/agents"><Users size={15} /> Manage agents</Link></>}
      />

      <div className="command-status-bar" aria-label="System service status">
        {(['core', 'shield', 'cortex'] as const).map((name) => {
          const Icon = name === 'core' ? Network : name === 'shield' ? ShieldCheck : BrainCircuit;
          const label = name === 'core' ? 'Integrity Core' : name === 'shield' ? 'Shield' : 'Cortex';
          const service = services[name];
          return <div className="service-status" key={name}><span className={`service-icon ${service.state}`}><Icon size={16} /></span><div><strong>{label}</strong><small>{service.detail}</small></div><span className={`control-state ${service.state}`}>{service.state}</span></div>;
        })}
        <div className="service-summary"><strong>{onlineServices}/3</strong><small>systems online</small></div>
      </div>

      <div className="control-page-body">
        <section className="control-metric-grid">
          <article className="control-metric"><span><Users size={14} /> Registered agents</span><strong>{agentsLoading ? '—' : agents.length}</strong><small>{registeredOnchain} with on-chain primitives</small></article>
          <article className="control-metric"><span><CircleDollarSign size={14} /> Fleet ITK balance</span><strong>{formatItk(totalFleetBalance)}</strong><small>{formatItk(stats?.protocol_staked_itk ?? null)} ITK staked</small></article>
          <article className="control-metric"><span><Activity size={14} /> Network AIS</span><strong>{stats ? stats.aggregate_ais.toFixed(1) : '—'}</strong><small>Live aggregate across registered agents</small></article>
          <article className={`control-metric${pendingActions ? ' attention' : ''}`}><span><TriangleAlert size={14} /> Review queue</span><strong>{pendingActions}</strong><small>{deniedActions.length} policy denials · {unresolved.length} evidence gaps</small></article>
        </section>

        <div className="command-grid-primary">
          <section className="control-section fleet-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Fleet</span><h2>Agents under management</h2></div><Link to="/agents">Open fleet <ArrowRight size={14} /></Link></div>
            {fleet.length === 0 ? <div className="control-empty">{agentsLoading ? 'Loading the registered fleet…' : 'No registered agents. Open Agents & Identity to enroll one.'}</div> : (
              <div className="fleet-table-wrap"><table className="fleet-table"><thead><tr><th>Agent / DID</th><th>Identity</th><th>AIS</th><th>ITK balance</th><th>Staked</th><th /></tr></thead><tbody>{fleet.map((row) => <tr key={row.id} className={selectedAgent?.id === row.id ? 'selected' : undefined}><td><strong title={row.label}>{row.label}</strong><code title={row.id}>{shortId(row.id)}</code></td><td><span className={`control-state ${row.onchain ? 'online' : row.onchain === false ? 'degraded' : 'checking'}`}>{row.onchain ? 'On-chain' : row.onchain === false ? 'DID only' : 'Unknown'}</span></td><td>{row.ais?.toFixed(0) ?? '—'}</td><td>{formatItk(row.balance)}</td><td>{formatItk(row.staked)}</td><td><button onClick={() => { const match = agents.find((agent) => agent.id === row.id); if (match) setSelectedAgent(match); }}>Select</button></td></tr>)}</tbody></table></div>
            )}
          </section>

          <aside className="control-section attention-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Operator attention</span><h2>Gated actions</h2></div><Link to="/security">Review <ArrowRight size={14} /></Link></div>
            <div className="attention-summary"><span className={pendingActions ? 'warn' : 'good'}>{pendingActions}</span><div><strong>{pendingActions ? 'Items require review' : 'No blocked actions'}</strong><small>Selected agent: {selectedAgent ? selectedAgent.alias || selectedAgent.name || shortId(selectedAgent.id) : 'none'}</small></div></div>
            <div className="attention-list">
              {deniedActions.slice(0, 3).map((entry) => <article key={entry.id}><span className="attention-dot danger" /><div><strong>{entry.event_type}</strong><small>{entry.reason_code || entry.detail || 'Policy denied this action'}</small></div><time>{new Date(entry.created_at).toLocaleTimeString()}</time></article>)}
              {unresolved.slice(0, 2).map((entry, index) => <article key={entry.invocation_id || index}><span className="attention-dot warn" /><div><strong>{entry.intent_type || 'Invocation evidence'}</strong><small>{entry.status.replace(/_/g, ' ')}</small></div></article>)}
              {!pendingActions && <div className="control-empty compact"><BadgeCheck size={18} /> Current policy and evidence queues are clear.</div>}
            </div>
            {shieldSummary && <div className="attention-footer"><ShieldCheck size={14} /> {shieldSummary.device_count} Shield devices · {shieldDenials} denied actions recorded</div>}
          </aside>
        </div>

        <div className="command-grid-secondary">
          <section className="control-section ais-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Integrity metrics</span><h2>Agent Integrity Score</h2></div><Link to="/intelligence">Full intelligence <ArrowRight size={14} /></Link></div>
            <div className="ais-control-body">
              <div className="ais-primary-score"><span>Current AIS</span><strong>{selectedAis ? selectedAis.ais.toFixed(1) : '—'}</strong><small>{selectedAgent ? selectedAgent.alias || selectedAgent.name || shortId(selectedAgent.id) : 'No agent selected'} · {selectedAis?.event_count ?? 0} scored events</small></div>
              <div className="ais-mini-chart" aria-label="AIS trend graph">
                {aisHistory.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={aisHistory}><XAxis dataKey="bucket_start" hide /><YAxis domain={[0, 1000]} hide /><ChartTooltip contentStyle={{ background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: 5, fontSize: 11 }} labelFormatter={(value) => new Date(String(value)).toLocaleTimeString()} formatter={(value) => [Number(value).toFixed(1), 'AIS']} /><Line type="monotone" dataKey="ais" stroke="var(--success)" strokeWidth={2} dot={false} activeDot={{ r: 3 }} /></LineChart></ResponsiveContainer> : <div className="chart-empty">AIS trend appears after scored history is recorded.</div>}
              </div>
              <div className="ais-component-list">
                {aisComponents.map(([label, value]) => <div key={label}><div><span>{label}</span><strong>{value.toFixed(0)}</strong></div><span className="ais-track"><i style={{ width: `${Math.min(100, Math.max(0, value / 10))}%` }} /></span></div>)}
                {!selectedAis && <div className="control-empty compact">No AIS reading is available for the selected agent.</div>}
              </div>
              <div className="ais-flags"><span className={`control-state ${selectedAis?.zk_proof_verified ? 'online' : 'checking'}`}>ZK proof {selectedAis?.zk_proof_verified ? 'verified' : 'not verified'}</span><span className={`control-state ${selectedAis?.onchain_zk_boost_consistent === true ? 'online' : selectedAis?.onchain_zk_boost_consistent === false ? 'offline' : 'checking'}`}>On-chain boost {selectedAis?.onchain_zk_boost_consistent == null ? 'unknown' : selectedAis.onchain_zk_boost_consistent ? 'consistent' : 'mismatch'}</span></div>
            </div>
          </section>

          <section className="control-section evidence-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Correlation</span><h2>Intent → policy → outcome</h2></div><Link to="/knowledge">Open evidence <ArrowRight size={14} /></Link></div>
            <div className="evidence-stats"><div><strong>{reconciledCount}</strong><span>Reconciled</span></div><div><strong>{unresolved.length}</strong><span>Evidence gaps</span></div><div><strong>{invocations.length}</strong><span>Runtime intents</span></div><div><strong>{shieldSummary?.latest_decisions.length ?? '—'}</strong><span>Shield decisions</span></div></div>
            <div className="evidence-flow" aria-label="Evidence correlation flow">
              <div><span className={`flow-node ${services.cortex.state}`}><BrainCircuit size={15} /></span><strong>Cortex</strong><small>{invocations.length} intents</small></div><i />
              <div><span className={`flow-node ${services.shield.state}`}><ShieldCheck size={15} /></span><strong>Shield</strong><small>{shieldSummary?.latest_decisions.length ?? '—'} decisions</small></div><i />
              <div><span className={`flow-node ${services.core.state}`}><Network size={15} /></span><strong>BCC / Kernel</strong><small>{reconciliation.length} records</small></div><i />
              <div><span className={`flow-node ${unresolved.length ? 'degraded' : 'online'}`}><BadgeCheck size={15} /></span><strong>Outcome</strong><small>{reconciledCount} reconciled</small></div>
            </div>
            <div className="invocation-list">
              {invocations.slice(0, 4).map((item) => <article key={`evidence-${item.invocation_id}`}><span className={`attention-dot ${item.runtime_status === 'complete' ? 'good' : 'warn'}`} /><div><strong>{item.tool_name || 'Agent action'}</strong><code>{item.pre_tool?.intent_rationale || shortId(item.invocation_id)}</code></div><span>{item.runtime_status.replace(/_/g, ' ')}</span></article>)}
              {!invocations.length && <div className="control-empty compact">No correlated runtime intents were returned by Cortex.</div>}
            </div>
          </section>

          <section className="control-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">Knowledge</span><h2>Cortex operating context</h2></div><Link to="/knowledge">Explore <ArrowRight size={14} /></Link></div>
            <div className="knowledge-stats"><div><strong>{knowledge?.memories ?? '—'}</strong><span>Memories</span></div><div><strong>{knowledge?.entities ?? '—'}</strong><span>Entities</span></div><div><strong>{knowledge?.relations ?? '—'}</strong><span>Relations</span></div><div><strong>{knowledge?.sessions ?? '—'}</strong><span>Sessions</span></div></div>
            <div className="invocation-list">
              {invocations.slice(0, 4).map((item) => <article key={item.invocation_id}><span className={`attention-dot ${item.runtime_status === 'complete' ? 'good' : 'warn'}`} /><div><strong>{item.tool_name || 'Agent invocation'}</strong><code>{shortId(item.invocation_id)}</code></div><span>{item.runtime_status.replace(/_/g, ' ')}</span></article>)}
              {!invocations.length && <div className="control-empty compact">No recent Cortex invocations were returned.</div>}
            </div>
          </section>

          <section className="control-section">
            <div className="control-section-heading"><div><span className="control-eyebrow">On-chain</span><h2>ITK network position</h2></div><Link to="/treasury">Manage funds <ArrowRight size={14} /></Link></div>
            <div className="chain-position">
              <div className="wallet-context"><span><WalletCards size={18} /></span><div><small>Connected operator wallet</small><strong>{walletAddress ? shortId(walletAddress) : 'Not connected'}</strong></div>{walletAddress ? <a href={`https://sepolia.basescan.org/address/${walletAddress}`} target="_blank" rel="noreferrer" aria-label="Open wallet on BaseScan"><ExternalLink size={15} /></a> : <button onClick={() => void connectWallet()}>Connect</button>}</div>
              <div className="chain-stat-grid"><div><span>Markets</span><strong>{protocol?.market_count ?? '—'}</strong></div><div><span>Marketplace volume</span><strong>{formatItk(fromWei(protocol?.total_marketplace_volume))} ITK</strong></div><div><span>Credit escrowed</span><strong>{formatItk(fromWei(protocol?.escrowed_credit))} ITK</strong></div><div><span>Allocations</span><strong>{protocol?.allocation_count ?? '—'}</strong></div></div>
              <div className="chain-note"><Landmark size={15} /><span>Balances and protocol positions are read from the Oracle’s Base Sepolia on-chain view. Missing reads remain explicit.</span></div>
            </div>
          </section>
        </div>

        <section className="control-section cot-section">
          <div className="control-section-heading"><div><span className="control-eyebrow">Reasoning observability</span><h2>Chain-of-Thought Explorer</h2></div><Link to="/knowledge">Knowledge & evidence <ArrowRight size={14} /></Link></div>
          <div className="cot-control-body"><COTPlatform /></div>
        </section>

        <section className="control-shortcuts" aria-label="Control panel shortcuts">
          <Link to="/agents"><Fingerprint size={18} /><span><strong>Identity</strong><small>DID, verification, XNS</small></span><ArrowRight size={15} /></Link>
          <Link to="/treasury"><Landmark size={18} /><span><strong>Funds & access</strong><small>ITK, stake, credit, allowances</small></span><ArrowRight size={15} /></Link>
          <Link to="/security"><ShieldCheck size={18} /><span><strong>Security</strong><small>Shield, policies, gated actions</small></span><ArrowRight size={15} /></Link>
          <Link to="/knowledge"><Database size={18} /><span><strong>Knowledge</strong><small>Cortex, intelligence, evidence</small></span><ArrowRight size={15} /></Link>
        </section>
      </div>
    </div>
  );
}
