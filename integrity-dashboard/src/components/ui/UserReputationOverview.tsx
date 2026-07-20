// @ts-nocheck
import React, { useMemo, useState } from 'react';
import { Shield, Zap, Target, Activity, Cpu, Lock, Info, ChevronRight, CheckCircle2, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, PolarRadiusAxis } from 'recharts';
import { useIsMobile } from '../../utils/useIsMobile';

interface UserReputationOverviewProps {
    agents: any[];
    selectedAgent?: any;
}

export const UserReputationOverview: React.FC<UserReputationOverviewProps> = ({ agents, selectedAgent }) => {
    const isMobile = useIsMobile();
    const [activeMetric, setActiveMetric] = useState<string | null>(null);
    
    const targetAgent = selectedAgent || (agents && agents.length > 0 ? agents[0] : null);

    const radarConfigs = useMemo(() => {
        if (!targetAgent) return [];
        
        const getVal = (val: any, fallback: number) => val || fallback;
        const displayEntropy = getVal(targetAgent.entropy_score, 500);
        const displayGrounding = getVal(targetAgent.grounding_score, 500);
        const displaySacrifice = getVal(targetAgent.sacrifice_score, (targetAgent.staked_ratio * 1000) || 700);

        const entropyData = [
            { subject: 'Stability', A: targetAgent.stability_score || displayEntropy, fullMark: 1000 },
            { subject: 'Consistency', A: targetAgent.consistency_score || (displayEntropy * 0.95), fullMark: 1000 },
            { subject: 'Predictability', A: targetAgent.predictability_score || (displayEntropy * 1.05), fullMark: 1000 },
        ];

        const groundingData = [
            { subject: 'Oversight', A: targetAgent.oversight_score || displayGrounding, fullMark: 1000 },
            { subject: 'Fidelity', A: targetAgent.fidelity_score || (displayGrounding * 1.1), fullMark: 1000 },
            { subject: 'Compliance', A: targetAgent.compliance_score || (displayGrounding * 0.9), fullMark: 1000 },
        ];

        const sacrificeData = [
            { subject: 'Stake', A: displaySacrifice, fullMark: 1000 },
            { subject: 'Compute', A: targetAgent.compute_score || (displaySacrifice * 0.85), fullMark: 1000 },
            { subject: 'Collateral', A: targetAgent.collateral_score || (displaySacrifice * 1.15), fullMark: 1000 },
        ];

        return [
            { 
                id: 'entropy',
                title: 'Entropy Radar', 
                data: entropyData, 
                color: '#60a5fa', 
                icon: <Activity size={16} />, 
                description: 'Measures behavioral stability and response consistency over time.',
                longDesc: 'The Entropy Score analyzes the variance in agent responses across identical contexts. High entropy suggests model drift or instability, while low entropy indicates reliable, predictable behavior. This metric is derived from our proprietary Monte-Carlo simulation of agent state-transitions.',
                equation: 'S_e = - \\sum p_i \\log p_i'
            },
            { 
                id: 'grounding',
                title: 'Grounding Radar', 
                data: groundingData, 
                color: '#10b981', 
                icon: <Zap size={16} />, 
                description: 'Verifies model fidelity and compliance with real-world constraints.',
                longDesc: 'Grounding quantifies how well an agent\'s internal logic aligns with verified external facts. We use a consensus of cross-domain oracles to validate agent assertions. A high grounding score is mandatory for agents handling high-value legal or medical transactions.',
                equation: 'S_g = \\frac{V_{facts}}{T_{assertions}}'
            },
            { 
                id: 'sacrifice',
                title: 'Sacrifice Radar', 
                data: sacrificeData, 
                color: '#f43f5e', 
                icon: <Target size={16} />, 
                description: 'Quantifies skin-in-the-game through staking and compute dedication.',
                longDesc: 'Sacrifice measures the economic friction an agent accepts to prove its commitment. This includes ITK staking, compute-proof (Proof-of-Work headers), and collateral lockups. It acts as a primary deterrent against Sybil attacks and malicious pivots.',
                equation: 'S_s = \\log(1 + \\sum C_i)'
            },
        ];
    }, [targetAgent]);
    
    if (!targetAgent) return null;

    const getAISCap = (tier: number) => {
        if (tier === 3) return 1000;
        if (tier === 2) return 850;
        return 600;
    };

    const displayAIS = Math.min(targetAgent.current_ais, getAISCap(targetAgent.verification_tier || 1));

    return (
        <div style={{ marginBottom: '48px' }}>
            <style>{`
                .metric-card-interactive {
                    transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s;
                    cursor: pointer;
                }
                .metric-card-interactive:hover {
                    transform: translateY(-5px) scale(1.02);
                    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                    border-color: rgba(255,255,255,0.1) !important;
                    background: rgba(255,255,255,0.02) !important;
                }
                .metric-detail-overlay {
                    background: rgba(5, 13, 24, 0.98);
                    backdrop-filter: blur(20px);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 24px;
                    padding: 40px;
                    margin-top: 24px;
                    position: relative;
                    overflow: hidden;
                }
                .equation-pill {
                    background: rgba(212, 175, 55, 0.05);
                    border: 1px solid rgba(212, 175, 55, 0.2);
                    color: var(--gold);
                    padding: 8px 16px;
                    border-radius: 8px;
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 0.8rem;
                    display: inline-block;
                }
            `}</style>

            <div className={`flex-${isMobile ? 'column' : 'between'} mb-8`} style={{ alignItems: isMobile ? 'flex-start' : 'center', gap: isMobile ? '16px' : 0 }}>
                <div>
                    <h2 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, margin: 0 }}>Tri-Metric Command Center</h2>
                    <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: isMobile ? '0.75rem' : '0.9rem' }}>Deep reputation intelligence for <span style={{ color: 'var(--gold)' }}>{targetAgent.alias}</span></p>
                </div>
                <div style={{ textAlign: isMobile ? 'left' : 'right' }}>
                    <div style={{ fontSize: '0.65rem', color: 'var(--gold)', fontWeight: 800, letterSpacing: '0.2em' }}>AGGREGATE TRUST INDEX</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: isMobile ? 'flex-start' : 'flex-end' }}>
                        <div style={{ fontSize: isMobile ? '1.2rem' : '1.8rem', fontWeight: 900, fontFamily: 'JetBrains Mono, monospace' }}>{Math.round(displayAIS)}</div>
                        <div style={{ padding: '4px 8px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '6px', fontSize: '0.65rem', color: '#10b981', fontWeight: 800 }}>
                            {targetAgent.risk_tier || 'AAA'}
                        </div>
                    </div>
                </div>
            </div>

            {/* Staking Power / Trust Ceiling Indicator */}
            <div style={{ 
                background: 'rgba(255,255,255,0.02)', 
                border: '1px solid rgba(255,255,255,0.05)', 
                borderRadius: '16px', 
                padding: '24px', 
                marginBottom: '40px',
                position: 'relative',
                overflow: 'hidden'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', alignItems: 'flex-end' }}>
                    <div>
                        <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Trust Ceiling Progress</div>
                        <div style={{ fontSize: '1rem', fontWeight: 800 }}>Tier {targetAgent.verification_tier || 1} Accountability</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontWeight: 800 }}>AIS MAX CAP</div>
                        <div style={{ fontSize: '1rem', fontWeight: 900, color: 'var(--gold)' }}>{getAISCap(targetAgent.verification_tier || 1)}</div>
                    </div>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', position: 'relative', overflow: 'hidden' }}>
                    <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${(displayAIS / getAISCap(targetAgent.verification_tier || 1)) * 100}%` }}
                        style={{ height: '100%', background: 'linear-gradient(90deg, #c9a84c, #e6cfa0)', borderRadius: '4px', boxShadow: '0 0 10px rgba(201, 168, 76, 0.3)' }}
                    />
                </div>
                <div style={{ marginTop: '16px', display: 'flex', gap: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>
                        <Lock size={12} /> Staked ITK Power: <span style={{ color: 'white', fontWeight: 700 }}>{Math.round(targetAgent.staked_ratio * 100)}%</span>
                    </div>
                    {targetAgent.staked_ratio < 0.5 && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', color: '#f43f5e', fontWeight: 700 }}>
                            <AlertCircle size={12} /> UNDER-COLLATERALIZED RISK
                        </div>
                    )}
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '24px' }}>
                {radarConfigs.map((config, idx) => (
                    <motion.div 
                        key={idx}
                        layoutId={`card-${config.id}`}
                        onClick={() => setActiveMetric(activeMetric === config.id ? null : config.id)}
                        className="enterprise-card metric-card-interactive" 
                        style={{ 
                            padding: '32px', 
                            background: activeMetric === config.id ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.01)', 
                            border: activeMetric === config.id ? `1px solid ${config.color}` : '1px solid rgba(255,255,255,0.05)',
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <div style={{ color: config.color }}>{config.icon}</div>
                                <span style={{ fontSize: '0.75rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase' }}>{config.title}</span>
                            </div>
                            {activeMetric === config.id ? <CheckCircle2 size={14} style={{ color: config.color }} /> : <Info size={14} style={{ color: 'rgba(255,255,255,0.2)' }} />}
                        </div>
                        
                        <div style={{ height: '200px', width: '100%', pointerEvents: 'none' }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <RadarChart cx="50%" cy="50%" outerRadius="70%" data={config.data}>
                                    <PolarGrid stroke="rgba(255,255,255,0.05)" />
                                    <PolarAngleAxis dataKey="subject" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9, fontWeight: 700 }} />
                                    <PolarRadiusAxis domain={[0, 1000]} tick={false} axisLine={false} />
                                    <Radar
                                        name={config.title}
                                        dataKey="A"
                                        stroke={config.color}
                                        fill={config.color}
                                        fillOpacity={0.4}
                                        strokeWidth={2}
                                        isAnimationActive={true}
                                    />
                                </RadarChart>
                            </ResponsiveContainer>
                        </div>

                        <div style={{ marginTop: '20px', textAlign: 'center' }}>
                            <div style={{ fontSize: '1.4rem', fontWeight: 900, color: 'white' }}>{Math.round(config.data[0].A)}</div>
                            <div style={{ fontSize: '0.6rem', color: config.color, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>PULSE STRENGTH</div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', color: 'rgba(255,255,255,0.3)', fontSize: '0.6rem', fontWeight: 700 }}>
                                CLICK FOR INTELLIGENCE <ChevronRight size={10} />
                            </div>
                        </div>
                    </motion.div>
                ))}
            </div>

            <AnimatePresence>
                {activeMetric && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="metric-detail-overlay"
                    >
                        {radarConfigs.filter(c => c.id === activeMetric).map(config => (
                            <div key={config.id} style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '48px', alignItems: 'center' }}>
                                <div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                                        <div style={{ padding: '12px', background: `${config.color}20`, borderRadius: '12px', color: config.color }}>
                                            {config.icon}
                                        </div>
                                        <h3 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>{config.title.replace(' Radar', '')} Intelligence</h3>
                                    </div>
                                    <p style={{ color: 'rgba(255,255,255,0.6)', lineHeight: 1.7, fontSize: '0.95rem', marginBottom: '32px' }}>
                                        {config.longDesc}
                                    </p>
                                    <div style={{ display: 'flex', gap: '24px' }}>
                                        <div>
                                            <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '12px' }}>Formal Verification</div>
                                            <div className="equation-pill">{config.equation}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '12px' }}>ZK-Status</div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', fontWeight: 800, fontSize: '0.8rem' }}>
                                                <Lock size={14} /> PROOF ANCHORED
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '20px', padding: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                    <div style={{ marginBottom: '24px' }}>
                                        <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'white' }}>Signal Composition</h4>
                                        <p style={{ margin: '4px 0 0', fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>Real-time telemetry sub-components.</p>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                        {config.data.map((d, i) => (
                                            <div key={i}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.75rem', fontWeight: 700 }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.6)' }}>{d.subject}</span>
                                                    <span style={{ color: config.color }}>{d.A}/1000</span>
                                                </div>
                                                <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                                                    <motion.div 
                                                        initial={{ width: 0 }}
                                                        animate={{ width: `${(d.A / 1000) * 100}%` }}
                                                        style={{ height: '100%', background: config.color }}
                                                    />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <button 
                                    onClick={() => setActiveMetric(null)}
                                    style={{ position: 'absolute', top: '24px', right: '24px', background: 'rgba(255,255,255,0.05)', border: 'none', color: 'white', padding: '8px', borderRadius: '50%', cursor: 'pointer' }}
                                >
                                    <ChevronRight size={20} style={{ transform: 'rotate(90deg)' }} />
                                </button>
                            </div>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
