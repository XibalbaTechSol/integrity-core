import { useState } from 'react';
import { ethers } from 'ethers';
import { Globe, Loader2 } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { oracle } from '../../services/oracle';
import { XNS_ADDRESS } from '../../constants';
import { XNS_ABI } from '../../chain/xns';
import { executeAsAgent } from '../../chain/markets';

// PRODUCTION_GAPS.md §4: the register-handle *write* flow was a deliberate deferral
// ("CLI/SDK for now"). This closes it the same way every other on-chain write in this
// dashboard works — routed through the agent's own SovereignAgent.execute (see
// chain/markets.ts's executeAsAgent), never a direct wallet-EOA call, because
// XibalbaNameService.register requires msg.sender to be a registered agent contract.
export function XNSRegisterForm() {
  const { selectedAgent, walletAddress, addToast } = useDashboard();
  const [handle, setHandle] = useState('');
  const [busy, setBusy] = useState(false);

  const handleRegister = async () => {
    const trimmed = handle.trim();
    if (!trimmed) { addToast('error', 'Enter a handle to register.'); return; }
    if (!selectedAgent) { addToast('error', 'Select an agent first.'); return; }
    if (!walletAddress) { addToast('error', 'Connect the agent controller wallet.'); return; }
    if (!XNS_ADDRESS) { addToast('error', 'XibalbaNameService is not deployed on this network.'); return; }

    setBusy(true);
    try {
      const eth = (window as any).ethereum;
      if (!eth) throw new Error('No Web3 wallet detected.');
      const signer = await new ethers.BrowserProvider(eth).getSigner();

      const sa = await oracle.resolveSovereignAgent(selectedAgent.eth_address);
      if (!sa) throw new Error('This agent has no on-chain SovereignAgent yet.');

      const data = new ethers.Interface(XNS_ABI as any).encodeFunctionData('register', [trimmed]);
      await executeAsAgent(signer, sa, XNS_ADDRESS, data);

      addToast('success', `Registered handle "${trimmed}".`);
      setHandle('');
    } catch (err: any) {
      addToast('error', `Registration failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
      <div style={{
        display: 'flex', flex: 1, gap: '8px', background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border)', borderRadius: 'var(--r-md)',
        padding: '4px 4px 4px 12px', alignItems: 'center',
      }}>
        <Globe size={16} className="text-muted" />
        <input
          type="text"
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !busy && handleRegister()}
          placeholder="Register a handle for your agent (e.g. myagent)"
          style={{ flex: 1, background: 'transparent', border: 'none', color: 'white', fontSize: '0.85rem', outline: 'none', padding: '8px 0' }}
        />
      </div>
      <button
        onClick={handleRegister}
        disabled={busy || !handle.trim()}
        className="btn btn-sm btn-primary"
        style={{ borderRadius: 'calc(var(--r-md) - 2px)' }}
      >
        {busy ? <Loader2 size={14} className="pulse" /> : 'Register'}
      </button>
    </div>
  );
}
