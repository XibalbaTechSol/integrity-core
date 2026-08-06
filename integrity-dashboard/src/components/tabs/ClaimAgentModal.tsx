import { useState } from 'react';
import { ethers } from 'ethers';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Shield, Lock, CheckCircle, Loader2, AlertCircle, XCircle } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { oracle } from '../../services/oracle';
import { SOVEREIGN_AGENT_ABI } from '../../chain/bytecode';

interface ClaimAgentModalProps {
  isOpen: boolean;
  defaultAddress?: string;
  onClose: () => void;
  onSuccess: () => void;
}

// Real "claim" (no mock challenge/signature theater). Control of a SovereignAgent is
// held as its DEFAULT_ADMIN_ROLE (AccessControl) — the `onlyController` modifier is just
// hasRole(DEFAULT_ADMIN_ROLE, msg.sender). So the honest, on-chain proof of ownership is
// reading that role for the connected wallet; a signed string proves nothing the chain
// doesn't already record. If the wallet controls the agent we link it in the oracle
// (associating the DID with this owner); if it doesn't, we say so plainly — only the
// current controller can transfer control via SovereignAgent.rotateController.
export function ClaimAgentModal({ isOpen, defaultAddress = '', onClose, onSuccess }: ClaimAgentModalProps) {
  const { addToast, walletAddress, connectWallet } = useDashboard();
  const [step, setStep] = useState<1 | 2>(1);
  const [agentAddress, setAgentAddress] = useState(defaultAddress);
  const [isChecking, setIsChecking] = useState(false);
  const [isLinking, setIsLinking] = useState(false);
  const [result, setResult] = useState<{ did: string; controls: boolean } | null>(null);

  const handleVerify = async () => {
    if (!ethers.isAddress(agentAddress)) {
      addToast('error', 'Please enter a valid Ethereum address');
      return;
    }
    if (!walletAddress) {
      addToast('error', 'Connect a wallet first — control is checked against it.');
      return;
    }
    setIsChecking(true);
    try {
      const provider = new ethers.BrowserProvider((window as any).ethereum);
      const sa = new ethers.Contract(agentAddress, SOVEREIGN_AGENT_ABI, provider);
      // agentDID() also validates this is really a SovereignAgent (a non-SA address reverts).
      const did: string = await sa.agentDID();
      const adminRole: string = await sa.DEFAULT_ADMIN_ROLE();
      const controls: boolean = await sa.hasRole(adminRole, walletAddress);
      setResult({ did, controls });
      setStep(2);
    } catch (err: any) {
      addToast('error', `Not a resolvable SovereignAgent: ${err.shortMessage || err.message}`);
    } finally {
      setIsChecking(false);
    }
  };

  const handleLink = async () => {
    if (!result || !walletAddress) return;
    setIsLinking(true);
    try {
      // Resolve the real 7-primitive set the oracle derives from XibalbaAgentRegistry,
      // then record the association (the oracle re-verifies primitives on-chain).
      const detail = await oracle.getAgent(agentAddress);
      if (!detail.primitives) throw new Error('Agent primitives not resolvable on-chain yet.');
      await oracle.register({
        did: result.did,
        did_document: { id: result.did, controller: walletAddress },
        primitives: detail.primitives,
        eth_address_hex: walletAddress,
      });
      addToast('success', 'Agent linked to your dashboard.');
      onSuccess();
    } catch (err: any) {
      addToast('error', `Link failed: ${err.message}`);
    } finally {
      setIsLinking(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} />

      <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        style={{ position: 'relative', width: '100%', maxWidth: '500px', background: 'var(--bg-secondary)', border: '1px solid var(--gold-muted)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', boxShadow: '0 20px 50px rgba(0,0,0,0.6)' }}>
        <div style={{ padding: 'var(--space-6)', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--navy-light)' }}>
          <div className="flex items-center gap-3">
            <Shield size={20} color="var(--gold)" />
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'white' }}>Claim Existing Agent</h3>
          </div>
          <button onClick={onClose} className="btn btn-icon" aria-label="Close modal"><X size={20} /></button>
        </div>

        <div style={{ padding: 'var(--space-8)' }}>
          <AnimatePresence mode="wait">
            {step === 1 ? (
              <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div className="flex-col gap-2">
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>SovereignAgent Address</label>
                  <input type="text" placeholder="0x..." className="input mono" value={agentAddress} onChange={(e) => setAgentAddress(e.target.value)} />
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Enter the SovereignAgent contract address. We check on-chain whether your connected wallet holds its controller role.
                  </p>
                </div>
                {!walletAddress ? (
                  <button className="btn btn-primary" onClick={connectWallet}>Connect Wallet</button>
                ) : (
                  <button className="btn btn-primary" onClick={handleVerify} disabled={isChecking || !agentAddress}>
                    {isChecking ? <><Loader2 className="spin" size={18} /> Checking control…</> : 'Verify Control On-Chain'}
                  </button>
                )}
              </motion.div>
            ) : (
              <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div style={{ padding: 'var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--primary)', fontSize: '0.75rem', fontWeight: 800 }}>
                    <Lock size={14} /> AGENT DID
                  </div>
                  <div className="mono" style={{ fontSize: '0.8rem', wordBreak: 'break-all', opacity: 0.8 }}>{result?.did}</div>
                </div>

                {result?.controls ? (
                  <div className="flex-col gap-4">
                    <div style={{ padding: 'var(--space-4)', background: 'rgba(16, 185, 129, 0.1)', borderRadius: 'var(--radius-md)', border: '1px solid var(--success)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <CheckCircle size={20} color="var(--success)" />
                      <div style={{ fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600 }}>Your wallet holds this agent's controller role.</div>
                    </div>
                    <button className="btn btn-primary" onClick={handleLink} disabled={isLinking}>
                      {isLinking ? <><Loader2 className="spin" size={18} /> Linking…</> : 'Link Agent to Dashboard'}
                    </button>
                  </div>
                ) : (
                  <div style={{ padding: 'var(--space-4)', background: 'rgba(239, 68, 68, 0.08)', borderRadius: 'var(--radius-md)', border: '1px solid var(--danger)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--danger)', fontWeight: 600, fontSize: '0.85rem' }}>
                      <XCircle size={18} /> Connected wallet is not the controller.
                    </div>
                    <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0 }}>
                      Only the agent's current controller can transfer control (SovereignAgent.rotateController). Connect the controlling wallet, or have the current controller rotate control to <span className="mono">{walletAddress?.slice(0, 6)}…{walletAddress?.slice(-4)}</span>.
                    </p>
                  </div>
                )}

                <button className="btn btn-ghost btn-sm" onClick={() => { setStep(1); setResult(null); }} disabled={isLinking}>
                  Back to Address
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div style={{ padding: 'var(--space-4) var(--space-8)', background: 'var(--bg-secondary)', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <AlertCircle size={16} color="var(--text-muted)" />
          <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', margin: 0 }}>
            Claiming links an agent you already control on-chain (deployed outside this dashboard) to your session.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
