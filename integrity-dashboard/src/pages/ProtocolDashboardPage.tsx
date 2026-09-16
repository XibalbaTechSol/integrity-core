import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ethers } from 'ethers';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronRight,
  Copy,
  KeyRound,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { oracle, type AisResponse, type AgentResponse, type AuditLogEntryDto, type Erc8004BindingDto, type MarketSummaryDto, type ProvenanceEntryDto, type WalletResponse } from '../services/oracle';
import { graphMemory, type MerkleRoot, type StoreStatus } from '../services/graphMemory';
import { readAgentBalances, type OnChainBalance } from '../integrity/wallet/chainClient';
import { ALLOW_UNSCOPED_AGENT_DIRECTORY } from '../config';
import { NAVIGATION_ITEMS } from '../navigation';
import './ProtocolDashboardPage.css';

type Tab = 'overview' | 'identity' | 'records' | 'proofs' | 'wallets' | 'transactions' | 'contracts' | 'security' | 'activity';

const short = (value?: string | null, start = 10, end = 8) => {
  if (!value) return 'Unavailable';
  if (value.length <= start + end + 1) return value;
  return `${value.slice(0, start)}…${value.slice(-end)}`;
};

const copyText = async (value?: string | null) => {
  if (!value) return;
  try {
    await navigator.clipboard?.writeText(value);
  } catch {
    // Clipboard access is optional in embedded/automated browsers; never turn a
    // copy affordance into an uncaught application error.
  }
};

const formatItk = (value?: string | null) => {
  if (!value) return null;
  try { return ethers.formatEther(value); } catch { return value; }
};

function State({ ok, children }: { ok: boolean | null; children: string }) {
  return <span className={`protocol-state ${ok === true ? 'good' : ok === false ? 'bad' : 'muted'}`}><i />{children}</span>;
}

function EvidenceValue({ label, value }: { label: string; value?: string | null }) {
  return <div className="evidence-value"><span>{label}</span><code>{short(value, 12, 10)}</code><button aria-label={`Copy ${label}`} onClick={() => void copyText(value)}><Copy size={13} /></button></div>;
}

function AgentCard({ agent, selected, onSelect }: { agent: ReturnType<typeof useDashboard>['agents'][number]; selected: boolean; onSelect: () => void }) {
  return <button className={`agent-list-row ${selected ? 'selected' : ''}`} onClick={onSelect}>
    <span className="agent-avatar">{(agent.alias || agent.name || 'A').slice(0, 2).toUpperCase()}</span>
    <span className="agent-list-copy"><strong>{agent.alias || agent.name || short(agent.id, 12, 8)}</strong><small>{short(agent.id, 15, 9)}</small></span>
    <span className="agent-list-score">{agent.current_ais == null ? '—' : agent.current_ais.toFixed(1)}<small>AIS</small></span>
    <ChevronRight size={15} />
  </button>;
}

