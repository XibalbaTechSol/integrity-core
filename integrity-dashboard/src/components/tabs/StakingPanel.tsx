import { useState } from 'react';
import { Panel } from '../shared/Panel';
import { Lock, Coins, TrendingUp, AlertTriangle } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { oracle } from '../../services/oracle';
import { ethers } from 'ethers';
import { ITK_TOKEN_ADDRESS } from '../../constants';
import ITK_ABI from '../abi/IntegrityToken.json';

// Staking in this protocol is per-agent: an agent bonds $ITK into its OWN Slasher
// clone (Slasher.stake), never a monolithic "protocol" contract. The Slasher address
// is resolved live from the agent's on-chain primitive set — never hardcoded. Minimal
// ABI: just the write we call here (the read side is the /v1/agent/{id}/stake endpoint).
const SLASHER_ABI = ['function stake(uint256 amount)'] as const;

export function StakingPanel() {
  const { selectedAgent, stats, addToast, fetchData, walletAddress } = useDashboard();
  const [stakeAmount, setStakeAmount] = useState<string>('');
  const [isStaking, setIsStaking] = useState(false);

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
      const itkContract = new ethers.Contract(ITK_TOKEN_ADDRESS, ITK_ABI.abi, signer);
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
      // Real on-chain stake now reflects via the /v1/agent/{id}/stake read on refresh.
      if (fetchData) await fetchData();
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
              {selectedAgent ? selectedAgent.staked_itk.toLocaleString() : '0'}
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Active Bond (ITK)</div>
          </div>
        </Panel>

        <Panel title="Staking Yield" icon={<Coins size={18} />}>
          <div className="flex-col items-center justify-center p-4">
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--secondary)' }}>
              {stats ? '8.4%' : '0%'}
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Current APR</div>
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
                  <div className="flex justify-between items-center" style={{ fontSize: '0.75rem' }}>
                    <span>Estimated AIS Boost:</span>
                    <span style={{ fontWeight: 600 }}>+{Math.floor(Number(stakeAmount || 0) / 100)} pts</span>
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
            <div className="flex justify-between items-center">
              <span style={{ fontSize: '0.875rem' }}>Maintenance Margin</span>
              <span style={{ fontWeight: 600 }}>120%</span>
            </div>
            <div style={{ width: '100%', height: '8px', background: 'var(--bg-secondary)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ width: '85%', height: '100%', background: 'var(--success)' }}></div>
            </div>
            <div className="text-muted" style={{ fontSize: '0.75rem' }}>
              Your current collateralization ratio is healthy. Slashed funds are diverted to the Insurance Pool.
            </div>

            <div className="table-container" style={{ marginTop: 'var(--space-2)' }}>
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
                    <td>Initial Bond</td>
                    <td>10,000 ITK</td>
                    <td>Locked</td>
                  </tr>
                  <tr>
                    <td>Performance Buffer</td>
                    <td>2,500 ITK</td>
                    <td>Available</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
