// @ts-nocheck
import React, { useState } from 'react';
import { Search, Globe, Fingerprint, AlertTriangle, Loader2, ArrowRight } from 'lucide-react';
import axios from 'axios';
import { API_BASE } from '../../constants';

export const XNSSearchService: React.FC = () => {
    const [query, setQuery] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async () => {
        if (!query.trim()) return;
        setIsLoading(true);
        setError(null);
        setResult(null);

        try {
            let response;

            if (query.startsWith('did:intg:')) {
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { did: query.trim() }
                });
            } else if (query.endsWith('.intg')) {
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { xns: query.trim() }
                });
            } else if (query.startsWith('0x')) {
                response = await axios.get(`${API_BASE}/v1/identity/agent/${query.trim()}`);
            } else {
                response = await axios.get(`${API_BASE}/v1/identity/resolve`, {
                    params: { xns: query.trim() }
                });
            }

            setResult(response.data);
        } catch (e: any) {
            if (e.response?.status === 404) {
                setError("Agent not found in the XNS Registry.");
            } else {
                setError("Unable to connect to the XNS Resolver.");
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex-col gap-4">
            <div style={{
                display: 'flex',
                gap: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--r-md)',
                padding: '4px 4px 4px 12px',
                alignItems: 'center'
            }}>
                <Search size={16} className="text-muted" />
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="Search handle (e.g. xibalba.intg) or DID..."
                    style={{
                        flex: 1,
                        background: 'transparent',
                        border: 'none',
                        color: 'white',
                        fontSize: '0.85rem',
                        outline: 'none',
                        padding: '8px 0'
                    }}
                />
                <button
                    onClick={handleSearch}
                    disabled={isLoading || !query.trim()}
                    className="btn btn-sm btn-primary"
                    style={{ borderRadius: 'calc(var(--r-md) - 2px)' }}
                >
                    {isLoading ? <Loader2 size={14} className="pulse" /> : <ArrowRight size={14} />}
                </button>
            </div>

            {error && (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px',
                    background: 'rgba(244, 63, 94, 0.08)',
                    border: '1px solid rgba(244, 63, 94, 0.2)',
                    borderRadius: 'var(--r-md)',
                    fontSize: '0.75rem',
                    color: 'rgba(255,255,255,0.7)'
                }}>
                    <AlertTriangle size={16} style={{ color: '#f43f5e', flexShrink: 0 }} />
                    {error}
                </div>
            )}

            {result && (
                <div style={{
                    padding: '16px',
                    background: 'var(--glass-surface-light)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--r-md)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px'
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '8px',
                                background: 'rgba(16, 185, 129, 0.1)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center'
                            }}>
                                <Fingerprint size={18} style={{ color: '#10b981' }} />
                            </div>
                            <div>
                                <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 800 }}>
                                    {result.alias || "Agent Identified"}
                                </h4>
                                <p className="mono" style={{ margin: 0, fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                                    {result.eth_address?.slice(0, 8)}...{result.eth_address?.slice(-8)}
                                </p>
                            </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '1.25rem', fontWeight: 900, color: 'var(--gold)' }}>
                                {result.current_ais}
                            </div>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 800, letterSpacing: '0.05em' }}>
                                AIS SCORE
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                         <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>VERIFICATION</div>
                            <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#60a5fa' }}>Tier {result.verification_tier}</div>
                         </div>
                         <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>TRUST LEVEL</div>
                            <div style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--gold)' }}>{result.trust_level}</div>
                         </div>
                    </div>

                    {result.xns_handle && (
                         <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--gold)' }}>
                            <Globe size={14} />
                            <span style={{ fontWeight: 800 }}>{result.xns_handle}</span>
                         </div>
                    )}
                </div>
            )}

            {!result && !error && !isLoading && (
                <div style={{ textAlign: 'center', padding: '12px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                    Lookup any agent across the Integrity Network by handle or DID.
                </div>
            )}
        </div>
    );
};
