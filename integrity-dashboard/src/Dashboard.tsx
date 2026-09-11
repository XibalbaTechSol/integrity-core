import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ethers } from 'ethers';
import { ArrowRight, BadgeCheck, BrainCircuit, Code, Database, ExternalLink, FileCheck2, Fingerprint, Landmark, Network, RefreshCw, ShieldCheck, Users, WalletCards } from 'lucide-react';
import { useDashboard } from './context/DashboardContext';
import { ControlHeader } from './components/control/ControlHeader';
import { oracle, type AisResponse, type IntentOutcomeDto, type StatsDto, type AuditLogEntryDto } from './services/oracle';
import { graphMemory, type AgentMemorySummary, type InvocationCorrelation } from './services/graphMemory';
import { shieldBackend, type ShieldDashboardSummary } from './services/shieldBackend';
import { GRAPH_MEMORY_URL, SHIELD_BACKEND_URL, SHIELD_TENANT_ID } from './config';

type ServiceState = { state: 'checking' | 'online' | 'degraded' | 'offline'; detail: string };
const initialService: ServiceState = { state: 'checking', detail: 'Checking connection' };
const fromWei = (value?: string | null) => { if (!value) return null; try { return Number(ethers.formatEther(value)); } catch { return null; } };
const formatItk = (value: number | null) => value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const shortId = (value: string) => value.length > 30 ? `${value.slice(0, 14)}…${value.slice(-10)}` : value;