export default function ProtocolDashboardPage() {
  const location = useLocation();
  const { agents, agentsLoading, selectedAgent, setSelectedAgent, connectWallet, walletAddress } = useDashboard();
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [detail, setDetail] = useState<AgentResponse | null>(null);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [ethBalance, setEthBalance] = useState<string | null>(null);
  const [onChainBalance, setOnChainBalance] = useState<OnChainBalance | null>(null);
  const [erc8004, setErc8004] = useState<Erc8004BindingDto | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceEntryDto[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntryDto[]>([]);
  const [contracts, setContracts] = useState<MarketSummaryDto[]>([]);
  const [cortex, setCortex] = useState<StoreStatus | null>(null);
  const [merkle, setMerkle] = useState<MerkleRoot | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const routeTab: Tab = location.pathname === '/identity' ? 'identity' : location.pathname === '/records' ? 'records' : location.pathname === '/proofs' ? 'proofs' : location.pathname === '/wallets' ? 'wallets' : location.pathname === '/transactions' ? 'transactions' : location.pathname === '/contracts' ? 'contracts' : location.pathname === '/security' ? 'security' : location.pathname === '/activity' ? 'activity' : 'overview';
  // Reuse the proven content regions for related workspace routes while keeping
  // the public information architecture explicit and discoverable.
  const tab: 'overview' | 'identity' | 'agents' | 'wallets' | 'contracts' | 'evidence' = routeTab === 'identity' ? 'identity' : ['records', 'proofs', 'activity'].includes(routeTab) ? 'evidence' : ['transactions', 'security'].includes(routeTab) ? 'wallets' : routeTab as 'overview' | 'wallets' | 'contracts';
  const tabTitles: Record<Tab, string> = { overview: 'Protocol overview', identity: 'Agent identity', records: 'Integrity records', proofs: 'Proofs & verification', wallets: 'Wallet', transactions: 'Transactions', contracts: 'Contracts', security: 'Security & keys', activity: 'Activity log' };

  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    setEthBalance(null);
    setOnChainBalance(null);
    setErc8004(null);
    setProvenance([]);
    setAuditLog([]);
    setLoading(true);
    Promise.allSettled([
      oracle.getAis(selectedAgent.id),
      oracle.getAgent(selectedAgent.id),
      oracle.getWallet(selectedAgent.id),
      oracle.getAgentContracts(selectedAgent.id),
      oracle.getErc8004(selectedAgent.id),
      oracle.getProvenance(selectedAgent.id),
      oracle.getAuditLog(selectedAgent.id, 20),
      graphMemory.status(),
      graphMemory.sessions(1),
    ]).then(([aisResult, detailResult, walletResult, contractResult, ercResult, provenanceResult, auditResult, cortexResult, sessionsResult]) => {
      if (!active) return;
      if (aisResult.status === 'fulfilled') setAis(aisResult.value);
      if (detailResult.status === 'fulfilled') {
        setDetail(detailResult.value);
        const sovereignAgent = detailResult.value.primitives?.sovereign_agent;
        if (sovereignAgent && ethers.isAddress(sovereignAgent)) {
          readAgentBalances(sovereignAgent)
            .then(balance => { if (!active) return; setOnChainBalance(balance); setEthBalance(balance.eth); })
            .catch(() => active && setEthBalance(null));
        }
      }
      if (walletResult.status === 'fulfilled') setWallet(walletResult.value);
      if (contractResult.status === 'fulfilled') setContracts(contractResult.value);
      if (ercResult.status === 'fulfilled') setErc8004(ercResult.value);
      if (provenanceResult.status === 'fulfilled') setProvenance(provenanceResult.value);
      if (auditResult.status === 'fulfilled') setAuditLog(auditResult.value);
      if (cortexResult.status === 'fulfilled') setCortex(cortexResult.value);
      if (sessionsResult.status === 'fulfilled' && sessionsResult.value[0]) {
        graphMemory.sessionMerkleRoot(sessionsResult.value[0].external_session_id).then(root => active && setMerkle(root)).catch(() => undefined);
      }
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [selectedAgent, refreshNonce]);

  const primitiveRows = useMemo(() => detail?.primitives ? Object.entries(detail.primitives) : [], [detail]);
  const nav = NAVIGATION_ITEMS;

  return <div className="protocol-app">
    <aside className="protocol-sidebar">
      <Link className="protocol-brand" to="/dashboard"><img src="/logo.png" alt="Integrity" /><span>PROTOCOL CORE</span></Link>
      <div className="protocol-network"><span>Network</span><strong><i />Base Sepolia</strong></div>
      <nav aria-label="Protocol navigation" tabIndex={0}>{nav.map(item => { const Icon = item.icon; return <Link key={item.to} aria-label={item.label} className={routeTab === item.to.slice(1) || (routeTab === 'overview' && item.to === '/dashboard') ? 'active' : ''} to={item.to}><Icon size={17} /><span>{item.label}</span></Link>; })}</nav>
      <div className="protocol-sidebar-foot"><LockKeyhole size={15} /><span>Key material never rendered</span><small>Protocol surface v1</small></div>
    </aside>
    <main className="protocol-main">
      <header className="protocol-topbar"><div><span className="protocol-kicker">Integrity protocol backbone</span><h1>{tabTitles[routeTab]}</h1></div><div className="protocol-top-actions"><label>Selected agent<select aria-label="Selected agent" value={selectedAgent?.id || ''} onChange={event => { const next = agents.find(agent => agent.id === event.target.value); if (next) setSelectedAgent(next); }}><option value="">{agentsLoading ? 'Loading agents…' : 'No agent selected'}</option>{agents.map(agent => <option key={agent.id} value={agent.id}>{agent.alias || agent.name || short(agent.id)}</option>)}</select></label><button className="icon-button" aria-label="Refresh data" onClick={() => setRefreshNonce(value => value + 1)}><RefreshCw size={16} className={loading ? 'spin' : ''} /></button><span className="wallet-connection"><i />{walletAddress ? short(walletAddress, 7, 5) : 'Wallet offline'}</span></div></header>

      <section className="protocol-health"><div><span>Network health</span><strong><i />{detail ? 'Connected' : 'Awaiting Oracle'}</strong></div><div><span>Identity binding</span><strong><i className={erc8004?.binding_status === 'verified' ? '' : 'muted-dot'} />{erc8004?.binding_status === 'verified' ? 'ERC-8004 verified' : 'Not confirmed'}</strong></div><div><span>Cortex evidence</span><strong><i className={cortex?.integrity_check === 'ok' ? '' : 'muted-dot'} />{cortex ? `${cortex.memory_count.toLocaleString()} memories` : 'Unavailable'}</strong></div><div><span>Live data</span><strong><i className={ais ? '' : 'muted-dot'} />{ais ? 'Oracle projection' : 'Read-only state'}</strong></div></section>

      <div className="protocol-content">
        {(tab === 'overview' || tab === 'identity') && <section className="protocol-grid agent-focus-grid"><div className="protocol-panel selected-agent-panel"><div className="panel-heading"><div><span className="panel-label">Selected identity</span><h2>{selectedAgent?.alias || selectedAgent?.name || (selectedAgent ? short(selectedAgent.id, 15, 9) : 'No agent selected')}</h2></div><State ok={erc8004?.binding_status === 'verified'}>{erc8004?.binding_status === 'verified' ? 'Verified' : 'Not verified'}</State></div><div className="identity-lines"><EvidenceValue label="ERC-8004 / DID" value={selectedAgent?.id} /><EvidenceValue label="Sovereign agent" value={detail?.primitives?.sovereign_agent} /><EvidenceValue label="NFT owner" value={erc8004?.nft_owner_address} /><EvidenceValue label="Agent wallet" value={erc8004?.agent_wallet_address} /><div className="ais-score"><span>Agent Integrity Score</span><strong>{ais?.ais == null ? '—' : ais.ais.toFixed(1)}</strong><small>/ 100 · Tier {detail?.verification_tier ?? selectedAgent?.verification_tier ?? '—'} · Oracle projection</small></div></div></div><div className="protocol-panel agent-list-panel"><div className="panel-heading"><div><span className="panel-label">{ALLOW_UNSCOPED_AGENT_DIRECTORY ? 'Operator / dev directory' : 'Authenticated scope'}</span><h2>Agents</h2></div><span className="panel-count">{agents.length}</span></div><div className="agent-list">{agents.length ? agents.map(agent => <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedAgent?.id} onSelect={() => setSelectedAgent(agent)} />) : <div className="empty-state">No permitted agents are available for this authenticated session.</div>}</div></div></section>}

        {(tab === 'overview' || tab === 'wallets') && <section className="protocol-grid wallet-grid"><div className="protocol-panel wallet-panel"><div className="panel-heading"><div><span className="panel-label">Agent treasury</span><h2>Wallet custody</h2></div><KeyRound size={19} /></div><div className="wallet-lock"><LockKeyhole size={22} /><div><strong>Protected key boundary</strong><span>Private keys are never shown. This UI can read the resolved treasury and connect an external signer, but cannot export or custody agent keys.</span></div></div><div className="wallet-address-row"><span>Agent wallet · on-chain resolved</span><code>{short(detail?.primitives?.sovereign_agent, 12, 10)}</code><small>Controller and signer relationship are shown only when independently verified by ERC-8004 data.</small></div><div className="balance-grid"><div><span>ITK balance · Oracle</span><strong>{formatItk(wallet?.itk_balance) ?? onChainBalance?.itk ?? '—'} <small>ITK</small></strong></div><div><span>ETH balance · RPC</span><strong>{ethBalance ?? '—'} <small>ETH</small></strong></div></div><div className="wallet-actions"><button className="primary-button" onClick={() => void connectWallet()}><ArrowUpFromLine size={16} />Connect external signer</button><button className="secondary-button" onClick={() => void copyText(detail?.primitives?.sovereign_agent)}><ArrowDownToLine size={16} />Copy receive address</button></div>{onChainBalance && <div className="source-line">On-chain read · Base Sepolia · block {onChainBalance.blockNumber} · {onChainBalance.itkSymbol} {onChainBalance.itk}</div>}</div><div className="protocol-panel transaction-panel"><div className="panel-heading"><div><span className="panel-label">Wallet activity</span><h2>Transactions</h2></div><span className="panel-count">{wallet?.transaction_history?.length ?? 0}</span></div>{wallet?.transaction_history?.length ? wallet.transaction_history.slice(0, 6).map(tx => <div className="transaction-row" key={tx.id}><span className="tx-icon"><ArrowUpFromLine size={14} /></span><span><strong>{tx.type} · {tx.asset}</strong><small>{short(tx.id, 12, 8)} · {tx.status}</small></span><b>{tx.amount}</b></div>) : <div className="empty-state">Oracle transaction history is unavailable until event indexing is implemented.</div>}</div></section>}

        {(tab === 'overview' || tab === 'evidence') && <section className="protocol-panel evidence-panel"><div className="panel-heading"><div><span className="panel-label">Proof surface</span><h2>Evidence chain</h2></div><a href="#evidence">Inspect all <ChevronRight size={14} /></a></div><div className="evidence-chain"><div className="evidence-node"><span>01</span><strong>BCC intent</strong><small>{auditLog.length ? `${auditLog.length} audit records` : 'Unavailable'}</small></div><div className="evidence-line" /><div className="evidence-node"><span>02</span><strong>Hash</strong><small>{provenance.length ? `${provenance.length} anchored leaves` : 'Unavailable'}</small></div><div className="evidence-line" /><div className="evidence-node"><span>03</span><strong>Merkle root</strong><small>{short(provenance[0]?.root || merkle?.root_node_id, 10, 8)}</small></div><div className="evidence-line" /><div className="evidence-node"><span>04</span><strong>ZK proof</strong><small>{ais?.zk_proof_verified === true ? 'Verified' : ais ? 'Not verified' : 'Unavailable'}</small></div><div className="evidence-line" /><div className="evidence-node"><span>05</span><strong>Oracle receipt</strong><small>{ais ? 'AIS projection' : 'Unavailable'}</small></div></div><div className="evidence-detail-grid"><EvidenceValue label="Merkle root" value={provenance[0]?.root || merkle?.root_node_id} /><EvidenceValue label="Latest content leaf" value={provenance[0]?.leaf} /><EvidenceValue label="Verification state" value={ais ? (ais.zk_proof_verified ? 'zk_verified' : 'not_verified') : 'unavailable'} /><EvidenceValue label="Reporting period" value={ais ? `${ais.period_start} → ${ais.period_end}` : null} /></div></section>}

        {(tab === 'overview' || tab === 'contracts') && <section className="protocol-panel contracts-panel"><div className="panel-heading"><div><span className="panel-label">Agent-controlled surface</span><h2>Deployed contracts</h2></div><span className="panel-count">{contracts.length + primitiveRows.length}</span></div><div className="contracts-table-wrap"><table><thead><tr><th>Address</th><th>Contract / primitive</th><th>Role</th><th>Authoritative controller</th><th>State</th></tr></thead><tbody>{primitiveRows.map(([name, address]) => <tr key={name}><td><code>{short(String(address), 11, 8)}</code></td><td><strong>{name.replace(/_/g, ' ')}</strong><small>Resolved by Oracle from agent registry</small></td><td>Protocol primitive</td><td>{erc8004 ? short(erc8004.nft_owner_address, 8, 6) : 'Unverified'}</td><td><State ok={Boolean(address && !/^0x0+$/i.test(String(address)))}>{address && !/^0x0+$/i.test(String(address)) ? 'Resolved' : 'Missing'}</State></td></tr>)}{contracts.map(contract => <tr key={contract.address}><td><code>{short(contract.address, 11, 8)}</code></td><td><strong>IntegrityMarket</strong><small>{short(contract.question, 42, 0)}</small></td><td>Creator projection</td><td>{short(contract.creator, 8, 6)}</td><td><State ok={!contract.resolved}>{contract.resolved ? 'Resolved' : 'Active'}</State></td></tr>)}</tbody></table>{!primitiveRows.length && !contracts.length && <div className="empty-state">No owned or controlled contracts were verified for this identity.</div>}</div></section>}

        <section className="protocol-note"><ShieldCheck size={16} /><span>This console exposes protocol evidence and wallet controls. It never renders private keys or treats AIS as authorization by itself.</span></section>
      </div>
    </main>
  </div>;
}
