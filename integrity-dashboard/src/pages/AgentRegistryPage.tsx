import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, ChevronRight, CircleAlert, Copy, Database, KeyRound, RefreshCw, Search, ShieldCheck, UsersRound } from 'lucide-react';
import { useDashboard, type Agent } from '../context/DashboardContext';
import './AgentRegistryPage.css';

type RegistryFilter = 'all' | 'writable' | 'read-only' | 'unavailable';

const short = (value?: string | null, start = 12, end = 8) => {
  if (!value) return 'Unavailable';
  if (value.length <= start + end + 1) return value;
  return `${value.slice(0, start)}…${value.slice(-end)}`;
};
const displayName = (agent: Agent) => agent.alias || agent.name || short(agent.id, 10, 6);

function StatusDot({ tone = 'neutral' }: { tone?: 'good' | 'warn' | 'neutral' }) {
  return <span className={`registry-status-dot ${tone}`} aria-hidden="true" />;
}

function StatusLabel({ agent }: { agent: Agent }) {
  if (agent.namespace_state === 'unavailable') return <span className="registry-status muted"><StatusDot /> Namespace unavailable</span>;
  if (agent.writable === false || agent.store_access === 'read_only') return <span className="registry-status warn"><StatusDot tone="warn" /> Read only</span>;
  return <span className="registry-status good"><StatusDot tone="good" /> Writable</span>;
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1400); } catch { setCopied(false); }
  };
  return <button className="registry-icon-button" type="button" onClick={copy} aria-label={copied ? `${label} copied` : `Copy ${label}`} title={copied ? 'Copied' : `Copy ${label}`}>{copied ? <Check size={14} /> : <Copy size={14} />}</button>;
}

function DetailRow({ label, value, mono = false, copyable = false }: { label: string; value: string; mono?: boolean; copyable?: boolean }) {
  return <div className="registry-detail-row"><span>{label}</span><div className="registry-detail-value"><strong className={mono ? 'mono' : ''} title={value}>{value}</strong>{copyable && value !== 'Unavailable' && <CopyButton value={value} label={label} />}</div></div>;
}

function AgentRow({ agent, selected, onSelect }: { agent: Agent; selected: boolean; onSelect: () => void }) {
  return <button className={`registry-agent-row${selected ? ' selected' : ''}`} type="button" onClick={onSelect} aria-pressed={selected}>
    <span className="registry-avatar">{displayName(agent).slice(0, 2).toUpperCase()}</span>
    <span className="registry-agent-main"><strong>{displayName(agent)}</strong><small>{agent.profile_id ? `Profile ${agent.profile_id}` : short(agent.id)}</small></span>
    <span className="registry-row-state"><StatusLabel agent={agent} /></span>
    <span className="registry-row-score">{agent.current_ais != null ? agent.current_ais.toFixed(1) : '—'}<small>AIS</small></span>
    <ChevronRight className="registry-row-chevron" size={16} aria-hidden="true" />
  </button>;
}

