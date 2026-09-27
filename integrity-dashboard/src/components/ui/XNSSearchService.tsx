// @ts-nocheck
import React, { useState } from 'react';
import { Search, Globe, Fingerprint, AlertTriangle, Loader2, ArrowRight, CheckCircle2, Sparkles } from 'lucide-react';
import { oracle } from '../../services/oracle';
import { useDashboard } from '../../context/DashboardContext';

// Two distinct handle systems live behind this one search box:
//  - The on-chain XibalbaNameService (oracle.resolveXns) -- a separate, optional
//    "list this handle as an on-chain alias" step, not the primary directory.
//  - The Oracle-local xns_handles directory (oracle.xnsAvailable/xnsResolveHandle/
//    xnsClaim) -- a chat-app-style unique username per agent, independent of on-chain
//    state, and what every agent registered through this dashboard actually gets. This
//    component searches/claims against the Oracle-local directory; on-chain aliasing is
//    a separate, not-yet-built capability.
export const XNSSearchService: React.FC = () => {
    const { agents } = useDashboard();
    const [query, setQuery] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState<any>(null);
    // Only ever set when xns_available really returned available:true -- drives the
    // "available, pick an agent, claim it" card. Kept strictly separate from
    // `suggestions` below: a taken handle has suggestions but must NOT show this card.
    const [availableHandle, setAvailableHandle] = useState<string | null>(null);
    // Populated whenever the backend returns any (only happens when taken), shown
    // regardless of whether `result` resolved -- independent of `availableHandle`.
    const [suggestions, setSuggestions] = useState<string[]>([]);
    const [claimAgentId, setClaimAgentId] = useState('');
    const [isClaiming, setIsClaiming] = useState(false);
    const [claimed, setClaimed] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const runSearch = async (raw: string) => {
        const q = raw.trim();
        if (!q) return;
        setIsLoading(true);
        setError(null);
        setResult(null);
        setAvailableHandle(null);
        setSuggestions([]);
        setClaimed(null);

        try {
            if (q.startsWith('did:') || q.startsWith('0x')) {
                // Direct DID/address lookup -- an existing agent, not a handle search.
                const detail = await oracle.getAgent(q);
                setResult(detail);
                return;
            }

            const handle = q.replace(/^@/, '');
            const avail = await oracle.xnsAvailable(handle);
            if (avail.available) {
                setAvailableHandle(avail.handle);
                setClaimAgentId(agents[0]?.id ?? '');
                return;
            }

            // Taken -- resolve who holds it and show the same rich agent card the
            // DID/address path shows, sourced from the Oracle-local directory now
            // rather than the on-chain resolver. availableHandle stays null: this
            // handle is NOT available, only its suggestions are.
            try {
                const resolved = await oracle.xnsResolveHandle(handle);
                const detail = await oracle.getAgent(resolved.agent_id);
                setResult({ ...detail, xns_handle: resolved.handle });
            } catch {
                // Handle exists per xns_available but resolve raced/failed -- still
                // honest to say "taken", just without the rich card.
                setError(`Handle "${handle}" is already taken.`);
            }
            setSuggestions(avail.suggestions);
        } catch (e: any) {
            const status = e?.status as number | undefined;
            const msg = String(e?.message ?? '');
            if (status === 400 || msg.includes('400')) {
                setError('Handles are 3-32 characters, lowercase letters/digits/./-/_, starting with a letter.');
            } else {
                setError('Could not search right now. Try again in a moment.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    const handleClaim = async () => {
        if (!availableHandle || !claimAgentId) return;
        setIsClaiming(true);
        setError(null);
        try {
            const claim = await oracle.xnsClaim(claimAgentId, availableHandle);
            setClaimed(claim.handle);
            setAvailableHandle(null);
        } catch (e: any) {
            const status = e?.status as number | undefined;
            if (status === 409) {
                setError('Someone claimed that handle just now, or this agent already holds a different one. Try another.');
            } else {
                setError('Could not claim this handle right now. Try again in a moment.');
            }
        } finally {
            setIsClaiming(false);
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
                    id="xns-search-query"
                    name="xns-search-query"
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && runSearch(query)}
                    placeholder="Search or claim a handle (e.g. atlas), or paste a DID..."
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
                    type="button"
                    aria-label={isLoading ? 'Searching XNS' : 'Search XNS'}
                    onClick={() => runSearch(query)}
                    disabled={isLoading || !query.trim()}
                    className="primary-button"
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

            {claimed && (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px',
                    background: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                    borderRadius: 'var(--r-md)',
                    fontSize: '0.75rem',
                    color: 'rgba(255,255,255,0.85)'
                }}>
                    <CheckCircle2 size={16} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span><strong>{claimed}</strong> is claimed. This agent is now identified by that handle across the ecosystem instead of its DID.</span>
                </div>
            )}

            {availableHandle && (
                <div style={{
                    padding: '16px',
                    background: 'var(--glass-surface-light)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--r-md)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: '#10b981', fontWeight: 800 }}>
                        <CheckCircle2 size={16} />
                        <span className="mono">{availableHandle}</span> is available
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <select
                            aria-label="Agent to claim this handle for"
                            value={claimAgentId}
                            onChange={(e) => setClaimAgentId(e.target.value)}
                            className="input"
                            style={{ flex: 1 }}
                        >
                            {agents.length === 0 && <option value="">No agents available</option>}
                            {agents.map((a) => (
                                <option key={a.namespace_key || a.id} value={a.id}>
                                    {a.alias || a.name || a.id}
                                </option>
                            ))}
                        </select>
                        <button
                            type="button"
                            className="primary-button"
                            onClick={handleClaim}
                            disabled={isClaiming || !claimAgentId}
                        >
                            {isClaiming ? <Loader2 size={14} className="pulse" /> : 'Claim'}
                        </button>
                    </div>
                </div>
            )}

            {suggestions.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 700 }}>
                        <Sparkles size={13} /> Available alternatives
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {suggestions.map((s) => (
                            <button
                                key={s}
                                type="button"
                                className="secondary-button"
                                style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                                onClick={() => { setQuery(s); runSearch(s); }}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
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
                                    {result.handle || result.alias || "Agent Identified"}
                                </h4>
                                <p className="mono" style={{ margin: 0, fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                                    {result.id ? `${result.id.slice(0, 18)}...${result.id.slice(-6)}` : ''}
                                </p>
                            </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '1.25rem', fontWeight: 900, color: 'var(--theme-accent)' }}>
                                {result.current_ais ?? '—'}
                            </div>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 800, letterSpacing: '0.05em' }}>
                                AIS SCORE
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                         <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>VERIFICATION</div>
                            <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#60a5fa' }}>Tier {result.verification_tier ?? 0}</div>
                         </div>
                         <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', fontWeight: 700, marginBottom: '4px' }}>IDENTIFIED BY</div>
                            <div style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--theme-accent)' }}>
                                {result.handle ? 'XNS handle' : 'DID'}
                            </div>
                         </div>
                    </div>

                    {result.handle && (
                         <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--theme-accent)' }}>
                            <Globe size={14} />
                            <span style={{ fontWeight: 800 }}>{result.handle}</span>
                         </div>
                    )}
                </div>
            )}

            {!result && !error && !availableHandle && !suggestions.length && !claimed && !isLoading && (
                <div style={{ textAlign: 'center', padding: '12px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                    Search a handle to check availability and claim it, or paste a DID to look up an existing agent. Agents with a handle are identified by it everywhere; agents without one are identified by DID.
                </div>
            )}
        </div>
    );
};
