// @ts-nocheck
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { getToken } from '../../services/userapi';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    X, 
    ChevronRight, 
    ChevronLeft, 
    Rocket, 
    Shield, 
    Zap, 
    Lock, 
    Fingerprint, 
    Code, 
    CheckCircle2, 
    Loader2, 
    ArrowRight,
    Cpu,
    Globe
} from 'lucide-react';
import { ethers } from 'ethers';
import { API_BASE } from '../../constants';

interface AgentOnboardingProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: (agentAddr: string) => void;
    editAgent?: any;
    userProfile?: any;
}

export const AgentOnboarding: React.FC<AgentOnboardingProps> = ({ isOpen, onClose, onSuccess, editAgent, userProfile }) => {
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState({
        alias: editAgent?.alias || '',
        xnsHandle: editAgent?.xns_handle?.replace('.intg', '') || userProfile?.handle || '',
        description: editAgent?.controller_entity || '',
        modelClass: editAgent?.agent_metadata?.modelClass || 'MEDIUM',
        controllerAddress: editAgent?.eth_address || '',
        vouchBy: ''
    });
    
    useEffect(() => {
        if (userProfile?.handle && !formData.xnsHandle) {
            setFormData(prev => ({ ...prev, xnsHandle: userProfile.handle }));
        }
    }, [userProfile]);

    const [isDeploying, setIsDeploying] = useState(false);
    const [deployedAddr, setDeployedAddr] = useState(editAgent?.eth_address || '');
    const [generatedWallet, setGeneratedWallet] = useState<{address: string, privateKey: string} | null>(null);

    const nextStep = () => setStep(s => s + 1);
    const prevStep = () => setStep(s => s - 1);

    const generateSovereignWallet = () => {
        const wallet = ethers.Wallet.createRandom();
        setGeneratedWallet({
            address: wallet.address,
            privateKey: wallet.privateKey
        });
        setFormData({ ...formData, controllerAddress: wallet.address });
    };

    const handleDeploy = async () => {
        setIsDeploying(true);
        try {
            // 1. Simulate smart contract deployment (or update commitment)
            await new Promise(r => setTimeout(r, 2000));
            const targetAddr = editAgent ? editAgent.eth_address : (formData.controllerAddress || `0x${Math.random().toString(16).substring(2, 42)}`);
            setDeployedAddr(targetAddr);

            // 2. Register/Update in Backend
            const jwt = getToken();
            const token = jwt ? `Bearer ${jwt}` : '';

            if (!token) {
                throw new Error("Authentication token missing. Please log in again.");
            }

            await axios.post(`${API_BASE}/v1/agent/register`, {
                eth_address: targetAddr,
                alias: formData.alias,
                xns_handle: formData.xnsHandle ? `${formData.xnsHandle}.intg` : null,
                description: formData.description
            }, {
                headers: { Authorization: token }
            });

            setIsDeploying(false);
            nextStep();
        } catch (error: any) {
            console.error("Registration failed:", error);
            setIsDeploying(false);
            const msg = error.response?.data?.detail || error.message || "Unknown error";
            alert(`Registration failed: ${msg}`);
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
                style={{ position: 'absolute', inset: 0, background: 'rgba(5, 13, 24, 0.9)', backdropFilter: 'blur(10px)' }} 
            />
            
            <motion.div 
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                style={{ 
                    position: 'relative', 
                    width: '100%', 
                    maxWidth: '900px', 
                    maxHeight: 'calc(100vh - 48px)',
                    background: 'var(--navy-deep)', 
                    border: '1px solid rgba(212, 175, 55, 0.2)', 
                    borderRadius: '32px', 
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    boxShadow: '0 40px 100px rgba(0,0,0,0.5)'
                }}
            >
                {/* Header */}
                <div style={{ padding: '32px 48px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'var(--gold-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)' }}>
                            <Rocket size={20} />
                        </div>
                        <div>
                            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0 }}>Agent Onboarding</h2>
                            <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', margin: 0 }}>Step {step} of 4: {getStepTitle(step)}</p>
                        </div>
                    </div>
                    <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer' }}>
                        <X size={24} />
                    </button>
                </div>

                {/* Progress Bar */}
                <div style={{ height: '4px', width: '100%', background: 'rgba(255,255,255,0.05)' }}>
                    <motion.div 
                        initial={{ width: '0%' }}
                        animate={{ width: `${(step / 4) * 100}%` }}
                        style={{ height: '100%', background: 'var(--gold)' }}
                    />
                </div>

                {/* Body */}
                <div style={{ flex: 1, padding: '48px', overflowY: 'auto' }}>
                    <AnimatePresence mode="wait">
                        {step === 1 && (
                            <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                                    <div className="flex-between mb-3">
                                        <h3 style={{ fontSize: '1.5rem', margin: 0 }}>Basic Identity</h3>
                                        <button 
                                            onClick={() => setFormData({
                                                ...formData,
                                                alias: 'Demo Sentinel ' + Math.floor(Math.random()*100),
                                                description: 'Autonomous research node for Xibalba Intelligence.',
                                                controllerAddress: `0x${Math.random().toString(16).substring(2, 42)}`
                                            })}
                                            style={{ background: 'rgba(212, 175, 55, 0.1)', border: '1px solid var(--gold)', borderRadius: '6px', color: 'var(--gold)', fontSize: '0.65rem', padding: '6px 12px', cursor: 'pointer' }}
                                        >
                                            Demo Auto-fill
                                        </button>
                                    </div>
                                    <p style={{ color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>Give your agent a unique alias and select its computational class. This data will be anchored to your SovereignAgent contract.</p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', marginBottom: '8px' }}>Agent Alias</label>
                                        <input 
                                            type="text" 
                                            placeholder="e.g. Neon Centurion" 
                                            value={formData.alias}
                                            onChange={e => setFormData({...formData, alias: e.target.value})}
                                            style={{ width: '100%', padding: '16px 24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', color: 'white', fontSize: '1rem' }}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', marginBottom: '8px' }}>Xibalba Name Service (XNS) Handle</label>
                                        <div style={{ position: 'relative' }}>
                                            <input 
                                                type="text" 
                                                placeholder="e.g. xibalba" 
                                                value={formData.xnsHandle}
                                                onChange={e => setFormData({...formData, xnsHandle: e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '')})}
                                                style={{ width: '100%', padding: '16px 120px 16px 24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', color: 'white', fontSize: '1rem', fontFamily: 'monospace' }}
                                            />
                                            <span style={{ position: 'absolute', right: '24px', top: '50%', transform: 'translateY(-50%)', color: 'var(--gold)', fontWeight: 800, fontSize: '0.9rem', pointerEvents: 'none' }}>.intg</span>
                                        </div>
                                        <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', marginTop: '8px' }}>Your unique identifier in the XNS registry. Permanently bound to your agent.</p>
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', marginBottom: '8px' }}>Agent Identity Description</label>
                                        <textarea 
                                            placeholder="Describe your agent's purpose and capabilities..." 
                                            value={formData.description}
                                            onChange={e => setFormData({...formData, description: e.target.value})}
                                            style={{ width: '100%', padding: '16px 24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', color: 'white', fontSize: '1rem', minHeight: '100px', resize: 'vertical' }}
                                        />
                                    </div>
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                            <label style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', margin: 0 }}>Agent Wallet Address (Controller)</label>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                <button 
                                                    onClick={generateSovereignWallet}
                                                    style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid #10b981', borderRadius: '6px', color: '#10b981', fontSize: '0.6rem', padding: '4px 8px', cursor: 'pointer' }}
                                                >
                                                    Generate New
                                                </button>
                                                <button 
                                                    onClick={async () => {
                                                        if (window.ethereum) {
                                                            const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
                                                            if (accounts && accounts[0]) {
                                                                setFormData({...formData, controllerAddress: accounts[0]});
                                                                setGeneratedWallet(null);
                                                            }
                                                        } else {
                                                            alert("No Web3 wallet detected. Please install MetaMask or similar.");
                                                        }
                                                    }}
                                                    style={{ background: 'transparent', border: '1px solid var(--gold)', borderRadius: '6px', color: 'var(--gold)', fontSize: '0.6rem', padding: '4px 8px', cursor: 'pointer' }}
                                                >
                                                    Connect Wallet
                                                </button>
                                            </div>
                                        </div>
                                        <input 
                                            type="text" 
                                            placeholder="0x..." 
                                            value={formData.controllerAddress}
                                            onChange={e => setFormData({...formData, controllerAddress: e.target.value})}
                                            style={{ width: '100%', padding: '16px 24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', color: 'white', fontSize: '1rem', fontFamily: 'monospace' }}
                                        />
                                        
                                        {generatedWallet && (
                                            <motion.div 
                                                initial={{ opacity: 0, height: 0 }}
                                                animate={{ opacity: 1, height: 'auto' }}
                                                style={{ marginTop: '12px', padding: '16px', background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '12px' }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', marginBottom: '8px' }}>
                                                    <Lock size={14} />
                                                    <span style={{ fontSize: '0.65rem', fontWeight: 800, textTransform: 'uppercase' }}>New Sovereign Wallet Generated</span>
                                                </div>
                                                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', marginBottom: '4px' }}>Private Key (SAVE THIS!):</div>
                                                <code style={{ fontSize: '0.75rem', color: 'white', wordBreak: 'break-all', background: 'black', padding: '4px 8px', borderRadius: '4px', display: 'block' }}>
                                                    {generatedWallet.privateKey}
                                                </code>
                                                <p style={{ fontSize: '0.6rem', color: '#f43f5e', marginTop: '8px', fontWeight: 700 }}>WARNING: Xibalba does not store your private key. If lost, the agent identity cannot be recovered.</p>
                                            </motion.div>
                                        )}
                                        <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', marginTop: '8px' }}>The Ethereum address that will have administrative rights over this agent.</p>
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', marginBottom: '16px' }}>Model Class</label>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                                            {['SMALL', 'MEDIUM', 'LARGE'].map(cls => (
                                                <button 
                                                    key={cls}
                                                    onClick={() => setFormData({...formData, modelClass: cls})}
                                                    style={{ 
                                                        padding: '20px', 
                                                        borderRadius: '16px', 
                                                        border: formData.modelClass === cls ? '2px solid var(--gold)' : '1px solid rgba(255,255,255,0.1)',
                                                        background: formData.modelClass === cls ? 'rgba(212, 175, 55, 0.05)' : 'rgba(255,255,255,0.02)',
                                                        color: formData.modelClass === cls ? 'white' : 'rgba(255,255,255,0.4)',
                                                        cursor: 'pointer',
                                                        transition: 'all 0.2s',
                                                        textAlign: 'center'
                                                    }}
                                                >
                                                    <div style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '4px' }}>{cls}</div>
                                                    <div style={{ fontSize: '0.6rem', opacity: 0.6 }}>{cls === 'SMALL' ? '< 7B' : cls === 'MEDIUM' ? '7B - 70B' : '> 70B'} Params</div>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {step === 2 && (
                            <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                                <div style={{ marginBottom: '40px' }}>
                                    <h3 style={{ fontSize: '1.5rem', marginBottom: '12px' }}>Sovereign Registry</h3>
                                    <p style={{ color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>Deploy your on-chain identity. This will mint a unique XID Identity NFT and anchor your agent to the Base Sepolia Reputation Registry.</p>
                                </div>
                                <div style={{ background: 'rgba(212, 175, 55, 0.05)', border: '1px solid rgba(212, 175, 55, 0.2)', padding: '32px', borderRadius: '24px', textAlign: 'center' }}>
                                    <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'var(--navy-deep)', border: '2px dashed var(--gold)', margin: '0 auto 24px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)' }}>
                                        <Fingerprint size={40} />
                                    </div>
                                    <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Mint Identity NFT</h4>
                                    <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', marginBottom: '32px' }}>Your reputation will be decoupled from your wallet and bound to this non-fungible asset.</p>
                                    
                                    <button 
                                        onClick={handleDeploy}
                                        disabled={isDeploying}
                                        className="btn btn-primary" 
                                        style={{ padding: '16px 40px', fontSize: '0.9rem', width: '100%' }}
                                    >
                                        {isDeploying ? (
                                            <><Loader2 className="animate-spin" size={20} /> Anchoring to Base Sepolia...</>
                                        ) : (
                                            <><Lock size={18} /> Initialize Sovereign Contract</>
                                        )}
                                    </button>
                                </div>
                            </motion.div>
                        )}

                        {step === 3 && (
                            <motion.div key="step3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                                <div style={{ marginBottom: '40px' }}>
                                    <h3 style={{ fontSize: '1.5rem', marginBottom: '12px' }}>SDK Orchestration</h3>
                                    <p style={{ color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>Your identity is live. Now, link your agentic fleet to the Xibalba Oracle to begin earning reputation points.</p>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                    <div style={{ background: '#0a0b0d', padding: '24px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                        <div className="flex-between mb-4">
                                            <span style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--gold)' }}>CONFIG_SECRET</span>
                                            <Code size={14} style={{ color: 'rgba(255,255,255,0.3)' }} />
                                        </div>
                                        <code style={{ fontSize: '0.8rem', color: '#10b981' }}>{`const client = new IntegrityClient({\n  agentAddress: "${deployedAddr}",\n  network: "base-sepolia"\n});`}</code>
                                    </div>
                                    <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                        <Cpu size={24} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                                        <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', margin: 0 }}><strong>Telemetry Active:</strong> The Xibalba Interceptor will automatically detect this contract and start streaming Tri-Metric signals once initialized.</p>
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {step === 4 && (
                            <motion.div key="step4" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} style={{ textAlign: 'center' }}>
                                <div style={{ width: '120px', height: '120px', borderRadius: '50%', background: '#10b98111', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 40px', border: '2px solid #10b981' }}>
                                    <CheckCircle2 size={64} />
                                </div>
                                <h3 style={{ fontSize: '2.5rem', marginBottom: '16px', fontFamily: 'Playfair Display, serif' }}>Agent Sovereign.</h3>
                                <p style={{ fontSize: '1.1rem', color: 'rgba(255,255,255,0.6)', maxWidth: '500px', margin: '0 auto 48px' }}>
                                    Congratulations! <strong>{formData.alias}</strong> is now a verified node in the Integrity Protocol.
                                </p>
                                
                                 <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '48px' }}>
                                    <div style={{ padding: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                        <div style={{ fontSize: '0.6rem', color: 'var(--gold)', fontWeight: 800, marginBottom: '8px' }}>ENTROPY</div>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>880</div>
                                    </div>
                                    <div style={{ padding: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                        <div style={{ fontSize: '0.6rem', color: '#10b981', fontWeight: 800, marginBottom: '8px' }}>GROUNDING</div>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>920</div>
                                    </div>
                                    <div style={{ padding: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                        <div style={{ fontSize: '0.6rem', color: '#60a5fa', fontWeight: 800, marginBottom: '8px' }}>SACRIFICE</div>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>750</div>
                                    </div>
                                    <div style={{ padding: '24px', background: 'rgba(212, 175, 55, 0.1)', borderRadius: '20px', border: '1px solid var(--gold)' }}>
                                        <div style={{ fontSize: '0.6rem', color: 'var(--gold)', fontWeight: 800, marginBottom: '8px' }}>INITIAL AIS</div>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>850</div>
                                    </div>
                                </div>

                                <button 
                                    onClick={() => { onSuccess(deployedAddr); onClose(); }}
                                    className="btn btn-primary" 
                                    style={{ padding: '16px 48px', fontSize: '0.9rem' }}
                                >
                                    Enter Command Center <ArrowRight size={18} style={{ marginLeft: '12px' }} />
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* Footer Controls */}
                {step < 4 && (
                    <div style={{ padding: '32px 48px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', background: 'rgba(0,0,0,0.1)' }}>
                        <button 
                            onClick={prevStep} 
                            disabled={step === 1 || isDeploying}
                            style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', opacity: step === 1 ? 0.3 : 1 }}
                        >
                            <ChevronLeft size={20} /> Back
                        </button>
                        {step !== 2 && (
                            <button 
                                onClick={nextStep}
                                disabled={step === 1 && (!formData.alias || !formData.controllerAddress)}
                                className="btn btn-primary"
                                style={{ padding: '12px 32px' }}
                            >
                                Continue <ChevronRight size={20} />
                            </button>
                        )}
                    </div>
                )}
            </motion.div>
        </div>
    );
};

function getStepTitle(step: number) {
    switch(step) {
        case 1: return "Agent Identity";
        case 2: return "On-Chain Registry";
        case 3: return "SDK Configuration";
        case 4: return "Finalized";
        default: return "";
    }
}
