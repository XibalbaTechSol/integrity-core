// @ts-nocheck
import React from 'react';
import { Cpu, Wallet, Shield, BarChart3, ChevronRight, Activity, Zap, Target, Star } from 'lucide-react';
import { motion } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';

interface HeroAgentSelectorProps {
    selectedAgent: any;
    activeTab: string;
    setActiveTab: (tab: string) => void;
}

export const HeroAgentSelector: React.FC<HeroAgentSelectorProps> = ({ selectedAgent, activeTab, setActiveTab }) => {
    const isMobile = useIsMobile();
    if (!selectedAgent) return null;

    const views = [
        { id: 'registry', label: 'Registry', icon: <Cpu size={14} />, color: 'var(--gold)' },
        { id: 'wallet', label: 'Wallet', icon: <Wallet size={14} />, color: '#60a5fa' },
        { id: 'analytics', label: 'Logic Suite', icon: <BarChart3 size={14} />, color: '#10b981' },
        { id: 'governance', label: 'Guardian', icon: <Shield size={14} />, color: '#a78bfa' },
    ];

    const eScore = Math.min(1, (selectedAgent.entropy_score || 500) / 1000);
    const gScore = Math.min(1, (selectedAgent.grounding_score || 500) / 1000);
    const sScore = Math.min(1, (selectedAgent.staked_ratio || 0.8));

    // Mobile: Compact agent status card
    if (isMobile) {
        return (
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                style={{
                    padding: '14px 16px',
                    marginBottom: '16px',
                    background: 'linear-gradient(135deg, rgba(212, 175, 55, 0.06) 0%, rgba(10, 11, 13, 0.4) 100%)',
                    border: '1px solid rgba(212, 175, 55, 0.12)',
                    borderRadius: '14px',
                }}
            >
                {/* Agent identity row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                    <div style={{
                        width: '40px', height: '40px', borderRadius: '10px',
                        background: 'var(--gold)', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: 'var(--obsidian)', flexShrink: 0,
                        boxShadow: '0 0 12px rgba(212, 175, 55, 0.2)',
                    }}>
                        <Cpu size={20} />
                    </div>
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <h1 style={{ fontSize: '0.95rem', fontWeight: 900, color: 'white', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {selectedAgent.alias}
                            </h1>
                            <div className="badge badge-gold" style={{ fontSize: '0.45rem', padding: '2px 5px', flexShrink: 0 }}>
                                T{selectedAgent.verification_tier}
                            </div>
                        </div>
                        <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>
                            {selectedAgent.eth_address.slice(0, 6)}...{selectedAgent.eth_address.slice(-4)}
                        </div>
                    </div>
                    {/* AIS Score */}
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div style={{ fontSize: '1.3rem', fontWeight: 900, color: 'var(--gold)', lineHeight: 1, fontFamily: 'Playfair Display, serif' }}>
                            {selectedAgent.current_ais}
                        </div>
                        <div style={{ fontSize: '0.45rem', color: 'rgba(255,255,255,0.3)', fontWeight: 800, letterSpacing: '0.1em' }}>AIS</div>
                    </div>
                </div>

                {/* Mini tri-metric bars */}
                <div style={{ display: 'flex', gap: '8px' }}>
                    {[
                        { label: 'ENT', value: eScore, color: '#60a5fa' },
                        { label: 'GND', value: gScore, color: '#10b981' },
                        { label: 'SAC', value: sScore, color: '#f43f5e' },
                    ].map((m, i) => (
                        <div key={i} style={{ flex: 1 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                <span style={{ fontSize: '0.45rem', fontWeight: 800, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.05em' }}>{m.label}</span>
                                <span style={{ fontSize: '0.45rem', fontWeight: 700, color: m.color }}>{Math.round(m.value * 100)}%</span>
                            </div>
                            <div style={{ width: '100%', height: '2px', background: 'rgba(255,255,255,0.06)', borderRadius: '1px', overflow: 'hidden' }}>
                                <div style={{ width: `${m.value * 100}%`, height: '100%', background: m.color, borderRadius: '1px', transition: 'width 0.8s ease' }} />
                            </div>
                        </div>
                    ))}
                </div>
            </motion.div>
        );
    }

    // Desktop: Full hero selector with view switcher
    return (
        <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="enterprise-card"
            style={{ 
                padding: '24px 32px', 
                marginBottom: '40px', 
                background: 'linear-gradient(90deg, rgba(212, 175, 55, 0.05) 0%, rgba(10, 11, 13, 0.4) 100%)',
                border: '1px solid rgba(212, 175, 55, 0.15)',
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '40px'
            }}
        >
            {/* Agent Identity Section */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                <div style={{ 
                    width: '56px', height: '56px', borderRadius: '12px', 
                    background: 'var(--gold)', display: 'flex', alignItems: 'center', 
                    justifyContent: 'center', color: 'var(--obsidian)',
                    boxShadow: '0 0 20px rgba(212, 175, 55, 0.2)',
                    flexShrink: 0
                }}>
                    <Cpu size={28} />
                </div>
                <div style={{ overflow: 'hidden', flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <h1 style={{ fontSize: '1.4rem', fontWeight: 900, color: 'white', margin: 0, letterSpacing: '-0.02em' }}>
                            {selectedAgent.alias}
                        </h1>
                        <div className="badge badge-gold" style={{ fontSize: '0.5rem', padding: '2px 6px' }}>
                            T{selectedAgent.verification_tier} ACTIVE
                        </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
                            {selectedAgent.eth_address}
                        </div>
                        <div style={{ display: 'flex', gap: '8px', borderLeft: '1px solid rgba(255,255,255,0.1)', paddingLeft: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Activity size={10} style={{ color: '#60a5fa' }} />
                                <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#60a5fa' }}>{selectedAgent.entropy_score}</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Zap size={10} style={{ color: '#10b981' }} />
                                <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#10b981' }}>{selectedAgent.grounding_score}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* View Switcher Section */}
            <div style={{ display: 'flex', background: 'rgba(0,0,0,0.3)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', gap: '4px' }}>
                {views.map((view) => (
                    <button
                        key={view.id}
                        onClick={() => setActiveTab(view.id)}
                        style={{
                            flex: 1,
                            padding: '10px 20px',
                            borderRadius: '10px',
                            border: 'none',
                            background: activeTab === view.id ? 'rgba(255,255,255,0.05)' : 'transparent',
                            color: activeTab === view.id ? 'white' : 'rgba(255,255,255,0.3)',
                            fontSize: '0.65rem',
                            fontWeight: 800,
                            cursor: 'pointer',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '4px',
                            transition: 'all 0.2s',
                            whiteSpace: 'nowrap',
                        }}
                    >
                        <div style={{ color: activeTab === view.id ? view.color : 'inherit' }}>{view.icon}</div>
                        {view.label}
                    </button>
                ))}
            </div>

            {/* Quick Action */}
            <button 
                className="btn btn-primary"
                onClick={() => setActiveTab('registry')}
                style={{ 
                    padding: '12px 24px', borderRadius: '12px', fontSize: '0.75rem', 
                    fontWeight: 800, display: 'flex', alignItems: 'center', gap: '10px' 
                }}
            >
                VIEW REGISTRY <ChevronRight size={14} />
            </button>
        </motion.div>
    );
};
