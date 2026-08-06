// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, ShieldCheck, Cpu, Database, ChevronRight, Activity, Fingerprint } from 'lucide-react';

export const LiveVerificationBridge: React.FC = () => {
    const [activeTx, setActiveTx] = useState<any>(null);
    const [bridgeStatus, setBridgeStatus] = useState<'IDLE' | 'CALCULATING' | 'VERIFYING' | 'COMMITTED'>('IDLE');

    useEffect(() => {
        const runSimulation = () => {
            const txs = [
                { id: 'TX_8821', agent: '0xTest...8a', e: 0.042, g: 0.98, s: 1200 },
                { id: 'TX_9104', agent: '0x71C...6F', e: 0.015, g: 0.94, s: 850 },
                { id: 'TX_1102', agent: '0xBB8...5F', e: 0.089, g: 0.72, s: 3000 }
            ];
            
            const selected = txs[Math.floor(Math.random() * txs.length)];
            setActiveTx(selected);
            setBridgeStatus('CALCULATING');

            setTimeout(() => setBridgeStatus('VERIFYING'), 2500);
            setTimeout(() => setBridgeStatus('COMMITTED'), 5000);
            setTimeout(() => {
                setBridgeStatus('IDLE');
                setActiveTx(null);
            }, 8000);
        };

        const interval = setInterval(runSimulation, 10000);
        runSimulation();
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="enterprise-card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>

            <div className="card-header" style={{ borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Terminal size={18} style={{ color: 'var(--gold)' }} />
                    <h2 style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--navy)', textTransform: 'uppercase', letterSpacing: '0.25em', margin: 0 }}>Live Verification Bridge</h2>
                </div>
                <div className="badge badge-gold animate-pulse">ORACLE_LISTENING</div>
            </div>
            <div style={{ padding: '0 32px 16px', fontSize: '0.65rem', color: 'var(--text-secondary)', lineHeight: 1.5, borderBottom: '1px solid var(--border)', textAlign: 'justify' }}>
                Cross-chain communication layer bridging off-chain computation with on-chain finality. Monitors the real-time transmission of ZK-Reputation proofs from the secure oracle enclave down to the Ethereum L2 settlement registry. The bridge ensures that all integrity state updates are mathematically verified before being committed, preventing spoofed telemetry from corrupting the protocol's global reputation ledger while maintaining low gas costs.
            </div>

            <div className="card-body" style={{ flex: 1, padding: '32px', display: 'flex', flexDirection: 'column', gap: '32px', justifyContent: 'center' }}>
                
                {/* Visual Bridge */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px', position: 'relative' }}>
                    
                    {/* Source: Agent Node */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '64px', height: '64px', borderRadius: '16px', background: 'var(--off-white)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--navy)' }}>
                            <Cpu size={28} />
                        </div>
                        <span style={{ fontSize: '0.6rem', fontWeight: 900, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Agent Node</span>
                    </div>

                    <div style={{ flex: 2, position: 'relative', height: '60px' }}>
                        {/* Connection Line */}
                        <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: '1px', background: 'var(--border)', transform: 'translateY(-50%)' }} />
                        
                        {/* Data Packets */}
                        <AnimatePresence>
                            {bridgeStatus === 'CALCULATING' && (
                                <>
                                    <motion.div initial={{ left: 0 }} animate={{ left: '100%' }} transition={{ duration: 1.5, repeat: Infinity }} style={{ position: 'absolute', top: '40%', width: '10px', height: '1px', background: 'var(--gold)', boxShadow: '0 0 10px var(--gold)' }} />
                                    <motion.div initial={{ left: 0 }} animate={{ left: '100%' }} transition={{ duration: 1.5, delay: 0.5, repeat: Infinity }} style={{ position: 'absolute', top: '50%', width: '10px', height: '1px', background: 'var(--navy-light)', boxShadow: '0 0 10px var(--navy-light)' }} />
                                    <motion.div initial={{ left: 0 }} animate={{ left: '100%' }} transition={{ duration: 1.5, delay: 1, repeat: Infinity }} style={{ position: 'absolute', top: '60%', width: '10px', height: '1px', background: 'var(--gold)', boxShadow: '0 0 10px var(--gold)' }} />
                                </>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* Middle: Smart Contract Calculation */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                        <motion.div 
                            animate={{ 
                                borderColor: bridgeStatus === 'CALCULATING' ? 'var(--gold)' : 'var(--border)',
                                scale: bridgeStatus === 'CALCULATING' ? 1.1 : 1,
                                boxShadow: bridgeStatus === 'CALCULATING' ? 'var(--shadow-gold)' : 'none'
                            }}
                            style={{ width: '80px', height: '80px', borderRadius: '20px', background: 'var(--background)', border: '2px solid', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--navy)' }}
                        >
                            <Database size={32} />
                        </motion.div>
                        <span style={{ fontSize: '0.6rem', fontWeight: 900, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'center' }}>Base L2<br/>Calculation</span>
                    </div>

                    <div style={{ flex: 2, position: 'relative', height: '60px' }}>
                        <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: '1px', background: 'var(--border)', transform: 'translateY(-50%)' }} />
                        
                        <AnimatePresence>
                            {bridgeStatus === 'VERIFYING' && (
                                <motion.div initial={{ left: 0 }} animate={{ left: '100%' }} transition={{ duration: 1.2 }} style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: '8px', background: 'var(--gold)', color: 'var(--navy)', padding: '4px 12px', borderRadius: '20px', fontSize: '0.6rem', fontWeight: 900 }}>
                                    <ShieldCheck size={12} /> XIBALBA_SIG
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* Destination: Xibalba Oracle Verify */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                        <motion.div 
                            animate={{ 
                                background: bridgeStatus === 'COMMITTED' ? 'var(--navy)' : 'var(--off-white)',
                                color: bridgeStatus === 'COMMITTED' ? 'var(--gold)' : 'var(--slate)',
                                borderColor: bridgeStatus === 'COMMITTED' ? 'var(--gold)' : 'var(--border)'
                            }}
                            style={{ width: '64px', height: '64px', borderRadius: '16px', border: '1px solid', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                        >
                            <ShieldCheck size={28} />
                        </motion.div>
                        <span style={{ fontSize: '0.6rem', fontWeight: 900, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Xibalba Oracle</span>
                    </div>
                </div>

                {/* Live Console Output */}
                <div style={{ backgroundColor: 'var(--navy-deep)', padding: '24px', borderRadius: '12px', color: '#10b981', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', overflow: 'hidden', border: '1px solid rgba(201, 168, 76, 0.2)' }}>
                    <div style={{ marginBottom: '16px', borderBottom: '1px solid rgba(16, 185, 129, 0.1)', paddingBottom: '8px', color: 'var(--gold)', fontWeight: 800 }}>
                        {activeTx ? `SYSTEM_BRIDGE :: ${activeTx.id}` : 'SYSTEM_BRIDGE :: IDLE'}
                    </div>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ display: 'flex', gap: '12px' }}>
                            <span style={{ opacity: 0.5 }}>{'>'}</span>
                            <span>INBOUND_TELEMETRY: {activeTx?.agent || 'NULL'}</span>
                        </div>
                        
                        <AnimatePresence>
                            {bridgeStatus !== 'IDLE' && (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <span style={{ opacity: 0.5 }}>{'>'}</span>
                                        <span style={{ color: 'var(--off-white)' }}>CONTRACT_CALC: AIS = 0.45({activeTx?.e}) + 0.35({activeTx?.g}) + 0.20(min(1, {activeTx?.s}/1000))</span>
                                    </div>
                                </motion.div>
                            )}

                            {(bridgeStatus === 'VERIFYING' || bridgeStatus === 'COMMITTED') && (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <span style={{ opacity: 0.5 }}>{'>'}</span>
                                        <span style={{ color: 'var(--gold)' }}>XIBALBA_AUTH: GENERATING_ZK_PROOF... [OK]</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <span style={{ opacity: 0.5 }}>{'>'}</span>
                                        <span style={{ color: 'var(--gold)' }}>XIBALBA_SIG: 0x8a92...f192_VALIDATED</span>
                                    </div>
                                </motion.div>
                            )}

                            {bridgeStatus === 'COMMITTED' && (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <span style={{ opacity: 0.5 }}>{'>'}</span>
                                        <span style={{ color: '#10b981' }}>COMMIT_SUCCESS: STATE_PROPAGATED_TO_BASE_L2</span>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </div>
        </div>
    );
};
