// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Brain, Cpu, MessageSquare, CheckCircle, AlertTriangle, Play, Settings, Info, ArrowRight, Save, Lock } from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';
import axios from 'axios';
import { API_BASE } from '../../constants';

interface Proposal {
    proposal_id: string;
    title: string;
    category: string;
    description: string;
    parameter: string;
    old_value: string;
    new_value: string;
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
}

export const GuardianPilot = () => {
    const isMobile = useIsMobile();
    const [config, setConfig] = useState({
        mode: 'Conservative',
        aggression: 20,
        riskTolerance: 'Low',
        focus: 'Stability'
    });

    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisResult, setAnalysisResult] = useState<any>(null);
    const [proposals, setProposals] = useState<Proposal[]>([]);
    const [activeProposal, setActiveProposal] = useState<Proposal | null>(null);

    useEffect(() => {
        const fetchProposals = async () => {
            try {
                const res = await axios.get(`${API_BASE}/v1/governance/proposals`);
                setProposals(res.data);
                if (res.data.length > 0) setActiveProposal(res.data[0]);
            } catch (e) {
                console.error("Fetch proposals failed", e);
            }
        };
        fetchProposals();
    }, []);

    const runAnalysis = async () => {
        if (!activeProposal) return;
        setIsAnalyzing(true);
        setAnalysisResult(null);
        
        try {
            const res = await axios.post(`${API_BASE}/v1/governance/analyze`, {
                proposal_id: activeProposal.proposal_id,
                mode: config.mode,
                aggression: config.aggression,
                risk_tolerance: config.riskTolerance
            });
            setAnalysisResult(res.data);
        } catch (e) {
            console.error("Analysis failed", e);
        } finally {
            setIsAnalyzing(false);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? '20px' : '32px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.2fr 1fr', gap: isMobile ? '20px' : '32px' }}>
                {/* Configuration Panel */}
                <div className="enterprise-card" style={{ padding: isMobile ? '24px' : '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
                        <div style={{ padding: '12px', background: 'rgba(212, 175, 55, 0.1)', borderRadius: '16px', color: 'var(--gold)' }}>
                            <Settings size={24} />
                        </div>
                        <div>
                            <h3 style={{ fontSize: isMobile ? '1.2rem' : '1.4rem', fontWeight: 800, margin: 0, color: 'white' }}>Configure Guardian</h3>
                            <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', margin: '4px 0 0' }}>Define the constitutional mandate for your AI proxy.</p>
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                        <div>
                            <label style={{ fontSize: '0.7rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', display: 'block', marginBottom: '12px' }}>
                                PROXY OPERATING MODE
                            </label>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                {['Conservative', 'Aggressive'].map(mode => (
                                    <button 
                                        key={mode}
                                        onClick={() => setConfig({ ...config, mode })}
                                        style={{ 
                                            padding: isMobile ? '12px' : '16px', borderRadius: '12px', 
                                            background: config.mode === mode ? 'rgba(212, 175, 55, 0.15)' : 'rgba(255,255,255,0.03)',
                                            border: config.mode === mode ? '1px solid var(--gold)' : '1px solid rgba(255,255,255,0.05)',
                                            color: config.mode === mode ? 'var(--gold)' : 'rgba(255,255,255,0.6)',
                                            fontSize: '0.85rem', fontWeight: 800, cursor: 'pointer', transition: 'all 0.2s'
                                        }}
                                    >
                                        {mode}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div>
                            <label style={{ fontSize: '0.7rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', display: 'block', marginBottom: '12px' }}>
                                RISK TOLERANCE: <span style={{ color: 'white' }}>{config.riskTolerance}</span>
                            </label>
                            <input 
                                type="range" min="0" max="100" 
                                value={config.aggression} 
                                onChange={(e) => setConfig({ ...config, aggression: parseInt(e.target.value), riskTolerance: parseInt(e.target.value) > 50 ? 'High' : 'Low' })}
                                style={{ width: '100%', accentColor: 'var(--gold)' }}
                            />
                        </div>

                        <button 
                            className="btn btn-primary"
                            style={{ padding: '16px', marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}
                        >
                            <Save size={18} /> SAVE MANDATE
                        </button>
                    </div>
                </div>

                {/* Proposal Selector */}
                <div className="enterprise-card" style={{ padding: isMobile ? '24px' : '32px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
                        <div style={{ padding: '12px', background: 'rgba(96, 165, 250, 0.1)', borderRadius: '16px', color: '#60a5fa' }}>
                            <MessageSquare size={24} />
                        </div>
                        <div>
                            <h3 style={{ fontSize: isMobile ? '1.2rem' : '1.4rem', fontWeight: 800, margin: 0, color: 'white' }}>Active Proposals</h3>
                            <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', margin: '4px 0 0' }}>Pilot Phase: {proposals.length} motions pending.</p>
                        </div>
                    </div>

                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {proposals.map(prop => (
                            <div 
                                key={prop.proposal_id}
                                onClick={() => setActiveProposal(prop)}
                                style={{ 
                                    padding: '24px', borderRadius: '16px', 
                                    background: activeProposal?.proposal_id === prop.proposal_id ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.02)',
                                    border: activeProposal?.proposal_id === prop.proposal_id ? '1px solid rgba(255,255,255,0.1)' : '1px solid transparent',
                                    cursor: 'pointer', transition: 'all 0.2s'
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                    <span style={{ fontSize: '0.65rem', fontWeight: 900, color: 'rgba(255,255,255,0.4)' }}>{prop.proposal_id.slice(0, 8).toUpperCase()}</span>
                                    <div className={`badge ${prop.risk_level === 'HIGH' ? 'badge-slate' : 'badge-gold'}`} style={{ fontSize: '0.55rem', color: prop.risk_level === 'HIGH' ? '#f43f5e' : '' }}>
                                        {prop.risk_level} RISK
                                    </div>
                                </div>
                                <h4 style={{ fontSize: '1rem', fontWeight: 800, margin: 0, color: 'white' }}>{prop.title}</h4>
                            </div>
                        ))}
                    </div>

                    <button 
                        onClick={runAnalysis}
                        disabled={isAnalyzing || !activeProposal}
                        className="btn btn-primary"
                        style={{ padding: '20px', marginTop: '24px', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}
                    >
                        {isAnalyzing ? (
                            <>
                                <Cpu className="animate-spin" size={20} />
                                ANALYZING...
                            </>
                        ) : (
                            <>
                                <Play size={20} />
                                RUN ANALYSIS
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Analysis Results Display */}
            <AnimatePresence mode="wait">
                {analysisResult && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="enterprise-card"
                        style={{ padding: isMobile ? '24px' : '40px', border: '1px solid rgba(212, 175, 55, 0.2)', background: 'rgba(5, 13, 24, 0.6)', position: 'relative', overflow: 'hidden' }}
                    >
                        <div style={{ position: 'absolute', top: 0, right: 0, padding: '24px', opacity: 0.1 }}>
                            <Brain size={isMobile ? 80 : 120} style={{ color: 'var(--gold)' }} />
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 300px', gap: isMobile ? '32px' : '60px' }}>
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                                    {analysisResult.decision === 'SUPPORT' ? (
                                        <div style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', fontWeight: 900 }}>
                                            <CheckCircle size={20} /> DECISION: SUPPORTED
                                        </div>
                                    ) : (
                                        <div style={{ color: '#f43f5e', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', fontWeight: 900 }}>
                                            <AlertTriangle size={20} /> DECISION: REJECTED
                                        </div>
                                    )}
                                    <div style={{ width: '1px', height: '14px', background: 'rgba(255,255,255,0.1)' }} />
                                    <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>{analysisResult.confidence}% Confidence</span>
                                </div>

                                <h4 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: '16px', color: 'white' }}>Technical Rationale</h4>
                                <p style={{ fontSize: isMobile ? '0.9rem' : '1.05rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6, margin: 0 }}>
                                    {analysisResult.reasoning}
                                </p>

                                <div style={{ marginTop: '32px', display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
                                    <div className="badge badge-gold" style={{ fontSize: '0.6rem' }}>SHADOW VOTE RECORDED</div>
                                    <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                                        <Lock size={12} /> ANCHORED TO PILOT LEDGER
                                    </div>
                                </div>
                            </div>

                            <div style={{ borderLeft: isMobile ? 'none' : '1px solid rgba(255,255,255,0.05)', borderTop: isMobile ? '1px solid rgba(255,255,255,0.05)' : 'none', paddingTop: isMobile ? '32px' : '0', paddingLeft: isMobile ? '0' : '40px' }}>
                                <h4 style={{ fontSize: '0.7rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '24px' }}>
                                    PROJECTED ECO-IMPACT
                                </h4>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                    {analysisResult.metrics_impact && Object.entries(analysisResult.metrics_impact).map(([key, val]: [string, any]) => (
                                        <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', textTransform: 'capitalize' }}>{key} Index</span>
                                            <span style={{ fontSize: '1rem', fontWeight: 800, color: val > 0 ? '#10b981' : (val < 0 ? '#f43f5e' : 'white') }}>
                                                {val > 0 ? '+' : ''}{val}%
                                            </span>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ marginTop: '32px', padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                    <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.4 }}>
                                        <Info size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                                        Impact is calculated using the Aura Neural Core simulator (v8.0).
                                    </div>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Educational Banner */}
            <div style={{ padding: isMobile ? '24px' : '32px', background: 'rgba(212, 175, 55, 0.05)', border: '1px solid rgba(212, 175, 55, 0.15)', borderRadius: '24px', display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: '24px' }}>
                <Shield size={32} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                    <h4 style={{ fontSize: '1.1rem', margin: 0, color: 'white' }}>The Guardian Pilot Roadmap</h4>
                    <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', margin: '4px 0 0', lineHeight: 1.6 }}>
                        We are currently in <strong>Stage 1 (Shadow Governance)</strong>. Your Guardian's votes are non-binding but are used to train the protocol's stability model.
                    </p>
                </div>
                <button className="btn btn-outline" style={{ whiteSpace: 'nowrap', width: isMobile ? '100%' : 'auto' }}>Learn More <ArrowRight size={14} /></button>
            </div>
        </div>
    );
};
