import { useState, useEffect, useCallback } from 'react';
import { ethers } from 'ethers';
import { useDashboard } from '../../context/useDashboard';
import { Panel } from '../shared/Panel';
import { StatusBadge } from '../shared/StatusBadge';
import { Coins, HandCoins, Clock, RefreshCw, Undo2, Send } from 'lucide-react';
import { oracle, type CreditDto } from '../../services/oracle';
import { A2A_CAPITAL_POOL_ADDRESS, ITK_TOKEN_ADDRESS } from '../../constants';
import ITK_ABI from '../abi/IntegrityToken.json';

// Real A2ACapitalPool wiring (no mock lending facility). The pool is a single global
// allocator->agent capital ESCROW, not a borrow/repay credit line: an allocator (this
// connected wallet — a human investor or another agent) escrows $ITK earmarked for a
// specific agent, gated on that agent's LIVE effective AIS, then releases it to the
// agent or claws it back. There is no on-chain "borrow", "APR", or "loan" — the old
// panel invented all of those. See contracts/src/markets/A2ACapitalPool.sol.
const POOL_ABI = [
  'function allocate(address agent, uint256 amount, uint256 minAisToMaintain) returns (uint256 allocationId)',
  'function release(uint256 allocationId)',
  'function clawback(uint256 allocationId)',
  'function allocations(uint256) view returns (address allocator, address agent, uint256 amount, uint256 minAisToMaintain, uint8 status, uint256 createdAt)',
  'event Allocated(uint256 indexed allocationId, address indexed allocator, address indexed agent, uint256 amount, uint256 minAisToMaintain)',
] as const;

// Mirrors A2ACapitalPool.Status.
const STATUS = ['Escrowed', 'Released', 'ClawedBack', 'Breached'] as const;

interface MyAllocation {
  id: string;
  amount: bigint;
  minAis: bigint;
  status: number;
  createdAt: number;
}

const fmt = (wei: string | bigint) => Number(ethers.formatEther(wei)).toLocaleString(undefined, { maximumFractionDigits: 2 });

