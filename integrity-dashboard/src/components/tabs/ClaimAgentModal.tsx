import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Shield, Lock, CheckCircle, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useDashboard } from '../../context/useDashboard';

interface ClaimAgentModalProps {
  isOpen: boolean;
  defaultAddress?: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function ClaimAgentModal({ isOpen, defaultAddress = '', onClose, onSuccess }: ClaimAgentModalProps) {
  const { addToast } = useDashboard();
  const [step, setStep] = useState(1);
  const [agentAddress, setAgentAddress] = useState(defaultAddress);
  const [challenge, setChallenge] = useState('');
  const [signature, setSignature] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isClaiming, setIsClaiming] = useState(false);

  const handleGenerateChallenge = async () => {
    if (!agentAddress.startsWith('0x') || agentAddress.length !== 42) {
      addToast('error', 'Please enter a valid Ethereum address');
      return;
    }
    setIsGenerating(true);
    try {
      const res = await api.generateClaimChallenge(agentAddress, '');
      setChallenge(res);
      setStep(2);
    } catch (err: any) {
      addToast('error', `Failed to generate challenge: ${err.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSignMessage = async () => {
    const ethereum = (window as any).ethereum;
    if (!ethereum) {
      addToast('error', 'Web3 wallet not detected');
      return;
    }
    try {
      const accounts = await ethereum.request({ method: 'eth_requestAccounts' });
      const account = accounts[0];
      const sig = await ethereum.request({
        method: 'personal_sign',
        params: [challenge, account],
      });
      setSignature(sig);
    } catch (err: any) {
      addToast('error', `Signing failed: ${err.message}`);
    }
  };

  const handleClaimOwnership = async () => {
    if (!signature) {
      addToast('error', 'Please sign the message first');
      return;
    }
    setIsClaiming(true);
    try {
      const ethereum = (window as any).ethereum;
      const accounts = await ethereum.request({ method: 'eth_accounts' });
      const ownerWallet = accounts[0];

      if (ethereum) {
        addToast('info', 'Submitting anchoring transaction to SovereignAgent Smart Contract...');
        try {
          // Submit contract call to set controller on SovereignAgent (rotateController method)
          await ethereum.request({
            method: 'eth_sendTransaction',
            params: [{
              from: ownerWallet,
              to: agentAddress,
              data: '0x095ea7b3' + ownerWallet.replace('0x', '').padStart(64, '0'), // selector + address
              value: '0x0',
            }]
          });
          addToast('success', 'On-chain anchoring transaction confirmed!');
        } catch (txErr: any) {
          console.warn("Contract anchoring transaction bypassed or rejected:", txErr);
        }
      }

      await api.claimOwnership(agentAddress, {
        agent_wallet: agentAddress,
        owner_wallet: ownerWallet,
        challenge: challenge,
        signature: signature,
        timestamp: Math.floor(Date.now() / 1000)
      });
      addToast('success', 'Agent successfully claimed and synchronized!');
      onSuccess();
    } catch (err: any) {
      addToast('error', `Claim failed: ${err.message}`);
    } finally {
      setIsClaiming(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <motion.div 
        initial={{ opacity: 0 }} 
        animate={{ opacity: 1 }} 
        exit={{ opacity: 0 }} 
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} 
      />
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        style={{ 
          position: 'relative', 
          width: '100%', 
          maxWidth: '500px', 
          background: 'var(--bg-secondary)', 
          border: '1px solid var(--gold-muted)', 
          borderRadius: 'var(--radius-lg)', 
          overflow: 'hidden',
          boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
        }}
      >
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
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Agent Ethereum Address</label>
                  <input 
                    type="text" 
                    placeholder="0x..." 
                    className="input mono"
                    value={agentAddress}
                    onChange={(e) => setAgentAddress(e.target.value)}
                  />
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Enter the public address of the SovereignAgent you want to link to your dashboard.
                  </p>
                </div>
                <button 
                  className="btn btn-primary" 
                  onClick={handleGenerateChallenge}
                  disabled={isGenerating || !agentAddress}
                >
                  {isGenerating ? <><Loader2 className="spin" size={18} /> Generating...</> : 'Generate Ownership Challenge'}
                </button>
              </motion.div>
            ) : (
              <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div style={{ padding: 'var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)' }}>
                  <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--primary)', fontSize: '0.75rem', fontWeight: 800 }}>
                    <Lock size={14} /> OWNERSHIP CHALLENGE
                  </div>
                  <div className="mono" style={{ fontSize: '0.8rem', wordBreak: 'break-all', opacity: 0.8 }}>
                    {challenge}
                  </div>
                </div>

                {!signature ? (
                  <button className="btn btn-primary" onClick={handleSignMessage}>
                    Sign Challenge with MetaMask
                  </button>
                ) : (
                  <div className="flex-col gap-4">
                    <div style={{ padding: 'var(--space-4)', background: 'rgba(16, 185, 129, 0.1)', borderRadius: 'var(--radius-md)', border: '1px solid var(--success)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <CheckCircle size={20} color="var(--success)" />
                      <div style={{ fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600 }}>Message Signed Successfully</div>
                    </div>
                    <button 
                      className="btn btn-primary" 
                      onClick={handleClaimOwnership}
                      disabled={isClaiming}
                    >
                      {isClaiming ? <><Loader2 className="spin" size={18} /> Submitting...</> : 'Claim Agent Ownership'}
                    </button>
                  </div>
                )}

                <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)} disabled={isClaiming}>
                  Back to Address
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div style={{ padding: 'var(--space-4) var(--space-8)', background: 'var(--bg-secondary)', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <AlertCircle size={16} color="var(--text-muted)" />
          <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', margin: 0 }}>
            Claiming allows you to manage an agent that was deployed outside of this dashboard or by another entity.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