export default function Dashboard() {
  const { agents, agentsLoading, selectedAgent, stats, walletAddress, connectWallet } = useDashboard();
  const [services, setServices] = useState<Record<'core' | 'shield' | 'cortex', ServiceState>>({ core: initialService, shield: initialService, cortex: initialService });
  const [protocol, setProtocol] = useState<StatsDto | null>(null);
  const [invocations, setInvocations] = useState<InvocationCorrelation[]>([]);
  const [audit, setAudit] = useState<AuditLogEntryDto[]>([]);
  const [reconciliation, setReconciliation] = useState<IntentOutcomeDto[]>([]);
  const [shieldSummary, setShieldSummary] = useState<ShieldDashboardSummary | null>(null);
  const [agentMemory, setAgentMemory] = useState<AgentMemorySummary | null>(null);
  const [selectedAis, setSelectedAis] = useState<AisResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    const [core, shield, cortex, invocationsResult] = await Promise.allSettled([oracle.getStats(), shieldBackend.health(), graphMemory.status(), graphMemory.invocations(8)]);
    setServices({
      core: core.status === 'fulfilled' ? { state: 'online', detail: 'Oracle and on-chain read model responding' } : { state: 'offline', detail: 'Oracle API unavailable' },
      shield: shield.status === 'fulfilled' && shield.value.ok ? { state: 'online', detail: 'External enforcement system responding' } : { state: 'offline', detail: 'Shield backend unavailable' },
      // The protocol-surface counter measures reachability, not the optional
      // full-store integrity scan. Cortex deliberately reports
      // "skipped (fast mode)" for a healthy low-latency status check; treating
      // that diagnostic as offline made a live Cortex API render as 2/3 online.
      cortex: cortex.status === 'fulfilled' ? { state: 'online', detail: `${cortex.value.memory_count} memories · integrity ${cortex.value.integrity_check}` } : { state: 'offline', detail: 'Cortex local API unavailable' },
    });
    setProtocol(core.status === 'fulfilled' ? core.value : null);
    setInvocations(invocationsResult.status === 'fulfilled' ? invocationsResult.value : []);
    setRefreshing(false);
  }, []);
  useEffect(() => { void loadOverview(); }, [loadOverview]);
  useEffect(() => {
    if (!selectedAgent) { setAudit([]); setReconciliation([]); setShieldSummary(null); setAgentMemory(null); setSelectedAis(null); return; }
    let active = true;
    // Agent 360 needs bounded Cortex aggregates; the full memory list belongs
    // to the Cortex workspace. Passing zero avoids sorting a large profile just
    // to render three preview cards here.
    const shieldTenant = SHIELD_TENANT_ID || selectedAgent.eth_address;
    Promise.allSettled([oracle.getAuditLog(selectedAgent.id, 8), oracle.getReconciliation(selectedAgent.id), shieldBackend.dashboardSummary(shieldTenant), oracle.getAis(selectedAgent.id), graphMemory.agentSummary(selectedAgent.id, 0)]).then(([auditResult, reconciliationResult, shieldResult, aisResult, memoryResult]) => {
      if (!active) return;
      setAudit(auditResult.status === 'fulfilled' ? auditResult.value : []);
      setReconciliation(reconciliationResult.status === 'fulfilled' ? reconciliationResult.value : []);
      setShieldSummary(shieldResult.status === 'fulfilled' ? shieldResult.value : null);
      setAgentMemory(memoryResult.status === 'fulfilled' ? memoryResult.value : null);
      setSelectedAis(aisResult.status === 'fulfilled' ? aisResult.value : null);
    });
    return () => { active = false; };
  }, [selectedAgent?.id, selectedAgent?.eth_address]);

  const deniedActions = audit.filter(entry => entry.decision.toLowerCase().includes('deny'));
  const unresolved = reconciliation.filter(entry => entry.status !== 'reconciled');
  const pendingActions = deniedActions.length + unresolved.length;
  const onlineServices = Object.values(services).filter(service => service.state === 'online').length;
  const reconciledCount = reconciliation.filter(entry => entry.status === 'reconciled').length;
  const fleetBalance = useMemo(() => agents.reduce((sum, agent) => sum + (agent.staked_itk ?? 0), 0), [agents]);

  return <div className="control-page command-center protocol-overview">
    <ControlHeader eyebrow="Integrity protocol" title="Protocol overview" description="A verifiable path from agent identity to policy decision and signed outcome." actions={<><button className="control-secondary-action" onClick={() => void loadOverview()} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spin' : undefined} /> Refresh</button><Link className="control-primary-action" to="/agents"><Users size={15} /> Manage agents</Link></>} />
    <div className="command-status-bar protocol-status" aria-label="Protocol status">
      {(['core', 'shield', 'cortex'] as const).map(name => { const Icon = name === 'core' ? Network : name === 'shield' ? ShieldCheck : BrainCircuit; const label = name === 'core' ? 'Integrity Core' : name === 'shield' ? 'Shield' : 'Cortex'; const service = services[name]; const href = name === 'shield' ? SHIELD_BACKEND_URL : name === 'cortex' ? GRAPH_MEMORY_URL : '/wiki'; return <a className="service-status" href={href} target={name === 'core' ? undefined : '_blank'} rel={name === 'core' ? undefined : 'noreferrer'} key={name}><span className={`service-icon ${service.state}`}><Icon size={16} /></span><div><strong>{label}</strong><small>{service.detail}</small></div><span className={`control-state ${service.state}`}>{service.state}</span></a>; })}
      <div className="service-summary"><strong>{onlineServices}/3</strong><small>protocol surfaces online</small></div>
    </div>
    <div className="control-page-body protocol-body">
      <div className="protocol-grid">
        <section className="control-section protocol-spine-section"><div className="control-section-heading"><div><span className="control-eyebrow">Visual backbone</span><h2>Protocol spine</h2></div><span className="protocol-caption">identity + score + policy + evidence</span></div>
          <div className="protocol-spine" aria-label="Agent identity to verified outcome"><div className="spine-node"><span><Fingerprint size={22} /></span><strong>Agent identity</strong><small>{agentsLoading ? 'Loading agents' : `${agents.length} registered`}</small></div><i /><div className="spine-node"><span><ShieldCheck size={22} /></span><strong>Integrity score</strong><small>{selectedAis ? `${selectedAis.ais.toFixed(0)} AIS · ${selectedAis.event_count} events` : 'Select an agent for live AIS'}</small></div><i /><div className="spine-node"><span><FileCheck2 size={22} /></span><strong>Policy decision</strong><small>{pendingActions ? `${pendingActions} items need review` : 'No blocked actions'}</small></div><i /><div className="spine-node"><span><BadgeCheck size={22} /></span><strong>Verified outcome</strong><small>{reconciledCount} reconciled · {unresolved.length} gaps</small></div></div>
          <div className="protocol-spine-footer"><span>Integrity Core</span><small>Every action remains attributable, policy-bound, and evidence-bearing.</small></div>
          <div className="external-systems"><span className="control-eyebrow">Connected systems</span><a href={SHIELD_BACKEND_URL} target="_blank" rel="noreferrer"><ShieldCheck size={17} /><span><strong>Shield</strong><small>Threat defence & enforcement</small></span><ExternalLink size={14} /></a><a href={GRAPH_MEMORY_URL} target="_blank" rel="noreferrer"><BrainCircuit size={17} /><span><strong>Cortex</strong><small>Intelligence & provenance</small></span><ExternalLink size={14} /></a></div>
        </section>
        <aside className="control-section attention-section"><div className="control-section-heading"><div><span className="control-eyebrow">Operator attention</span><h2>Review queue</h2></div><Link to="/security">Review <ArrowRight size={14} /></Link></div><div className="attention-summary"><span className={pendingActions ? 'warn' : 'good'}>{pendingActions}</span><div><strong>{pendingActions ? 'Items require review' : 'No blocked actions'}</strong><small>Selected agent: {selectedAgent ? selectedAgent.alias || selectedAgent.name || shortId(selectedAgent.id) : 'none'}</small></div></div><div className="attention-list">{deniedActions.slice(0, 3).map(entry => <article key={entry.id}><span className="attention-dot danger" /><div><strong>{entry.event_type}</strong><small>{entry.reason_code || entry.detail || 'Policy denied this action'}</small></div></article>)}{unresolved.slice(0, 2).map((entry, index) => <article key={entry.invocation_id || index}><span className="attention-dot warn" /><div><strong>{entry.intent_type || 'Invocation evidence'}</strong><small>{entry.status.replace(/_/g, ' ')}</small></div></article>)}{!pendingActions && <div className="control-empty compact"><BadgeCheck size={18} /> Current queues are clear.</div>}</div>{shieldSummary && <div className="attention-footer"><ShieldCheck size={14} /> {shieldSummary.device_count} Shield devices · {shieldSummary.decisions_by_action?.deny ?? shieldSummary.decisions_by_action?.block ?? 0} denied actions</div>}</aside>
      </div>
      <div className="protocol-lower-grid"><section className="control-section evidence-section"><div className="control-section-heading"><div><span className="control-eyebrow">Recent protocol events</span><h2>Evidence timeline</h2></div><Link to="/knowledge">View evidence <ArrowRight size={14} /></Link></div><div className="evidence-stats"><div><strong>{reconciledCount}</strong><span>Reconciled</span></div><div><strong>{unresolved.length}</strong><span>Evidence gaps</span></div><div><strong>{invocations.length}</strong><span>Runtime intents</span></div><div><strong>{shieldSummary?.latest_decisions.length ?? '—'}</strong><span>Shield decisions</span></div></div><div className="invocation-list">{invocations.slice(0, 5).map(item => <article key={item.invocation_id}><span className={`attention-dot ${item.runtime_status === 'complete' ? 'good' : 'warn'}`} /><div><strong>{item.tool_name || 'Agent action'}</strong><code>{item.pre_tool?.intent_rationale || shortId(item.invocation_id)}</code></div><span>{item.runtime_status.replace(/_/g, ' ')}</span></article>)}{!invocations.length && <div className="control-empty compact">No correlated runtime intents were returned.</div>}</div></section>
        <section className="control-section network-position-section"><div className="control-section-heading"><div><span className="control-eyebrow">Protocol context</span><h2>Network position</h2></div><Link to="/treasury">View funds <ArrowRight size={14} /></Link></div><div className="network-position"><div className="wallet-context"><span><WalletCards size={18} /></span><div><small>Connected operator wallet</small><strong>{walletAddress ? shortId(walletAddress) : 'Not connected'}</strong></div>{walletAddress ? <a href={`https://sepolia.basescan.org/address/${walletAddress}`} target="_blank" rel="noreferrer" aria-label="Open wallet on BaseScan"><ExternalLink size={15} /></a> : <button onClick={() => void connectWallet()}>Connect</button>}</div><div className="chain-stat-grid"><div><span>Agents</span><strong>{agents.length}</strong></div><div><span>Aggregate AIS</span><strong>{stats ? stats.aggregate_ais.toFixed(0) : '—'}</strong></div><div><span>ITK staked</span><strong>{formatItk(stats?.protocol_staked_itk ?? fromWei(String(fleetBalance)))}</strong></div><div><span>Markets</span><strong>{protocol?.market_count ?? '—'}</strong></div></div><div className="chain-note"><Landmark size={15} /><span>On-chain positions remain context for the protocol spine, not a separate command surface.</span></div></div></section></div>
      <section className="control-section agent-360-section"><div className="control-section-heading"><div><span className="control-eyebrow">Selected agent</span><h2>Agent 360</h2></div><span className="protocol-caption">Oracle + Shield + Cortex</span></div><div className="control-metric-grid compact"><div className="control-metric"><span>Cortex memories</span><strong>{agentMemory?.memories ?? '—'}</strong><small>{agentMemory?.embedded_memories == null ? 'Embedding coverage in Cortex workspace' : `${agentMemory.embedded_memories} embedded`}</small></div><div className="control-metric"><span>Cortex sessions</span><strong>{agentMemory?.sessions ?? '—'}</strong><small>{agentMemory ? `${agentMemory.sources} provenance sources` : 'Unavailable'}</small></div><div className="control-metric"><span>Shield devices</span><strong>{shieldSummary?.device_count ?? '—'}</strong><small>{shieldSummary ? `${Object.values(shieldSummary.decisions_by_action).reduce((sum, value) => sum + value, 0)} recorded decisions` : 'Unavailable'}</small></div><div className="control-metric"><span>Shield denied</span><strong>{shieldSummary ? (shieldSummary.decisions_by_action.deny ?? shieldSummary.decisions_by_action.block ?? 0) : '—'}</strong><small>{shieldSummary ? 'Server-recorded actions' : 'Unavailable'}</small></div></div><div className="agent-360-records">{agentMemory?.recent_memories.slice(0, 3).map(memory => <article key={memory.id}><span className="attention-dot good" /><div><strong>{memory.content.slice(0, 110)}{memory.content.length > 110 ? '…' : ''}</strong><small>{memory.source.kind} · {memory.evidence_class} · {memory.status}</small></div></article>)}{agentMemory && !agentMemory.recent_memories.length && <div className="control-empty compact">Open Cortex Evidence to inspect recent memories for this agent.</div>}{!agentMemory && <div className="control-empty compact">Cortex agent summary unavailable; no records are inferred.</div>}</div></section>
      <section className="control-shortcuts protocol-shortcuts" aria-label="Protocol surfaces"><Link to="/agents"><Fingerprint size={18} /><span><strong>Agents</strong><small>Identity and registration</small></span><ArrowRight size={15} /></Link><Link to="/security"><ShieldCheck size={18} /><span><strong>Policy</strong><small>Rules and gated actions</small></span><ArrowRight size={15} /></Link><Link to="/knowledge"><Database size={18} /><span><strong>Evidence</strong><small>Proof and reconciliation</small></span><ArrowRight size={15} /></Link><Link to="/developer"><Code size={18} /><span><strong>Build</strong><small>Integrations and tests</small></span><ArrowRight size={15} /></Link></section>
    </div>
  </div>;
}