export function CreditPanel() {
  const { selectedAgent, walletAddress, connectWallet, addToast, fetchData } = useDashboard();

  const [credit, setCredit] = useState<CreditDto | null>(null);
  const [amount, setAmount] = useState('5000');
  const [minAis, setMinAis] = useState('');
  const [isAllocating, setIsAllocating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [myAllocations, setMyAllocations] = useState<MyAllocation[]>([]);
  const [loadingAllocs, setLoadingAllocs] = useState(false);

  const agentAddr = selectedAgent?.eth_address;

  // Real per-agent aggregate straight from the A2ACapitalPool read endpoint.
  useEffect(() => {
    if (!agentAddr) { setCredit(null); return; }
    let active = true;
    oracle.getCredit(agentAddr).then(c => { if (active) setCredit(c); }).catch(() => { if (active) setCredit(null); });
    return () => { active = false; };
  }, [agentAddr]);

  // The connected wallet's OWN allocations to this agent, read live from Allocated
  // events (allocationId + allocator + agent are all indexed, so this filters exactly)
  // then re-checked against the current on-chain status so Release/Clawback only show
  // for still-escrowed entries.
  const loadMyAllocations = useCallback(async () => {
    const eth = (window as any).ethereum;
    if (!eth || !walletAddress || !agentAddr) { setMyAllocations([]); return; }
    setLoadingAllocs(true);
    try {
      const provider = new ethers.BrowserProvider(eth);
      const pool = new ethers.Contract(A2A_CAPITAL_POOL_ADDRESS, POOL_ABI, provider);
      const events = await pool.queryFilter(pool.filters.Allocated(null, walletAddress, agentAddr));
      const rows = await Promise.all(events.map(async (ev: any) => {
        const id = ev.args.allocationId as bigint;
        const a = await pool.allocations(id);
        return { id: id.toString(), amount: a.amount as bigint, minAis: a.minAisToMaintain as bigint, status: Number(a.status), createdAt: Number(a.createdAt) };
      }));
      rows.sort((x, y) => y.createdAt - x.createdAt);
      setMyAllocations(rows);
    } catch {
      setMyAllocations([]);
    } finally {
      setLoadingAllocs(false);
    }
  }, [walletAddress, agentAddr]);

  useEffect(() => { loadMyAllocations(); }, [loadMyAllocations]);

  const refresh = async () => {
    if (agentAddr) oracle.getCredit(agentAddr).then(setCredit).catch(() => {});
    await loadMyAllocations();
    if (fetchData) await fetchData();
  };

  const getSigner = async () => {
    const eth = (window as any).ethereum;
    if (!eth) throw new Error('No Web3 wallet detected.');
    return new ethers.BrowserProvider(eth).getSigner();
  };

  const handleAllocate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent || !agentAddr) return;
    if (!walletAddress) { addToast('error', 'Connect a Base Sepolia wallet to allocate capital.'); return; }
    const amt = ethers.parseEther(amount || '0');
    if (amt <= 0n) { addToast('error', 'Enter an amount greater than zero.'); return; }
    // Default the AIS floor to the agent's current score if the allocator didn't set one.
    const threshold = BigInt(minAis || Math.round(selectedAgent.current_ais || 0));

    setIsAllocating(true);
    try {
      const signer = await getSigner();
      const itk = new ethers.Contract(ITK_TOKEN_ADDRESS, ITK_ABI.abi, signer);
      // 1. Approve the pool to pull the escrow (only if the standing allowance is short).
      const allowance: bigint = await itk.allowance(walletAddress, A2A_CAPITAL_POOL_ADDRESS);
      if (allowance < amt) {
        addToast('info', 'Approving $ITK for the capital pool…');
        await (await itk.approve(A2A_CAPITAL_POOL_ADDRESS, amt)).wait();
      }
      // 2. Escrow the capital, gated on the agent's live AIS at allocation time.
      const pool = new ethers.Contract(A2A_CAPITAL_POOL_ADDRESS, POOL_ABI, signer);
      addToast('info', 'Escrowing capital to the agent…');
      const tx = await pool.allocate(agentAddr, amt, threshold);
      await tx.wait();
      addToast('success', `Allocated ${amount} $ITK to ${selectedAgent.alias}`);
      await refresh();
    } catch (err: any) {
      addToast('error', `Allocation failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setIsAllocating(false);
    }
  };

  const act = async (id: string, kind: 'release' | 'clawback') => {
    setBusyId(id);
    try {
      const signer = await getSigner();
      const pool = new ethers.Contract(A2A_CAPITAL_POOL_ADDRESS, POOL_ABI, signer);
      addToast('info', kind === 'release' ? 'Releasing capital to the agent…' : 'Reclaiming escrowed capital…');
      const tx = kind === 'release' ? await pool.release(id) : await pool.clawback(id);
      await tx.wait();
      addToast('success', kind === 'release' ? 'Capital released to the agent.' : 'Escrow reclaimed.');
      await refresh();
    } catch (err: any) {
      addToast('error', `${kind} failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-3">
        <Panel title="Capital Position" icon={<Coins size={18} />} className="flex-col justify-between">
          {!selectedAgent ? <div className="text-muted">Select an agent</div> : (
            <>
              <div style={{ textAlign: 'center', marginBottom: 'var(--space-4)' }}>
                <div style={{ fontSize: '2.4rem', fontWeight: 800, color: 'var(--primary)', lineHeight: 1 }}>
                  {credit ? fmt(credit.total_allocated) : '0'}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Total Allocated (ITK)
                </div>
              </div>
              {[
                ['Escrowed', credit?.escrowed, 'var(--gold)'],
                ['Released', credit?.released, 'var(--success)'],
                ['Clawed Back', credit?.clawed_back, 'var(--text-primary)'],
                ['Breached', credit?.breached, (Number(credit?.breached || 0) > 0 ? 'var(--danger)' : 'var(--text-primary)')],
              ].map(([label, val, color]) => (
                <div key={label as string} className="flex justify-between" style={{ padding: 'var(--space-2) 0', borderTop: '1px solid var(--glass-border)' }}>
                  <span className="text-muted" style={{ fontSize: '0.875rem' }}>{label}</span>
                  <span className="mono" style={{ color: color as string }}>{val ? fmt(val) : '0'} ITK</span>
                </div>
              ))}
              <div className="flex justify-between" style={{ padding: 'var(--space-2) 0', borderTop: '1px solid var(--glass-border)' }}>
                <span className="text-muted" style={{ fontSize: '0.875rem' }}>Allocations</span>
                <span className="mono">{credit?.allocation_count ?? 0}</span>
              </div>
            </>
          )}
        </Panel>

        <Panel title="Allocate Capital" icon={<HandCoins size={18} />} style={{ gridColumn: 'span 2' }}>
          <form onSubmit={handleAllocate} className="grid-cols-2">
            <div className="flex-col gap-4">
              <div className="form-group">
                <label className="form-label" htmlFor="alloc-amount">Amount to Escrow (ITK)</label>
                <input id="alloc-amount" type="number" className="input" value={amount} onChange={e => setAmount(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="min-ais">Minimum AIS to Maintain</label>
                <input id="min-ais" type="number" className="input" value={minAis}
                  onChange={e => setMinAis(e.target.value)}
                  placeholder={selectedAgent ? `Defaults to current (${Math.round(selectedAgent.current_ais || 0)})` : 'Select an agent'} />
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Capital is escrowed only while the agent's live AIS clears this floor; it's re-checked at release.
                </div>
              </div>
            </div>

            <div className="flex-col gap-4">
              <div style={{ background: 'var(--bg-primary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)', height: '100%' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', marginBottom: 'var(--space-3)' }}>
                  You (<span className="mono">{walletAddress ? `${walletAddress.slice(0, 6)}…${walletAddress.slice(-4)}` : 'not connected'}</span>) escrow $ITK for
                  <span style={{ color: 'var(--primary)' }}> {selectedAgent?.alias || 'the selected agent'}</span>. Release it once satisfied, or clawback any time before release.
                </div>
                <div style={{ padding: 'var(--space-2)', background: 'var(--primary-dim)', borderRadius: 'var(--radius-sm)', fontSize: '0.72rem', color: 'var(--text-primary)' }}>
                  On-chain via A2ACapitalPool — no lending, no interest. Purely trust-gated capital delegation.
                </div>
                {!walletAddress ? (
                  <button type="button" className="btn btn-primary" style={{ width: '100%', marginTop: 'var(--space-4)' }} onClick={connectWallet}>
                    Connect Wallet
                  </button>
                ) : (
                  <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: 'var(--space-4)' }} disabled={!selectedAgent || isAllocating}>
                    {isAllocating ? <RefreshCw className="spin" size={16} /> : <><Send size={15} style={{ marginRight: 6 }} /> Escrow Capital</>}
                  </button>
                )}
              </div>
            </div>
          </form>
        </Panel>
      </div>

      <Panel title="Your Allocations to this Agent" icon={<Clock size={18} />}>
        {!selectedAgent ? (
          <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>Select an agent to view your allocations.</div>
        ) : !walletAddress ? (
          <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>Connect a wallet to see allocations you've made.</div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr><th>Allocation ID</th><th>Amount</th><th>Min AIS</th><th>Created</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {loadingAllocs && <tr><td colSpan={6} className="text-muted" style={{ textAlign: 'center', padding: '2rem' }}>Reading on-chain allocations…</td></tr>}
                {!loadingAllocs && myAllocations.map(a => (
                  <tr key={a.id}>
                    <td className="mono">#{a.id}</td>
                    <td className="mono" style={{ color: 'var(--gold)' }}>{fmt(a.amount)} ITK</td>
                    <td className="mono">{a.minAis.toString()}</td>
                    <td>{a.createdAt ? new Date(a.createdAt * 1000).toLocaleDateString() : '—'}</td>
                    <td><StatusBadge status={STATUS[a.status]?.toLowerCase() || 'unknown'} /></td>
                    <td>
                      {a.status === 0 ? (
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem', color: 'var(--success)' }}
                            disabled={busyId === a.id} onClick={() => act(a.id, 'release')}>
                            {busyId === a.id ? '…' : 'Release'}
                          </button>
                          <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem', color: 'var(--gold)', display: 'flex', alignItems: 'center', gap: '2px' }}
                            disabled={busyId === a.id} onClick={() => act(a.id, 'clawback')}>
                            <Undo2 size={12} /> Clawback
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>{STATUS[a.status] || 'Settled'}</span>
                      )}
                    </td>
                  </tr>
                ))}
                {!loadingAllocs && myAllocations.length === 0 && (
                  <tr><td colSpan={6} className="text-muted" style={{ textAlign: 'center', padding: '2rem' }}>
                    You haven't allocated capital to this agent yet.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
