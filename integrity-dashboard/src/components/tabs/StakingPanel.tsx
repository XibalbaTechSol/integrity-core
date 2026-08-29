import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Lock, Coins, TrendingUp, AlertTriangle } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';
import { ethers } from 'ethers';
import { ITK_TOKEN_ADDRESS } from '../../constants';
import { ERC20_ABI } from '../../chain/markets';
import type { StakeDto } from '../../services/oracle';


// Staking in this protocol is per-agent: an agent bonds $ITK into its OWN Slasher
// clone (Slasher.stake), never a monolithic "protocol" contract. The Slasher address
// is resolved live from the agent's on-chain primitive set — never hardcoded. Minimal
// ABI: just the write we call here (the read side is the /v1/agent/{id}/stake endpoint).
const SLASHER_ABI = ['function stake(uint256 amount)'] as const;

export function StakingPanel() {
  const { selectedAgent, stats, addToast, walletAddress } = useDashboard() as any;
  const [stakeAmount, setStakeAmount] = useState<string>('');
  const [isStaking, setIsStaking] = useState(false);
  const [agentStake, setAgentStake] = useState<StakeDto | null>(null);

  useEffect(() => {
    if (!selectedAgent) { setAgentStake(null); return; }
    let active = true;
    oracle.getStake(selectedAgent.eth_address)
      .then(s => { if (active) setAgentStake(s); })
      .catch(() => { if (active) setAgentStake(null); });
    return () => { active = false; };
  }, [selectedAgent?.id]);

  const handleStake = async () => {
    if (!selectedAgent || !stakeAmount) return;

    const ethereum = (window as any).ethereum;
    if (!ethereum || !walletAddress) {
      addToast('error', 'Connect a Base Sepolia wallet to bond $ITK.');
      return;
    }

    setIsStaking(true);
    try {
      // Resolve the agent's own Slasher clone from its on-chain primitive set — the
      // real stake target. If the agent isn't fully registered, there's nothing to
      // stake into; say so rather than sending a tx to a zero/garbage address.
      const detail = await oracle.getAgent(selectedAgent.eth_address);
      const slasherAddr = detail.primitives?.slasher;
      if (!slasherAddr || /^0x0+$/i.test(slasherAddr)) {
        addToast('error', 'This agent has no deployed Slasher clone yet — register its primitives first.');
        return;
      }

      const provider = new ethers.BrowserProvider(ethereum);
      const signer = await provider.getSigner();
      const itkContract = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, signer);
      const amount = ethers.parseEther(stakeAmount);

      // 1. Approve the Slasher to pull the bond (only if the existing allowance is short).
      const allowance = await itkContract.allowance(walletAddress, slasherAddr);
      if (allowance < amount) {
        addToast('info', 'Approving $ITK for the agent Slasher…');
        const approveTx = await itkContract.approve(slasherAddr, amount);
        await approveTx.wait();
        addToast('success', 'Allowance granted');
      }

      // 2. Bond into the agent's Slasher (real Base Sepolia tx).
      const slasher = new ethers.Contract(slasherAddr, SLASHER_ABI, signer);
      addToast('info', 'Broadcasting stake to Base Sepolia…');
      const stakeTx = await slasher.stake(amount);
      await stakeTx.wait();

      addToast('success', `Bonded ${stakeAmount} $ITK for ${selectedAgent.alias}`);
      setStakeAmount('');
      oracle.getStake(selectedAgent.eth_address).then(setAgentStake).catch(() => {});

    } catch (err: any) {
      addToast('error', `Staking failed: ${err.shortMessage || err.message}`);
    } finally {
      setIsStaking(false);
    }
  };

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-3">
        <Panel title="Protocol TVL" icon={<TrendingUp size={18} />}>
          <div className="flex-col items-center justify-center p-4">
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>
              {(stats?.protocol_staked_itk || 0).toLocaleString()}
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Total ITK Staked</div>
          </div>
        </Panel>

        <Panel title="Your Stake" icon={<Lock size={18} />}>
          <div className="flex-col items-center justify-center p-4">
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--success)' }}>
              {agentStake ? Number(ethers.formatEther(agentStake.total_stake)).toLocaleString() : selectedAgent ? '0' : '—'}
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Active Bond (ITK)</div>
          </div>
        </Panel>

        <Panel title="Open Disputes" icon={<Coins size={18} />}>
          <div className="flex-col items-center justify-center p-4">
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--secondary)' }}>
              {agentStake ? agentStake.open_disputes : selectedAgent ? '0' : '—'}
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Active Slasher Disputes</div>
          </div>
        </Panel>
      </div>

      <div className="grid-cols-2">
        <Panel title="Bond Asset" icon={<Lock size={18} />}>
          <div className="flex-col gap-4">
            <div className="text-muted" style={{ fontSize: '0.875rem' }}>
              Lock ITK tokens to increase your agent's AIS floor and enable higher-value contracts.
            </div>

            {!selectedAgent ? (
              <div style={{ padding: 'var(--space-6)', textAlign: 'center', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                Please select an agent to manage bonds.
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label className="form-label" htmlFor="stake-amount">Amount to Stake (ITK)</label>
                  <input 
                    id="stake-amount"
                    type="number" 
                    className="input" 
                    placeholder="Min. 100 ITK"
                    value={stakeAmount}
                    onChange={e => setStakeAmount(e.target.value)}
                  />
                </div>

                <div style={{ background: 'var(--primary-dim)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--primary)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Stake feeds the Sacrifice component of AIS's geometric-mean formula — not a linear points bonus. Refresh the AIS panel after the bond confirms to see the effect.
                  </div>
                </div>

                <button
                  className="btn btn-primary" 
                  onClick={handleStake}
                  disabled={isStaking || !stakeAmount || Number(stakeAmount) < 100}
                >
                  {isStaking ? 'Broadcasting to Base...' : 'Commit Bond'}
                </button>
              </>
            )}
          </div>
        </Panel>

        <Panel title="Collateral Health" icon={<AlertTriangle size={18} />}>
          <div className="flex-col gap-4">
            {!agentStake ? (
              <div className="text-muted" style={{ fontSize: '0.875rem' }}>No stake position for this agent yet.</div>
            ) : (
              <>
                <div className="table-container">
                  <table className="table" style={{ fontSize: '0.75rem' }}>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Value</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Total Bond</td>
                        <td>{Number(ethers.formatEther(agentStake.total_stake)).toLocaleString()} ITK</td>
                        <td>—</td>
                      </tr>
                      <tr>
                        <td>Locked</td>
                        <td>{Number(ethers.formatEther(agentStake.locked_stake)).toLocaleString()} ITK</td>
                        <td>Locked</td>
                      </tr>
                      <tr>
                        <td>Available</td>
                        <td>{Number(ethers.formatEther(agentStake.available_stake)).toLocaleString()} ITK</td>
                        <td>Available</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                  {agentStake.open_disputes > 0
                    ? `${agentStake.open_disputes} open dispute(s) may result in slashing of locked stake.`
                    : 'No open disputes against this agent’s bond.'}
                </div>
              </>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