export function AgentRegistryPage() {
  const { agents, selectedAgent, setSelectedAgent, agentsLoading } = useDashboard();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<RegistryFilter>('all');
  const [refreshing, setRefreshing] = useState(false);
  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return agents.filter(agent => {
      const writable = agent.writable !== false && agent.store_access !== 'read_only';
      const matchesFilter = filter === 'all' || (filter === 'writable' && writable) || (filter === 'read-only' && !writable) || (filter === 'unavailable' && agent.namespace_state === 'unavailable');
      if (!matchesFilter) return false;
      if (!normalizedQuery) return true;
      return [displayName(agent), agent.id, agent.profile_id, agent.store_id, agent.namespace_key].filter(Boolean).some(value => String(value).toLowerCase().includes(normalizedQuery));
    });
  }, [agents, filter, query]);
  const selected = selectedAgent && filteredAgents.some(agent => (agent.namespace_key || agent.id) === (selectedAgent.namespace_key || selectedAgent.id)) ? selectedAgent : filteredAgents[0] || selectedAgent || null;
  const refresh = () => { setRefreshing(true); window.dispatchEvent(new Event('integrity-auth-changed')); window.setTimeout(() => setRefreshing(false), 900); };
  const writableCount = agents.filter(agent => agent.writable !== false && agent.store_access !== 'read_only').length;
  const readOnlyCount = agents.length - writableCount;

  return <div className="registry-page">
    <section className="registry-hero"><div><span className="registry-kicker">Identity & workspace scope</span><h1>Agent registry</h1><p>Review the agent namespaces available to this workspace and choose the identity that anchors your next operation.</p></div><div className="registry-hero-actions"><button className="registry-secondary-button" type="button" onClick={refresh} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'registry-spin' : ''} /> {refreshing ? 'Refreshing' : 'Refresh registry'}</button><Link className="registry-primary-button" to="/dashboard">Open command center <ArrowUpRight size={15} /></Link></div></section>
    <section className="registry-summary" aria-label="Registry summary"><div><span>Total namespaces</span><strong>{agentsLoading ? '—' : agents.length}</strong><small>Visible to this session</small></div><div><span>Writable</span><strong className="good-text">{agentsLoading ? '—' : writableCount}</strong><small>Can accept scoped writes</small></div><div><span>Read only</span><strong className="warn-text">{agentsLoading ? '—' : readOnlyCount}</strong><small>Inspection only</small></div><div><span>Source</span><strong className="summary-source"><Database size={15} /> Cortex</strong><small>Authenticated namespace projection</small></div></section>
    <div className="registry-workspace"><section className="registry-list-panel" aria-label="Agent namespaces"><div className="registry-panel-heading"><div><span className="registry-panel-label">Available identities</span><h2>Namespaces</h2></div><span className="registry-count">{filteredAgents.length} shown</span></div><div className="registry-toolbar"><label className="registry-search"><Search size={15} /><span className="sr-only">Search namespaces</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name, DID, or profile" /></label><div className="registry-filters" role="group" aria-label="Filter namespaces">{(['all', 'writable', 'read-only', 'unavailable'] as RegistryFilter[]).map(option => <button key={option} type="button" className={filter === option ? 'active' : ''} onClick={() => setFilter(option)}>{option === 'all' ? 'All' : option === 'read-only' ? 'Read only' : option[0].toUpperCase() + option.slice(1)}</button>)}</div></div><div className="registry-list">{agentsLoading && <div className="registry-empty"><RefreshCw size={18} className="registry-spin" /><span>Loading scoped namespaces…</span></div>}{!agentsLoading && filteredAgents.map(agent => <AgentRow key={agent.namespace_key || agent.id} agent={agent} selected={(selected?.namespace_key || selected?.id) === (agent.namespace_key || agent.id)} onSelect={() => setSelectedAgent(agent)} />)}{!agentsLoading && filteredAgents.length === 0 && <div className="registry-empty"><CircleAlert size={18} /><span>{agents.length ? 'No namespaces match this filter.' : 'No authenticated agent namespaces are available.'}</span></div>}</div><div className="registry-list-foot"><ShieldCheck size={14} /> Registry visibility follows the authenticated workspace scope.</div></section>
      <aside className="registry-detail-panel" aria-label="Selected agent details">{selected ? <><div className="registry-detail-heading"><div className="registry-detail-title"><span className="registry-avatar large">{displayName(selected).slice(0, 2).toUpperCase()}</span><div><span className="registry-panel-label">Selected namespace</span><h2>{displayName(selected)}</h2></div></div><StatusLabel agent={selected} /></div><p className="registry-detail-intro">This identity is the active scope for dashboard reads and downstream Cortex views.</p><div className="registry-detail-block"><DetailRow label="Agent DID" value={selected.id} mono copyable /><DetailRow label="Workspace" value={selected.store_id || 'Unavailable'} mono copyable /><DetailRow label="Profile" value={selected.profile_id || 'Unavailable'} mono /><DetailRow label="Verification tier" value={selected.verification_tier ? `Tier ${selected.verification_tier}` : 'Not reported'} /></div><div className="registry-detail-status"><div className="registry-detail-status-icon"><KeyRound size={17} /></div><div><strong>{selected.writable === false || selected.store_access === 'read_only' ? 'Read-only access' : 'Scoped write access'}</strong><span>{selected.writable === false || selected.store_access === 'read_only' ? 'Changes require a writable namespace.' : 'Writes remain subject to downstream authority checks.'}</span></div></div><div className="registry-detail-actions"><button className="registry-primary-button" type="button" onClick={() => setSelectedAgent(selected)}><Check size={15} /> Use this namespace</button><Link className="registry-secondary-button" to="/dashboard">View identity evidence <ArrowUpRight size={14} /></Link></div></> : <div className="registry-empty detail-empty"><UsersRound size={22} /><strong>Select an agent namespace</strong><span>Details and scope controls will appear here.</span></div>}</aside>
    </div>
  </div>;
}
