// @ts-nocheck
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity, Radio, ChevronDown, ChevronUp, Shield, Lock, FileCode, CheckCircle, AlertTriangle, Cpu, Terminal } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';

// Xibalba Solutions: Live Telemetry Stream Visualizer (v2.0)
// Real-time scrolling feed with interactive deep-dive capabilities for agent researchers.

export const TelemetryStream = () => {
    const isMobile = useIsMobile();
    const { agents } = useDashboard();
    const [stream, setStream] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    // Interactive filters
    const [selectedAgentFilter, setSelectedAgentFilter] = useState('All');
    const [selectedTypeFilter, setSelectedTypeFilter] = useState('All');
    const [showAlertsOnly, setShowAlertsOnly] = useState(false);

    // Real network-wide telemetry feed: the oracle exposes telemetry per-agent
    // (there is no global /telemetry/latest endpoint), so aggregate the real
    // TelemetryEventDetailDto stream across the live agent set, newest-first.
    // `flagged` is the real alert signal; performance_variance maps to the row's
    // discrepancy_ratio so the existing "alerts only" filter stays meaningful.
    useEffect(() => {
        let cancelled = false;
        const fetchTelemetry = async () => {
            try {
                const perAgent = await Promise.all(
                    agents.map((a) =>
                        oracle
                            .getTelemetry(a.eth_address)
                            .then((events) =>
                                events.map((e) => ({
                                    id: e.id,
                                    agent: a.alias,
                                    agent_id: e.agent_id,
                                    type: e.flagged ? 'FLAGGED' : 'RECORDED',
                                    flagged: e.flagged,
                                    created_at: e.created_at,
                                    metadata: {
                                        discrepancy_ratio: e.performance_variance,
                                        hgi_raw: e.hgi_raw,
                                        gpu_hours_verified: e.gpu_hours_verified,
                                        zk_verified: e.zk_verified,
                                        nonce: e.nonce,
                                        leaf_hash: e.leaf_hash,
                                    },
                                })),
                            )
                            .catch(() => []),
                    ),
                );
                const merged = perAgent
                    .flat()
                    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
                    .slice(0, 50);
                if (!cancelled) setStream(merged);
            } catch (e) {
                console.error('Telemetry fetch error:', e);
                if (!cancelled) setStream([]);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        fetchTelemetry();
        const interval = setInterval(fetchTelemetry, 5000);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [agents]);

    // Get unique list of agent names from the telemetry stream
    const uniqueAgents = ['All', ...new Set(stream.map(item => item.agent).filter(Boolean))];

    // Filter telemetry records based on user choices
    const filteredStream = stream.filter(item => {
        if (selectedAgentFilter !== 'All' && item.agent !== selectedAgentFilter) return false;
        if (selectedTypeFilter !== 'All' && item.type !== selectedTypeFilter) return false;
        if (showAlertsOnly) {
            // Real alert signal: the oracle's `flagged` boolean, or a high performance-variance
            // (the real discrepancy_ratio). The oracle reports no latency/accuracy fields.
            const isWarning = item.flagged || (item.metadata?.discrepancy_ratio != null && item.metadata.discrepancy_ratio > 0.1);
            if (!isWarning) return false;
        }
        return true;
    });

    const handleRowClick = (id: string) => {
        setExpandedId(expandedId === id ? null : id);
    };

    return (
        <div className="enterprise-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.05)' }}>

            {/* Header */}
            <div className="card-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', padding: isMobile ? '16px' : '24px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(212, 175, 55, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--theme-accent)' }}>
                        <Activity size={20} />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <h2 style={{ fontSize: '0.75rem', fontWeight: 700, color: 'white', textTransform: 'uppercase', letterSpacing: '0.25em', fontFamily: 'Inter, sans-serif', margin: 0 }}>Live Telemetry</h2>
                        <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.3em', marginTop: '2px' }}>Ingestion In-Progress</span>
                    </div>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {!isMobile && (
                        <div className="badge badge-gold" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Radio size={12} className="animate-pulse" />
                            Syncing Live Feed
                        </div>
                    )}
                </div>
            </div>

            {/* Interactive Filters Bar */}
            <div style={{
                padding: '12px 24px',
                background: 'rgba(0, 0, 0, 0.2)',
                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                display: 'flex',
                gap: '16px',
                flexWrap: 'wrap',
                alignItems: 'center'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>Agent Filter:</span>
                    <select
                        value={selectedAgentFilter}
                        onChange={e => setSelectedAgentFilter(e.target.value)}
                        style={{ background: '#0e0e12', border: '1px solid rgba(255,255,255,0.1)', color: 'white', fontSize: '0.7rem', padding: '4px 8px', borderRadius: '4px', outline: 'none' }}
                    >
                        {uniqueAgents.map(name => (
                            <option key={name} value={name}>{name}</option>
                        ))}
                    </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', fontWeight: 700 }}>Type:</span>
                    <select
                        value={selectedTypeFilter}
                        onChange={e => setSelectedTypeFilter(e.target.value)}
                        style={{ background: '#0e0e12', border: '1px solid rgba(255,255,255,0.1)', color: 'white', fontSize: '0.7rem', padding: '4px 8px', borderRadius: '4px', outline: 'none' }}
                    >
                        <option value="All">All Types</option>
                        <option value="RECORDED">RECORDED</option>
                        <option value="FLAGGED">FLAGGED</option>
                    </select>
                </div>

                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.7rem', color: 'rgba(255,255,255,0.7)' }}>
                    <input
                        type="checkbox"
                        checked={showAlertsOnly}
                        onChange={e => setShowAlertsOnly(e.target.checked)}
                        style={{ accentColor: 'var(--theme-accent)', cursor: 'pointer' }}
                    />
                    <span>Flagged Only</span>
                </label>
            </div>

            <div style={{ padding: isMobile ? '16px' : '16px 24px', fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Real-time ingestion of active node performance metrics. Click on any record to inspect cryptographic proofs, full payloads, and security policies.</span>
                <span style={{ fontWeight: 800, color: 'var(--theme-accent)' }}>{filteredStream.length} displayed</span>
            </div>

            {/* SCROLLING WINDOW */}
            <div className="card-body mono" style={{ flex: 1, overflowY: 'auto', maxHeight: '520px', fontSize: '0.75rem', padding: '16px 24px' }}>
                {loading && stream.length === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {[1, 2, 3, 4, 5].map(i => (
                            <div key={i} className="skeleton" style={{ height: isMobile ? '120px' : '40px', width: '100%' }} />
                        ))}
                    </div>
                ) : filteredStream.length === 0 ? (
                    <div style={{ padding: '40px', textAlign: 'center', color: 'rgba(255,255,255,0.3)', fontStyle: 'italic' }}>
                        No matching telemetry records found.
                    </div>
                ) : (
                    <AnimatePresence initial={false}>
                        {filteredStream.map((data) => {
                            const isWarning = data.flagged || (data.metadata?.discrepancy_ratio != null && data.metadata.discrepancy_ratio > 0.1);
                            const isExpanded = expandedId === data.id;
                            
                            return (
                                <div 
                                    key={data.id} 
                                    style={{ 
                                        marginBottom: '12px',
                                        border: `1px solid ${isWarning ? 'rgba(244, 63, 94, 0.2)' : isExpanded ? 'rgba(212, 175, 55, 0.3)' : 'rgba(255,255,255,0.03)'}`,
                                        borderRadius: '8px',
                                        background: isExpanded ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.005)',
                                        overflow: 'hidden',
                                        transition: 'all 0.2s'
                                    }}
                                >
                                    {/* Main Row */}
                                    <div 
                                        onClick={() => handleRowClick(data.id)}
                                        style={{
                                            padding: '12px 16px',
                                            display: 'flex',
                                            flexDirection: isMobile ? 'column' : 'row',
                                            alignItems: isMobile ? 'stretch' : 'center',
                                            gap: isMobile ? '8px' : '20px',
                                            cursor: 'pointer',
                                            color: isWarning ? '#f43f5e' : 'rgba(255,255,255,0.8)'
                                        }}
                                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.015)'; }}
                                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                                    >
                                        <span style={{ opacity: 0.6, width: '84px', fontSize: '0.65rem' }}>
                                            {data.created_at ? new Date(data.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                                        </span>

                                        <span style={{ width: '80px', fontWeight: 800, letterSpacing: '0.05em', color: data.type === 'FLAGGED' ? '#f43f5e' : '#10b981' }}>
                                            {data.type}
                                        </span>

                                        <span style={{ width: '120px', color: 'white', fontWeight: 700 }}>
                                            {data.agent}
                                        </span>

                                        {/* Real oracle-reported telemetry signals (TelemetryEventDetailDto): performance
                                            variance, grounding index, verified GPU-hours. No latency/accuracy exists. */}
                                        <div style={{ flex: 1, display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 700 }}>VARIANCE: <span style={{ color: isWarning ? '#f43f5e' : 'white' }}>{data.metadata?.discrepancy_ratio != null ? Number(data.metadata.discrepancy_ratio).toFixed(3) : '—'}</span></span>
                                            <span style={{ fontWeight: 700 }}>GROUNDING: <span style={{ color: 'white' }}>{data.metadata?.hgi_raw != null ? Number(data.metadata.hgi_raw).toFixed(3) : '—'}</span></span>
                                            <span style={{ fontWeight: 700 }}>GPU-HRS: <span style={{ color: 'white' }}>{data.metadata?.gpu_hours_verified != null ? Number(data.metadata.gpu_hours_verified).toFixed(2) : '—'}</span></span>
                                            {data.metadata?.zk_verified && (
                                                <span style={{ color: '#10b981', fontWeight: 800, fontSize: '0.65rem', border: '1px solid rgba(16,185,129,0.3)', padding: '1px 6px', borderRadius: '4px', background: 'rgba(16,185,129,0.05)' }}>[ZK]</span>
                                            )}
                                        </div>

                                        <div style={{ display: 'flex', alignItems: 'center', marginLeft: 'auto' }}>
                                            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                        </div>
                                    </div>

                                    {/* Expanded Detail Panel */}
                                    <AnimatePresence>
                                        {isExpanded && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                                style={{ 
                                                    borderTop: '1px solid rgba(255,255,255,0.05)',
                                                    background: 'rgba(0,0,0,0.3)',
                                                    padding: '16px'
                                                }}
                                            >
                                                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '16px' }}>
                                                    {/* Cryptographic Provenance */}
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '8px', padding: '12px' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.7rem', color: 'var(--theme-accent)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                                            <Lock size={12} /> Cryptographic Provenance
                                                        </div>
                                                        {/* Real fields from the signed TelemetryEventDetailDto — the Merkle leaf that gets
                                                            anchored on-chain via StateAnchor, its nonce, and the oracle's ZK-verify result. */}
                                                        <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.7)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Event ID: </span><span style={{ fontFamily: 'monospace', color: 'white' }}>{data.id}</span></div>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Merkle Leaf: </span><span style={{ fontFamily: 'monospace', color: 'white', wordBreak: 'break-all' }}>{data.metadata?.leaf_hash || '—'}</span></div>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Nonce: </span><span style={{ fontFamily: 'monospace', color: 'white' }}>{data.metadata?.nonce ?? '—'}</span></div>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>ZK Verification: </span><span style={{ color: data.metadata?.zk_verified ? '#10b981' : 'rgba(255,255,255,0.5)', fontWeight: 800 }}>{data.metadata?.zk_verified ? '✓ bb-verified' : 'not ZK-boosted'}</span></div>
                                                        </div>
                                                    </div>

                                                    {/* Policy & Auditing State */}
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '8px', padding: '12px' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.7rem', color: '#60a5fa', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                                            <Shield size={12} /> Scoring Signals
                                                        </div>
                                                        {/* Real signals the oracle actually stores + scores for this event. */}
                                                        <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.7)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Flag Status: </span><span style={{ color: data.flagged ? '#f43f5e' : '#10b981', fontWeight: 800 }}>{data.flagged ? 'FLAGGED' : 'CLEAR'}</span></div>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Performance Variance: </span><span>{data.metadata?.discrepancy_ratio != null ? Number(data.metadata.discrepancy_ratio).toFixed(4) : '—'}</span></div>
                                                            <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>Grounding Index (HGI): </span><span>{data.metadata?.hgi_raw != null ? Number(data.metadata.hgi_raw).toFixed(4) : '—'}</span></div>
                                                        </div>
                                                    </div>
                                                </div>

                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>
                            );
                        })}
                    </AnimatePresence>
                )}
            </div>
            
            <div className="card-footer" style={{ borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)', padding: '12px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="mono" style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)' }}>STREAM_BUFFER: {filteredStream.length}/50</span>
                <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Cpu size={12} /> Base L2 Gas Price: 1.25 gwei
                </span>
            </div>
        </div>
    );
};
