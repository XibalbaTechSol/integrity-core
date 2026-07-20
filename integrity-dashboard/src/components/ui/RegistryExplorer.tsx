// @ts-nocheck
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Search, Globe, CheckCircle2, AlertTriangle, Fingerprint, Shield, ArrowRight, Loader2 } from 'lucide-react';
import axios from 'axios';
import { useIsMobile } from '../../utils/useIsMobile';
import { API_BASE } from '../../constants';

interface RegistryExplorerProps {
    isOpen: boolean;
    onClose: () => void;
}

export const RegistryExplorer: React.FC<RegistryExplorerProps> = ({ isOpen, onClose }) => {
    const [query, setQuery] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);
    const isMobile = useIsMobile();

    const handleResolve = async () => {
        if (!query.trim()) return;
        setIsLoading(true);
        setError(null);
        setResult(null);

        try {
            let response;

            if (query.startsWith('did:intg:')) {
                // Resolve from DID string
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { did: query.trim() }
                });
            } else if (query.endsWith('.intg')) {
                // Resolve from XNS handle
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { xns: query.trim() }
                });
            } else if (query.startsWith('0x')) {
                // Direct address lookup (any 0x-prefixed string)
                response = await axios.get(`${API_BASE}/v1/identity/agent/${query.trim()}`);
            } else {
                // Try XNS handle without suffix
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { xns: query.trim() }
                });
            }

            setResult(response.data);
        } catch (e: any) {
            if (e.response?.status === 404) {
                setError("Agent not found in the Integrity Registry. This address has not been registered.");
            } else {
                setError("Unable to connect to the Xibalba Identity Oracle. Please try again.");
            }
        } finally {
            setIsLoading(false);
        }
    };

    const tierLabels: Record<number, { label: string; color: string }> = {
        1: { label: 'Sovereign', color: 'rgba(255,255,255,0.5)' },
        2: { label: 'Linked', color: '#60a5fa' },
        3: { label: 'Institutional', color: 'var(--gold)' }
    };

    if (!isOpen) return null;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={onClose}
                style={{
                    position: 'fixed',
                    inset: 0,
                    background: 'rgba(0,0,0,0.8)',
                    backdropFilter: 'blur(12px)',
                    zIndex: 9999,
                    display: 'flex',
                    alignItems: isMobile ? 'flex-end' : 'center',
                    justifyContent: 'center',
                    padding: isMobile ? '0' : '40px'
                }}
            >
                <motion.div
                    initial={isMobile ? { y: '100%' } : { opacity: 0, y: 40, scale: 0.95 }}
                    animate={{ y: 0, opacity: 1, scale: 1 }}
                    exit={isMobile ? { y: '100%' } : { opacity: 0, y: 40, scale: 0.95 }}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                        width: '100%',
                        maxWidth: '780px',
                        background: '#0a0e1a',
                        border: isMobile ? 'none' : '1px solid rgba(255,255,255,0.08)',
                        borderRadius: isMobile ? '32px 32px 0 0' : '28px',
                        overflow: 'hidden',
                        maxHeight: isMobile ? '95vh' : '90vh',
                        overflowY: 'auto'
                    }}
                >
                    {/* Header */}
                    <div style={{
                        padding: isMobile ? '24px 20px' : '28px 32px',
                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                            <div style={{
                                width: '40px', height: '40px', borderRadius: '12px',
                                background: 'rgba(212, 175, 55, 0.1)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                flexShrink: 0
                            }}>
                                <Globe size={20} style={{ color: 'var(--gold)' }} />
                            </div>
                            <div>
                                <h3 style={{ margin: 0, fontSize: isMobile ? '1rem' : '1.2rem', fontWeight: 800 }}>
                                    XNS Resolver
                                </h3>
                                <p style={{ margin: '2px 0 0', fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
                                    DID resolver
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            style={{
                                background: 'rgba(255,255,255,0.05)', border: 'none',
                                borderRadius: '10px', padding: '8px',
                                cursor: 'pointer', color: 'rgba(255,255,255,0.4)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                            }}
                        >
                            <X size={18} />
                        </button>
                    </div>

                    {/* Search Bar */}
                    <div style={{ padding: isMobile ? '20px' : '32px 32px 24px' }}>
                        <div style={{
                            display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: '12px',
                            background: isMobile ? 'transparent' : 'rgba(255,255,255,0.03)',
                            border: isMobile ? 'none' : '1px solid rgba(255,255,255,0.08)',
                            borderRadius: '16px',
                            padding: isMobile ? '0' : '6px 6px 6px 20px',
                            alignItems: isMobile ? 'stretch' : 'center'
                        }}>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '12px',
                                background: isMobile ? 'rgba(255,255,255,0.03)' : 'transparent',
                                border: isMobile ? '1px solid rgba(255,255,255,0.08)' : 'none',
                                borderRadius: '14px', padding: isMobile ? '0 16px' : '0',
                                flex: 1
                            }}>
                                <Search size={18} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
                                <input
                                    type="text"
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleResolve()}
                                    placeholder="Agent address..."
                                    style={{
                                        flex: 1, background: 'transparent', border: 'none',
                                        color: 'white', fontSize: '0.85rem', fontFamily: 'JetBrains Mono, monospace',
                                        outline: 'none', padding: '14px 0'
                                    }}
                                />
                            </div>
                            <button
                                onClick={handleResolve}
                                disabled={isLoading || !query.trim()}
                                style={{
                                    background: 'var(--gold)', color: '#0a0e1a',
                                    border: 'none', borderRadius: '14px',
                                    padding: '14px 24px', fontWeight: 800,
                                    fontSize: '0.75rem', cursor: 'pointer',
                                    letterSpacing: '0.05em',
                                    opacity: isLoading || !query.trim() ? 0.5 : 1,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                                }}
                            >
                                {isLoading ? <Loader2 size={16} className="pulse" /> : <ArrowRight size={16} />}
                                RESOLVE
                            </button>
                        </div>

                        {!isMobile && (
                            <div style={{
                                display: 'flex', gap: '12px', marginTop: '16px', flexWrap: 'wrap'
                            }}>
                                {['xibalba.intg', '0xTestAgentV8'].map(example => (
                                    <button
                                        key={example}
                                        onClick={() => { setQuery(example); }}
                                        style={{
                                            background: 'rgba(255,255,255,0.03)',
                                            border: '1px solid rgba(255,255,255,0.06)',
                                            borderRadius: '8px', padding: '6px 14px',
                                            color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem',
                                            fontFamily: 'JetBrains Mono, monospace',
                                            cursor: 'pointer', fontWeight: 600
                                        }}
                                    >
                                        {example}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Results */}
                    <div style={{ padding: isMobile ? '0 20px 40px' : '0 32px 32px' }}>
                        {error && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: '16px',
                                    padding: '20px',
                                    background: 'rgba(244, 63, 94, 0.08)',
                                    border: '1px solid rgba(244, 63, 94, 0.2)',
                                    borderRadius: '16px'
                                }}
                            >
                                <AlertTriangle size={20} style={{ color: '#f43f5e', flexShrink: 0 }} />
                                <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)' }}>{error}</span>
                            </motion.div>
                        )}

                        {result && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
                            >
                                {/* Agent Identity Card */}
                                <div style={{
                                    padding: isMobile ? '20px' : '28px',
                                    background: 'rgba(255,255,255,0.02)',
                                    border: '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: '20px'
                                }}>
                                    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: isMobile ? '20px' : '0', marginBottom: '24px' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                            <div style={{
                                                width: '48px', height: '48px', borderRadius: '14px',
                                                background: 'rgba(16, 185, 129, 0.1)',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                                            }}>
                                                <Fingerprint size={24} style={{ color: '#10b981' }} />
                                            </div>
                                            <div style={{ overflow: 'hidden' }}>
                                                <h4 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {result.alias || result.eth_address}
                                                </h4>
                                                <p style={{
                                                    margin: '4px 0 0', fontSize: '0.65rem',
                                                    fontFamily: 'JetBrains Mono, monospace',
                                                    color: 'rgba(255,255,255,0.4)',
                                                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                                                }}>
                                                    {result.eth_address}
                                                </p>
                                            </div>
                                        </div>
                                        <div style={{ textAlign: isMobile ? 'left' : 'right' }}>
                                            <div style={{
                                                fontSize: isMobile ? '1.5rem' : '1.8rem', fontWeight: 900,
                                                color: result.current_ais >= 750 ? 'var(--gold)' : result.current_ais >= 500 ? '#60a5fa' : '#f43f5e'
                                            }}>
                                                {result.current_ais}
                                            </div>
                                            <div style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700, letterSpacing: '0.15em' }}>
                                                INTEGRITY SCORE
                                            </div>
                                        </div>
                                    </div>

                                    {/* Metrics Row */}
                                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '12px' }}>
                                        {[
                                            {
                                                label: 'Verification Tier',
                                                value: `Tier ${result.verification_tier}`,
                                                sub: tierLabels[result.verification_tier]?.label || 'Unknown',
                                                color: tierLabels[result.verification_tier]?.color || 'white'
                                            },
                                            {
                                                label: 'Trust',
                                                value: result.trust_level,
                                                sub: result.trust_level === 'AAA' ? 'Prime' : 'Standard',
                                                color: result.trust_level === 'AAA' ? 'var(--gold)' : '#60a5fa'
                                            },
                                            {
                                                label: 'Ceiling',
                                                value: `${({1: 600, 2: 850, 3: 1000} as Record<number, number>)[result.verification_tier] || 600}`,
                                                sub: 'Max AIS',
                                                color: 'rgba(255,255,255,0.7)'
                                            }
                                        ].map((m, i) => (
                                            <div key={i} style={{
                                                padding: '12px 16px',
                                                background: 'rgba(0,0,0,0.3)',
                                                borderRadius: '12px',
                                                border: '1px solid rgba(255,255,255,0.04)'
                                            }}>
                                                <div style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700, letterSpacing: '0.1em', marginBottom: '4px' }}>
                                                    {m.label.toUpperCase()}
                                                </div>
                                                <div style={{ fontSize: '1rem', fontWeight: 900, color: m.color }}>{m.value}</div>
                                                <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)' }}>{m.sub}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* DID Document Preview */}
                                {result.did_document && (
                                    <div style={{
                                        background: 'rgba(0,0,0,0.4)',
                                        borderRadius: '16px',
                                        border: '1px solid rgba(255,255,255,0.04)',
                                        overflow: 'hidden'
                                    }}>
                                        <div style={{
                                            padding: '12px 16px',
                                            borderBottom: '1px solid rgba(255,255,255,0.04)',
                                            display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                                        }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                <Shield size={12} style={{ color: '#10b981' }} />
                                                <span style={{ fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.1em' }}>
                                                    ZK-PROOFED DID DOCUMENT
                                                </span>
                                            </div>
                                            <CheckCircle2 size={12} style={{ color: '#10b981' }} />
                                        </div>
                                        <pre style={{
                                            padding: '16px',
                                            margin: 0,
                                            fontSize: '0.6rem',
                                            fontFamily: 'JetBrains Mono, monospace',
                                            color: '#10b981',
                                            lineHeight: 1.5,
                                            maxHeight: '180px',
                                            overflow: 'auto',
                                            whiteSpace: 'pre-wrap',
                                            wordBreak: 'break-all'
                                        }}>
                                            {JSON.stringify(result.did_document, null, 2)}
                                        </pre>
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {/* Empty State */}
                        {!result && !error && !isLoading && (
                            <div style={{
                                textAlign: 'center', padding: '40px 20px',
                                color: 'rgba(255,255,255,0.2)'
                            }}>
                                <Search size={32} style={{ marginBottom: '12px', opacity: 0.3 }} />
                                <p style={{ fontSize: '0.8rem', fontWeight: 600, color: 'rgba(255,255,255,0.35)' }}>
                                    Resolve identities
                                </p>
                            </div>
                        )}
                    </div>
                </motion.div>
            </motion.div>
        </AnimatePresence>
    );
};
