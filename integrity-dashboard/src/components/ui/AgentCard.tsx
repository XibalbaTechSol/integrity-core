// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Award, Activity, Download, Copy, FileText, AlertTriangle, Fingerprint } from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';
import axios from 'axios';
import { API_BASE } from '../../constants';

interface AgentCardProps {
    agent: any;
    isSelected: boolean;
    onSelect: () => void;
    onEdit?: () => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, isSelected, onSelect, onEdit }) => {
    const isMobile = useIsMobile();
    
    if (!agent) return (
        <div className="enterprise-card flex-center" style={{ width: '100%', height: '100%', background: 'var(--glass-surface)' }}>
            <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.2em' }}>No Agent Data</span>
        </div>
    );

    const handleDownloadIdentity = (e: React.MouseEvent) => {
        e.stopPropagation();
        const identity = {
            agent_address: agent.eth_address,
            alias: agent.alias,
            xns_handle: agent.xns_handle || `${agent.alias.toLowerCase().replace(/ /g, '_')}.intg`,
            oracle_url: "https://api.integrity-protocol.v8.web.app",
            network: "base-sepolia",
            chain_id: 84532,
            verification_tier: agent.verification_tier,
            current_ais: agent.current_ais
        };
        const blob = new Blob([JSON.stringify(identity, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `identity_${agent.alias.toLowerCase().replace(/ /g, '_')}.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const handleCopyDid = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigator.clipboard.writeText(`did:intg:${agent.eth_address}`);
    };

    const eScore = Math.min(1, (agent.entropy_score || 500) / 1000);
    const gScore = Math.min(1, (agent.grounding_score || 500) / 1000);
    const sScore = Math.min(1, (agent.sacrifice_score || agent.staked_ratio * 1000 || 700) / 1000);

    const R = 38;
    const cx = 50;
    const cy = 50;
    
    const p1x = cx;
    const p1y = cy - (R * eScore);
    const p2x = cx + (R * gScore * Math.cos(Math.PI / 6));
    const p2y = cy + (R * gScore * Math.sin(Math.PI / 6));
    const p3x = cx - (R * sScore * Math.cos(Math.PI / 6));
    const p3y = cy + (R * sScore * Math.sin(Math.PI / 6));

    const isPrime = agent.current_ais >= 800;
    const isCritical = agent.current_ais < 400;

    return (
        <motion.div 
            whileHover={{ y: -4 }}
            className={`enterprise-card ${isSelected ? 'selected' : ''}`} 
            style={{ 
                cursor: 'pointer',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                background: isSelected ? 'var(--gold-muted)' : 'var(--glass-surface)',
                border: isSelected ? '1px solid var(--gold)' : '1px solid var(--border)',
                position: 'relative',
                overflow: 'hidden',
                borderRadius: 'var(--r-md)'
            }}
            onClick={onSelect}
        >
            {/* Dossier ID Strip */}
            <div style={{ position: 'absolute', top: 0, right: 0, width: '4px', height: '100%', background: isPrime ? 'var(--gold)' : isCritical ? '#f43f5e' : 'var(--border)' }} />

            <div style={{ padding: 'var(--space-6) var(--space-6) var(--space-4)', background: 'transparent' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-1)' }}>
                            <Fingerprint size={12} style={{ color: 'var(--gold)', opacity: 0.6 }} />
                            <span style={{ fontSize: '0.6rem', fontWeight: 800, color: 'var(--gold)', letterSpacing: '0.2em', textTransform: 'uppercase' }}>
                                Agent Dossier
                            </span>
                        </div>
                        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'white', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'Playfair Display, serif' }}>
                            {agent.alias}
                        </h3>
                        <p className="mono" style={{ fontSize: '0.55rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                            {agent.eth_address.substring(0, 16)}...
                        </p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                        <div className={`badge ${isPrime ? 'badge-gold' : 'badge-slate'}`} style={{ borderRadius: 'var(--r-xs)', fontSize: '0.55rem', fontWeight: 900 }}>
                            TIER {agent.verification_tier || 1}
                        </div>
                    </div>
                </div>
            </div>
            
            <div style={{ padding: '0 var(--space-6) var(--space-6)', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                {/* AIS Core Metric */}
                <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)', position: 'relative' }}>
                    <div style={{ fontSize: '3rem', fontWeight: 700, color: isPrime ? 'var(--gold)' : 'white', fontFamily: 'Playfair Display, serif', lineHeight: 1 }}>
                        {agent.current_ais}
                    </div>
                    <div style={{ fontSize: '0.6rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.3em', marginTop: 'var(--space-2)' }}>
                        Integrity Score
                    </div>
                    {isCritical && (
                        <div style={{ position: 'absolute', top: '-10px', right: '-20px', color: '#f43f5e' }} className="animate-pulse">
                            <AlertTriangle size={16} />
                        </div>
                    )}
                </div>

                {/* Radar visualization */}
                <div style={{ width: '100%', height: '140px', position: 'relative' }}>
                    <svg viewBox="0 0 100 100" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
                        <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                        <circle cx="50" cy="50" r="20" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                        
                        {/* Axes */}
                        <line x1="50" y1="50" x2="50" y2="10" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="2 2" />
                        <line x1="50" y1="50" x2="84.6" y2="70" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="2 2" />
                        <line x1="50" y1="50" x2="15.4" y2="70" stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="2 2" />

                        <motion.polygon 
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            points={`${p1x},${p1y} ${p2x},${p2y} ${p3x},${p3y}`}
                            fill={isPrime ? 'rgba(201, 168, 76, 0.2)' : 'rgba(255, 255, 255, 0.05)'}
                            stroke={isPrime ? 'var(--gold)' : 'white'}
                            strokeWidth="1.5"
                            strokeLinejoin="round"
                        />

                        <g style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '3.5px', fontWeight: 800, letterSpacing: '0.5px' }} fill="var(--text-muted)">
                            <text x="50" y="5" textAnchor="middle">ENTROPY</text>
                            <text x="92" y="75" textAnchor="middle">GROUND</text>
                            <text x="8" y="75" textAnchor="middle">SACRIFICE</text>
                        </g>
                    </svg>
                </div>

                {/* Micro-metrics */}
                <div style={{ width: '100%', marginTop: 'var(--space-6)', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-2)' }}>
                    {[
                        { val: eScore, label: 'E' },
                        { val: gScore, label: 'G' },
                        { val: sScore, label: 'S' }
                    ].map((m, idx) => (
                        <div key={idx} style={{ textAlign: 'center' }}>
                            <div className="mono" style={{ fontSize: '0.65rem', fontWeight: 700, color: 'white', marginBottom: '4px' }}>
                                {Math.round(m.val * 100)}%
                            </div>
                            <div style={{ height: '2px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '1px', overflow: 'hidden' }}>
                                <div style={{ height: '100%', width: `${m.val * 100}%`, background: isPrime ? 'var(--gold)' : 'white', opacity: 0.6 }} />
                            </div>
                            <div style={{ fontSize: '0.5rem', fontWeight: 900, color: 'var(--text-muted)', marginTop: '4px' }}>{m.label}</div>
                        </div>
                    ))}
                </div>
            </div>
            
            {/* Footer with Actions */}
            <div style={{ borderTop: '1px solid var(--border)', background: 'rgba(0,0,0,0.1)', padding: 'var(--space-3) var(--space-6)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <div style={{ fontSize: '0.6rem', fontWeight: 800, color: isPrime ? 'var(--gold)' : 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Activity size={10} /> {agent.tx_count_24h || 0} REQ/S
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <button 
                        onClick={(e) => { e.stopPropagation(); onEdit?.(); }}
                        style={{ background: 'none', border: 'none', color: 'var(--gold)', fontSize: '0.6rem', fontWeight: 800, cursor: 'pointer', padding: '4px 0' }}
                    >
                        EDIT
                    </button>
                    <button 
                        onClick={handleDownloadIdentity}
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}
                        title="Download Identity"
                    >
                        <Download size={14} />
                    </button>
                    <button 
                        onClick={handleCopyDid}
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}
                        title="Copy DID"
                    >
                        <Copy size={14} />
                    </button>
                </div>
            </div>
        </motion.div>
    );
};
