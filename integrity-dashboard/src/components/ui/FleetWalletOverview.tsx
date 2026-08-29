import { useCallback, useEffect, useState } from 'react';
import { ethers } from 'ethers';
import { Users, Coins, RefreshCw, ChevronRight } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';

interface FleetRow {
  id: string;
  alias: string;
  eth_address: string;
  balance: number; // ITK, human units
  ais: number | null;
}

// Portfolio view across every registered agent -- the piece a human actually managing a
// fleet of agents needs, that a single-agent wallet card can't show: which agents hold
// how much ITK, at a glance, before drilling into any one agent's detailed wallet below.
// Real oracle.getWallet() reads per agent, fanned out in parallel (same bounded
// client-side pattern DashboardContext already uses for protocol-wide aggregation) --
// no fabricated portfolio totals.
export function FleetWalletOverview() {
  const { agents, selectedAgent, setSelectedAgent } = useDashboard();
  const [rows, setRows] = useState<FleetRow[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (agents.length === 0) { setRows([]); return; }
    setLoading(true);
    try {
      const results = await Promise.all(
        agents.map(async (a) => {
          try {
            const w = await oracle.getWallet(a.eth_address);
            return { id: a.id, alias: a.alias || a.name || a.id, eth_address: a.eth_address, balance: Number(ethers.formatEther(w.itk_balance)), ais: a.current_ais ?? null };
          } catch {
            return { id: a.id, alias: a.alias || a.name || a.id, eth_address: a.eth_address, balance: 0, ais: a.current_ais ?? null };
          }
        }),
      );
      setRows(results.sort((x, y) => y.balance - x.balance));
    } finally {
      setLoading(false);
    }
  }, [agents]);

  useEffect(() => { load(); }, [load]);

  const totalItk = rows.reduce((sum, r) => sum + r.balance, 0);

  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)',
      padding: 'var(--space-6)', marginBottom: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Users size={18} color="var(--theme-accent)" />
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>Fleet Wallets</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Every registered agent's real on-chain ITK balance -- click one to manage it below.</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Fleet total ITK</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--theme-accent)' }}>{totalItk.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
          </div>
          <button onClick={load} disabled={loading} style={{ background: 'none', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '6px', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: 'var(--space-4) 0', textAlign: 'center' }}>
          {loading ? 'Loading fleet balances…' : 'No agents registered on this network yet.'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {rows.map((r) => (
            <button
              key={r.id}
              onClick={() => {
                const agent = agents.find(a => a.id === r.id);
                if (agent) setSelectedAgent(agent);
              }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)',
                padding: 'var(--space-3) var(--space-2)', background: r.id === selectedAgent?.id ? 'var(--theme-accent-muted)' : 'transparent',
                border: 'none', borderBottom: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)',
                cursor: 'pointer', textAlign: 'left', color: 'inherit', width: '100%',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--theme-accent-muted)', color: 'var(--theme-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Coins size={16} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem', color: r.id === selectedAgent?.id ? 'var(--theme-accent)' : 'var(--text-primary)' }}>{r.alias}</div>
                  <div className="mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.eth_address}</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexShrink: 0 }}>
                {r.ais != null && <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>AIS {r.ais.toFixed(0)}</span>}
                <span style={{ fontWeight: 700, fontSize: '0.9rem', fontVariantNumeric: 'tabular-nums' }}>{r.balance.toLocaleString(undefined, { maximumFractionDigits: 2 })} ITK</span>
                <ChevronRight size={14} color="var(--text-muted)" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
