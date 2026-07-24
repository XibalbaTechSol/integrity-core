import { useState, useEffect, useCallback } from 'react';
import { ethers } from 'ethers';
import { Panel } from '../shared/Panel';
import { StatusBadge } from '../shared/StatusBadge';
import {
  Zap, Plus, RefreshCw, BarChart2, Handshake, X, Terminal, Gavel, Trophy,
} from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { oracle, type MarketSummaryDto } from '../../services/oracle';
import { MARKET_FACTORY_ADDRESS, ITK_TOKEN_ADDRESS } from '../../constants';
import {
  MARKET_FACTORY_ABI, INTEGRITY_MARKET_ABI, ERC20_ABI, executeAsAgent,
} from '../../chain/markets';

interface ExecutionLog { id: number; time: string; message: string; }

const fmt = (wei: string | bigint) => Number(ethers.formatEther(wei)).toLocaleString(undefined, { maximumFractionDigits: 2 });

// Real application-layer markets (no mock task-bounty/hire/escrow/equity theater — all of
// that was localStorage + setTimeout with no on-chain or oracle backing). This is the human
// surface for the protocol thesis "agents deploy and own their own contracts": a registered
// agent deploys+owns an IntegrityMarket via MarketFactory (routed through its SovereignAgent),
// and any registered agent enters an AIS-gated, ITK-staked position. Every write routes through
// SovereignAgent.execute; ITK for a position is pulled from the SovereignAgent itself.
export function ActuarialHub({ mode }: { mode: 'markets' | 'stability' }) {
  const { selectedAgent, addToast, walletAddress, connectWallet } = useDashboard();

  const [markets, setMarkets] = useState<MarketSummaryDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<ExecutionLog[]>([]);
  // Agent.eth_address holds the DID; the real on-chain SovereignAgent address (needed to
  // route every write via execute, and to tell if this agent created a market) is resolved.
  const [saAddr, setSaAddr] = useState<string | null>(null);

  // Create-market form
  const [question, setQuestion] = useState('');
  const [outcomeCount, setOutcomeCount] = useState('2');
  const [minAis, setMinAis] = useState('500');
  const [durationHours, setDurationHours] = useState('72');
  const [isCreating, setIsCreating] = useState(false);

  // Enter-position modal
  const [posMarket, setPosMarket] = useState<MarketSummaryDto | null>(null);
  const [posOutcome, setPosOutcome] = useState('0');
  const [posAmount, setPosAmount] = useState('100');
  const [posBusy, setPosBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const addLog = (message: string) => setLogs(prev => [...prev, { id: Date.now() + Math.random(), time: new Date().toLocaleTimeString(), message }]);

  const fetchMarkets = useCallback(async () => {
    setLoading(true);
    try { setMarkets(await oracle.listMarkets()); }
    catch { setMarkets([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (mode === 'markets') fetchMarkets(); }, [mode, fetchMarkets]);

  useEffect(() => {
    const did = selectedAgent?.eth_address;
    if (!did) { setSaAddr(null); return; }
    let active = true;
    oracle.resolveSovereignAgent(did).then(a => { if (active) setSaAddr(a); }).catch(() => { if (active) setSaAddr(null); });
    return () => { active = false; };
  }, [selectedAgent]);

  const getSigner = async () => {
    const eth = (window as any).ethereum;
    if (!eth) throw new Error('No Web3 wallet detected.');
    return new ethers.BrowserProvider(eth).getSigner();
  };

  const requireAgentWallet = (): string | null => {
    if (!selectedAgent) { addToast('error', 'Select an agent first.'); return null; }
    if (!walletAddress) { addToast('error', 'Connect the agent controller wallet.'); return null; }
    if (!saAddr) { addToast('error', 'This agent has no on-chain SovereignAgent yet.'); return null; }
    return saAddr; // the agent's real on-chain SovereignAgent address
  };

  const handleCreateMarket = async () => {
    const sa = requireAgentWallet();
    if (!sa || !question.trim()) return;
    setIsCreating(true);
    addLog(`Deploying market: "${question}"…`);
    try {
      const signer = await getSigner();
      const deadline = Math.floor(Date.now() / 1000) + Math.max(1, parseInt(durationHours) || 72) * 3600;
      // Creator self-resolves the demo market (RESOLVER_ROLE = the SovereignAgent). Documented
      // trust boundary — a production market would name a real oracle network as resolver.
      const data = new ethers.Interface(MARKET_FACTORY_ABI as any).encodeFunctionData('deployMarket', [
        question.trim(), Number(outcomeCount), BigInt(Math.round(Number(minAis) || 0)), BigInt(deadline), sa,
      ]);
      const receipt = await executeAsAgent(signer, sa, MARKET_FACTORY_ADDRESS, data);
      let market = '';
      const iface = new ethers.Interface(MARKET_FACTORY_ABI as any);
      for (const log of receipt.logs) {
        try { const p = iface.parseLog(log); if (p?.name === 'MarketDeployed') { market = p.args.market; break; } } catch { /* not ours */ }
      }
      addLog(`SUCCESS: market deployed${market ? ` at ${market.slice(0, 10)}…` : ''}`);
      addToast('success', 'Market deployed and owned by your agent.');
      setQuestion('');
      await fetchMarkets();
    } catch (err: any) {
      addLog(`ERROR: ${err.shortMessage || err.reason || err.message}`);
      addToast('error', `Deploy failed: ${err.shortMessage || err.reason || err.message}`);
    } finally { setIsCreating(false); }
  };

  const handleEnterPosition = async () => {
    const sa = requireAgentWallet();
    if (!sa || !posMarket) return;
    setPosBusy(true);
    try {
      const signer = await getSigner();
      const amt = ethers.parseEther(posAmount || '0');
      if (amt <= 0n) throw new Error('Enter an amount greater than zero.');
      const itk = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI as any, signer);

      // 1. Fund-SA step: enterPosition pulls ITK from the SovereignAgent (msg.sender), so the
      //    SA must hold enough. Top it up from the controller wallet if short.
      const saBal: bigint = await itk.balanceOf(sa);
      if (saBal < amt) {
        const need = amt - saBal;
        addToast('info', `Funding your agent with ${fmt(need)} $ITK…`);
        await (await itk.transfer(sa, need)).wait();
      }
      // 2. Approve the market to pull from the SA (via execute), only if allowance is short.
      const allowance: bigint = await itk.allowance(sa, posMarket.address);
      if (allowance < amt) {
        addToast('info', 'Approving $ITK for the market…');
        const approveData = new ethers.Interface(ERC20_ABI as any).encodeFunctionData('approve', [posMarket.address, amt]);
        await executeAsAgent(signer, sa, ITK_TOKEN_ADDRESS, approveData);
      }
      // 3. Enter the position through the SovereignAgent. bccCommitmentHash is left zero here —
      //    the dashboard does not yet run the off-chain BCC pre-commitment flow (SDK-side);
      //    the stake/AIS-gate/payout are fully real, only the intent-binding is unset.
      addToast('info', 'Entering position…');
      const enterData = new ethers.Interface(INTEGRITY_MARKET_ABI as any).encodeFunctionData('enterPosition', [Number(posOutcome), amt, ethers.ZeroHash]);
      await executeAsAgent(signer, sa, posMarket.address, enterData);
      addLog(`SUCCESS: position on outcome #${posOutcome} for ${posAmount} ITK`);
      addToast('success', 'Position entered.');
      setPosMarket(null);
      await fetchMarkets();
    } catch (err: any) {
      addToast('error', `Position failed: ${err.shortMessage || err.reason || err.message}`);
    } finally { setPosBusy(false); }
  };

  const handleResolve = async (m: MarketSummaryDto, outcome: number) => {
    const sa = requireAgentWallet();
    if (!sa) return;
    setActionBusy(m.address);
    try {
      const signer = await getSigner();
      const data = new ethers.Interface(INTEGRITY_MARKET_ABI as any).encodeFunctionData('resolve', [outcome]);
      await executeAsAgent(signer, sa, m.address, data);
      addToast('success', `Market resolved to outcome #${outcome}.`);
      await fetchMarkets();
    } catch (err: any) {
      addToast('error', `Resolve failed: ${err.shortMessage || err.reason || err.message}`);
    } finally { setActionBusy(null); }
  };

  const handleClaim = async (m: MarketSummaryDto) => {
    const sa = requireAgentWallet();
    if (!sa) return;
    setActionBusy(m.address);
    try {
      const signer = await getSigner();
      const data = new ethers.Interface(INTEGRITY_MARKET_ABI as any).encodeFunctionData('claimPayout', []);
      await executeAsAgent(signer, sa, m.address, data);
      addToast('success', 'Payout claimed.');
      await fetchMarkets();
    } catch (err: any) {
      addToast('error', `Claim failed: ${err.shortMessage || err.reason || err.message}`);
    } finally { setActionBusy(null); }
  };

  if (mode === 'stability') {
    // The provider-stability benchmark leaderboard needs a real oracle endpoint that does not
    // exist yet (tracked as the benchmarks endpoint). Rather than fabricate provider rows /
    // regional-latency heatmaps / invented "8,421 verifiers online" counts (all of which the
    // old panel simply hardcoded), this is an honest gap until that endpoint lands.
    return (
      <div className="flex-col gap-6">
        <Panel title="Stability Leaderboard" icon={<BarChart2 size={18} />}>
          <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
            <BarChart2 size={28} style={{ opacity: 0.5, marginBottom: 8 }} />
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Provider benchmark endpoint pending</div>
            <p style={{ fontSize: '0.8rem', margin: '0 auto', maxWidth: 460 }}>
              Model/provider stability rankings will be served from a real oracle benchmarks endpoint
              (aggregating telemetry variance + grounding). Not yet wired — shown here rather than
              fabricated so the dashboard never displays invented metrics.
            </p>
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex-col gap-6">
      <Panel title="Deploy a Market" icon={<Zap size={18} />}>
        <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
          <div className="flex-col gap-4">
            <div style={{ padding: 'var(--space-3)', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)', marginBottom: '4px' }}>Your agent deploys & owns the market</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)' }}>
                An AIS-gated, ITK-staked outcome market — deployed via MarketFactory through your SovereignAgent. You are its creator and resolver.
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="mkt-q">Question</label>
              <input id="mkt-q" className="input" placeholder="e.g. Will BTC close above $100k by Friday?" value={question} onChange={e => setQuestion(e.target.value)} />
            </div>
            <div className="grid-cols-2" style={{ gap: 'var(--space-4)' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="mkt-outcomes">Outcomes</label>
                <input id="mkt-outcomes" type="number" min={2} max={8} className="input" value={outcomeCount} onChange={e => setOutcomeCount(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="mkt-minais">Min AIS to Enter</label>
                <input id="mkt-minais" type="number" className="input" value={minAis} onChange={e => setMinAis(e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="mkt-dur">Resolve Deadline (hours from now)</label>
              <input id="mkt-dur" type="number" className="input" value={durationHours} onChange={e => setDurationHours(e.target.value)} />
            </div>
            {!walletAddress ? (
              <button className="btn btn-primary" onClick={connectWallet}>Connect Wallet</button>
            ) : (
              <button className="btn btn-primary" onClick={handleCreateMarket} disabled={isCreating || !selectedAgent || !question.trim()}>
                {isCreating ? 'Deploying…' : <>Deploy Market <Plus size={16} style={{ marginLeft: 8 }} /></>}
              </button>
            )}
          </div>

          <div className="flex-col gap-4">
            <div data-testid="protocol-logs" style={{ background: 'var(--navy-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', height: '260px', padding: 'var(--space-3)', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div className="flex items-center justify-between" style={{ borderBottom: '1px solid var(--glass-border)', paddingBottom: '4px', marginBottom: '4px' }}>
                <div className="flex items-center gap-2" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}><Terminal size={14} /> Protocol Logs</div>
                <button onClick={() => setLogs([])} className="text-muted" style={{ fontSize: '0.65rem', background: 'none', border: 'none', cursor: 'pointer' }}>Clear</button>
              </div>
              {logs.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontStyle: 'italic', marginTop: 'var(--space-2)' }}>Awaiting market activity…</div>
              ) : logs.map(log => (
                <div key={log.id} className="mono" style={{ fontSize: '0.75rem', color: log.message.includes('SUCCESS') ? 'var(--success)' : log.message.includes('ERROR') ? 'var(--error)' : 'var(--text-primary)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>[{log.time}]</span> {log.message}
                </div>
              ))}
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Live Markets" icon={<Handshake size={18} />}
        action={<button className="btn btn-icon" onClick={fetchMarkets} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /></button>}>
        <div className="table-container">
          <table className="table">
            <thead>
              <tr><th>Question</th><th>Outcomes</th><th>Min AIS</th><th>Total Staked</th><th>Deadline</th><th>Status</th><th>Action</th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>Loading real markets…</td></tr>
              ) : markets.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>No markets deployed yet.</td></tr>
              ) : markets.map(m => {
                const deadline = Number(m.resolve_deadline) * 1000;
                const past = Date.now() >= deadline;
                const isCreator = !!saAddr && saAddr.toLowerCase() === m.creator.toLowerCase();
                return (
                  <tr key={m.address}>
                    <td style={{ maxWidth: 260 }}>
                      <div style={{ fontWeight: 500 }}>{m.question}</div>
                      <div className="mono" style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{m.address.slice(0, 12)}…</div>
                    </td>
                    <td>{m.outcome_count}{m.outcome_staked?.length ? ` (${m.outcome_staked.map(s => fmt(s)).join(' / ')})` : ''}</td>
                    <td>{m.min_ais_to_enter}</td>
                    <td className="mono" style={{ color: 'var(--gold)' }}>{fmt(m.total_staked)} ITK</td>
                    <td style={{ fontSize: '0.75rem' }}>{new Date(deadline).toLocaleString()}</td>
                    <td><StatusBadge status={m.resolved ? 'resolved' : past ? 'pending' : 'active'} /></td>
                    <td>
                      {m.resolved ? (
                        <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.72rem', color: 'var(--success)' }}
                          disabled={actionBusy === m.address} onClick={() => handleClaim(m)}>
                          <Trophy size={12} style={{ marginRight: 4 }} /> Claim
                        </button>
                      ) : isCreator && past ? (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {Array.from({ length: m.outcome_count }).map((_, i) => (
                            <button key={i} className="btn btn-ghost" style={{ padding: '3px 7px', fontSize: '0.68rem', color: 'var(--primary)' }}
                              disabled={actionBusy === m.address} onClick={() => handleResolve(m, i)}>
                              <Gavel size={10} style={{ marginRight: 2 }} /> #{i}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <button className="btn" style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                          disabled={!selectedAgent || past} onClick={() => { setPosMarket(m); setPosOutcome('0'); }}>
                          Enter Position
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {posMarket && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div onClick={() => !posBusy && setPosMarket(null)} style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} />
          <div style={{ position: 'relative', width: '100%', maxWidth: 460, background: 'var(--bg-secondary)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: 'var(--space-5)', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Enter Position</h3>
              <button onClick={() => !posBusy && setPosMarket(null)} className="btn btn-icon" aria-label="Close"><X size={18} /></button>
            </div>
            <div style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ fontSize: '0.85rem' }}>{posMarket.question}</div>
              <div className="form-group">
                <label className="form-label" htmlFor="pos-outcome">Outcome</label>
                <select id="pos-outcome" className="select" value={posOutcome} onChange={e => setPosOutcome(e.target.value)}>
                  {Array.from({ length: posMarket.outcome_count }).map((_, i) => <option key={i} value={i}>Outcome #{i}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="pos-amount">Stake (ITK)</label>
                <input id="pos-amount" type="number" className="input" value={posAmount} onChange={e => setPosAmount(e.target.value)} />
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                Pulled from your agent's SovereignAgent (topped up from your wallet if short), AIS-gated on entry.
              </div>
              <button className="btn btn-primary" onClick={handleEnterPosition} disabled={posBusy}>
                {posBusy ? 'Submitting…' : 'Stake Position'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
