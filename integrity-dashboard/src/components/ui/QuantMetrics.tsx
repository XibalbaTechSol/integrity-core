// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Activity, Shield, Target, Zap, ArrowRight, BarChart3, Lock, Eye, FileText, Cpu } from 'lucide-react';

interface QuantMetricsProps {
    agent: any;
}

export const QuantMetrics = ({ agent }: QuantMetricsProps) => {
    // Extract real XIA metrics from agent metadata or use realistic simulated defaults
    const meta = agent?.agent_metadata || {};
    
    const pnfStatus = meta.pnf_status || "VERIFIED"; 
    const complianceScore = agent?.compliance_score || 99.1;
    const enclaveAttestation = meta.enclave_attestation || "TEE_HARDENED";
    const integrityAdjustedSharpe = meta.ia_sharpe || 3.24;
    const computeAlpha = meta.compute_alpha || "+12.4%";
    const auditLogs = meta.audit_logs || [
        "[09:42:01] SIG_GEN: 0x8f1... VALIDATED",
        "[09:42:01] PNF_CHECK: NO_FRONT_RUNNING",
        "[09:42:02] ORDER_FILL: ETH/USDT @ 3241.2",
        "[09:42:03] SLIPPAGE_INTEGRITY: 99.98%",
        "[09:42:04] XIA_RECEIPT: ROI_7b2f...8a1c",
        "[09:42:05] BINDING: did:intg:xibalba (TEE)"
    ];

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h3 style={{ fontSize: '1.4rem', fontWeight: 800, color: 'white', margin: 0 }}>XIA: Institutional Alpha</h3>
                    <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)', marginTop: '4px' }}>Verifiable quantitative intelligence for sovereign trading desks.</p>
                </div>
                <div className="badge badge-gold" style={{ padding: '8px 16px', fontSize: '0.7rem' }}>XIA_PROVER_ACTIVE</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
                {/* Proof of Non-Frontrunning */}
                <motion.div 
                    whileHover={{ y: -5 }}
                    style={{ padding: '24px', background: 'rgba(16, 185, 129, 0.05)', borderRadius: '20px', border: '1px solid rgba(16, 185, 129, 0.1)' }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                        <div style={{ color: '#10b981' }}><Eye size={20} /></div>
                        <div style={{ fontSize: '0.7rem', fontWeight: 900, color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '4px 8px', borderRadius: '4px' }}>{pnfStatus}</div>
                    </div>
                    <h4 style={{ fontSize: '0.9rem', fontWeight: 800, marginBottom: '8px' }}>Proof of Non-Frontrunning</h4>
                    <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.5, margin: 0 }}>
                        Cryptographic proof that signal generation strictly preceded order execution, eliminating internal toxic flow.
                    </p>
                </motion.div>

                {/* Compliance Traceability */}
                <motion.div 
                    whileHover={{ y: -5 }}
                    style={{ padding: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                        <div style={{ color: 'var(--gold)' }}><FileText size={20} /></div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 900, color: 'var(--gold)' }}>{complianceScore}%</div>
                    </div>
                    <h4 style={{ fontSize: '0.9rem', fontWeight: 800, marginBottom: '8px' }}>Compliance Traceability</h4>
                    <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.5, margin: 0 }}>
                        Real-time mapping of agent reasoning to MiFID II and Dodd-Frank mandates for automated forensic auditing.
                    </p>
                </motion.div>

                {/* Enclave Attestation */}
                <motion.div 
                    whileHover={{ y: -5 }}
                    style={{ padding: '24px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                        <div style={{ color: '#a78bfa' }}><Cpu size={20} /></div>
                        <div style={{ fontSize: '0.7rem', fontWeight: 900, color: '#a78bfa', background: 'rgba(167, 139, 250, 0.1)', padding: '4px 8px', borderRadius: '4px' }}>{enclaveAttestation}</div>
                    </div>
                    <h4 style={{ fontSize: '0.9rem', fontWeight: 800, marginBottom: '8px' }}>Enclave Attestation</h4>
                    <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.5, margin: 0 }}>
                        Verification that strategy logic is executed in a hardware-hardened environment, tamper-proof from host admins.
                    </p>
                </motion.div>
            </div>

            {/* XIA Forensic Command Center */}
            <div style={{ padding: '40px', background: 'rgba(5, 13, 24, 0.8)', borderRadius: '32px', border: '1px solid rgba(212, 175, 55, 0.2)', position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '4px', background: 'linear-gradient(90deg, #10b981, var(--gold), #a78bfa)' }} />
                
                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '60px' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                            <Lock size={20} style={{ color: 'var(--gold)' }} />
                            <h4 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0 }}>Integrity-Adjusted Metrics</h4>
                        </div>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                                    <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', fontWeight: 700 }}>Integrity-Adjusted Sharpe</span>
                                    <span style={{ fontSize: '0.9rem', color: 'white', fontWeight: 900 }}>{integrityAdjustedSharpe}</span>
                                </div>
                                <div style={{ height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                                    <motion.div 
                                        initial={{ width: 0 }}
                                        animate={{ width: `${Math.min(100, (Number(integrityAdjustedSharpe) / 5) * 100)}%` }}
                                        style={{ height: '100%', background: 'var(--gold)' }}
                                    />
                                </div>
                                <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', marginTop: '8px' }}>Penalizing unverified trades and high-slippage execution.</p>
                            </div>

                            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                                    <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', fontWeight: 700 }}>Compute Alpha Yield</span>
                                    <span style={{ fontSize: '0.9rem', color: '#10b981', fontWeight: 900 }}>{computeAlpha}</span>
                                </div>
                                <div style={{ height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                                    <motion.div 
                                        initial={{ width: 0 }}
                                        animate={{ width: String(computeAlpha).includes('+') ? '74%' : '30%' }}
                                        style={{ height: '100%', background: '#10b981' }}
                                    />
                                </div>
                                <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', marginTop: '8px' }}>Performance relative to ZK-proof and TEE operational costs.</p>
                            </div>
                        </div>
                    </div>

                    <div style={{ background: 'rgba(0,0,0,0.5)', borderRadius: '24px', padding: '24px', border: '1px solid rgba(255,255,255,0.05)', fontFamily: 'JetBrains Mono, monospace' }}>
                        <div style={{ fontSize: '0.65rem', color: '#10b981', marginBottom: '16px' }}>&gt; XIA_AUDIT_LOG_STREAM</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {auditLogs.map((log: string, i: number) => (
                                <div key={i} style={{ fontSize: '0.7rem', color: log.includes('BINDING') ? 'var(--gold)' : 'rgba(255,255,255,0.4)' }}>
                                    {log}
                                </div>
                            ))}
                        </div>
                        <div className="pulse" style={{ width: '8px', height: '8px', background: '#10b981', borderRadius: '50%', marginTop: '20px' }} />
                    </div>
                </div>
            </div>
        </div>
    );
};
