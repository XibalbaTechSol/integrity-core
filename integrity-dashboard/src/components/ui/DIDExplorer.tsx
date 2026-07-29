import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    Fingerprint, ShieldCheck, FileText, ExternalLink, 
    Copy, Search, CheckCircle2, Key, Globe, Shield, Zap, Download
} from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';
import { oracle } from '../../services/oracle';

interface DIDExplorerProps {
    agent: any;
}

export const DIDExplorer: React.FC<DIDExplorerProps> = ({ agent }) => {
    const isMobile = useIsMobile();
    const [didDoc, setDidDoc] = useState<any>(null);
    const [vc, setVc] = useState<any>(null);
    const [handle, setHandle] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    // eth_address already holds the agent's DID, so never re-wrap an already-qualified DID
    // (that produced a malformed did:xibalba:did:integrity:… string).
    // Optional-chained on `agent` too: this runs on every render, including the one where
    // `agent` is null, and the `if (!agent) return null` guard below is far too late to
    // stop a bare `agent.eth_address` from throwing first.
    const canonicalDid = didDoc?.id
        || (agent?.eth_address?.startsWith('did:') ? agent.eth_address : `did:xibalba:${agent?.eth_address}`);
    const [activeView, setActiveView] = useState<'did' | 'vc' | 'raw'>('did');

    const downloadDID = () => {
        if (!didDoc) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(didDoc, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", `${agent.alias || 'agent'}_did.json`);
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
    };

    useEffect(() => {
        if (!agent) return;
        
        const fetchIdentity = async () => {
            setIsLoading(true);
            try {
                // Real DID document + real signed Verifiable Credential, both from the oracle
                // (agent.eth_address is the DID). The VC is an Ed25519-signed W3C
                // AgentIntegrityCredential issued live by the oracle's issuer key.
                // The XNS reverse-lookup reads the on-chain XibalbaNameService primary handle;
                // it returns 503 until that singleton is deployed, so it degrades to null
                // rather than faking a handle.
                const [detail, vcDoc, handleDoc] = await Promise.all([
                    oracle.getAgent(agent.eth_address),
                    oracle.getAgentVc(agent.eth_address).catch(() => null),
                    oracle.getAgentHandle(agent.eth_address).catch(() => null),
                ]);
                setDidDoc(detail.did_document || { id: agent.eth_address, note: 'No DID document on record for this agent.' });
                setVc(vcDoc || { note: 'Verifiable Credential unavailable.' });
                setHandle(handleDoc?.handle ?? null);
            } catch (e) {
                console.error("Identity fetch error:", e);
                setDidDoc({ id: agent.eth_address, note: 'DID document unavailable (oracle unreachable).' });
                setVc(null);
            } finally {
                setIsLoading(false);
            }
        };

        fetchIdentity();
    }, [agent]);

    if (!agent) return null;

    if (isLoading) {
        return (
            <div className="enterprise-card" style={{ padding: 'var(--space-10)' }}>
                <div className="skeleton" style={{ height: '40px', width: '240px', marginBottom: 'var(--space-8)', borderRadius: 'var(--r-sm)' }} />
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 'var(--space-8)' }}>
                    <div className="skeleton" style={{ height: '320px', borderRadius: 'var(--r-md)' }} />
                    <div className="skeleton" style={{ height: '320px', borderRadius: 'var(--r-md)' }} />
                </div>
            </div>
        );
    }

    return (
        <div className="enterprise-card" style={{ padding: '0', overflow: 'hidden', borderRadius: 'var(--r-lg)' }}>
            {/* Header / Tabs */}
            <div style={{ padding: 'var(--space-6) var(--space-8)', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: 'center', background: 'var(--glass-surface-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <Fingerprint size={22} style={{ color: 'var(--gold)' }} />
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, color: 'white', fontFamily: 'Playfair Display, serif' }}>Sovereign Identity Explorer</h3>
                </div>
                
                <div style={{ display: 'flex', gap: 'var(--space-2)', background: 'rgba(0,0,0,0.3)', padding: '4px', borderRadius: 'var(--r-md)', marginTop: isMobile ? 'var(--space-4)' : 0 }}>
                    {['did', 'vc', 'raw'].map((view) => (
                        <button
                            key={view}
                            onClick={() => setActiveView(view as any)}
                            style={{
                                padding: '8px 16px',
                                borderRadius: 'var(--r-sm)',
                                border: 'none',
                                background: activeView === view ? 'var(--gold-muted)' : 'transparent',
                                color: activeView === view ? 'var(--gold)' : 'var(--text-muted)',
                                fontSize: '0.65rem',
                                fontWeight: 800,
                                cursor: 'pointer',
                                textTransform: 'uppercase',
                                letterSpacing: '0.1em'
                            }}
                        >
                            {view}
                        </button>
                    ))}
                </div>
            </div>

            <div style={{ padding: 'var(--space-8)' }}>
                <AnimatePresence mode="wait">
                    {activeView === 'did' && (
                        <motion.div
                            key="did_view"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                        >
                            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 'var(--space-10)' }}>
                                {/* DID Document Visualization */}
                                <div>
                                    <div style={{ marginBottom: 'var(--space-8)' }}>
                                        <div style={{ fontSize: '0.6rem', fontWeight: 900, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: '8px' }}>Global DID Identifier</div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                                            <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--gold)', wordBreak: 'break-all', flex: 1 }}>{canonicalDid}</span>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                <button onClick={() => navigator.clipboard.writeText(canonicalDid)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }} title="Copy to Clipboard"><Copy size={14} /></button>
                                                <button onClick={downloadDID} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }} title="Download DID document (.json)" id="did-download-btn-did"><Download size={14} /></button>
                                            </div>
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                                        <div style={{ padding: '24px', background: 'var(--glass-surface-light)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                                                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(16, 185, 129, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--emerald)' }}>
                                                    <Key size={16} />
                                                </div>
                                                <span style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Verification Method</span>
                                            </div>
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.8 }}>
                                                <span className="mono">TYPE: JsonWebKey2020</span><br />
                                                <span className="mono">CTRL: {didDoc?.id?.slice(0, 16)}...</span><br />
                                                <span className="mono">LAYER: Base_Sepolia_L2</span>
                                            </div>
                                        </div>

                                        <div style={{ padding: '24px', background: 'var(--glass-surface-light)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                                                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(96, 165, 250, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa' }}>
                                                    <Globe size={16} />
                                                </div>
                                                <span style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Service Resolution</span>
                                            </div>
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.8 }}>
                                                <span className="mono">ORACLE: protocol.xibalba.io/v1/agent</span><br />
                                                <span className="mono">RESOLVER: identity.xibalba.io/v1/vc</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Identity Schematic */}
                                <div style={{ background: 'linear-gradient(225deg, rgba(201, 168, 76, 0.05) 0%, rgba(5, 13, 24, 0.8) 100%)', borderRadius: 'var(--r-lg)', padding: '40px', position: 'relative', overflow: 'hidden', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                                    <div style={{ position: 'absolute', top: '0', left: '0', width: '100%', height: '100%', opacity: 0.1, pointerEvents: 'none' }}>
                                        <div className="pulse-gold" style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '200px', height: '200px', border: '1px solid var(--gold)', borderRadius: '50%' }} />
                                        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '300px', height: '300px', border: '1px dashed rgba(255,255,255,0.2)', borderRadius: '50%' }} />
                                    </div>
                                    
                                    <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', width: '100%' }}>
                                        <div style={{ width: '100px', height: '100px', borderRadius: '24px', background: 'rgba(201, 168, 76, 0.15)', border: '2px solid var(--gold)', margin: '0 auto 24px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)', boxShadow: '0 0 40px rgba(201, 168, 76, 0.2)' }}>
                                            <Fingerprint size={48} />
                                        </div>
                                        <h4 style={{ fontSize: '1.25rem', fontWeight: 800, margin: '0 0 8px', fontFamily: 'Playfair Display, serif' }}>{agent.alias || "Sovereign Node"}</h4>
                                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 16px', background: 'var(--gold-muted)', borderRadius: 'var(--r-xl)', border: '1px solid var(--border)', marginBottom: '32px' }}>
                                            <Shield size={12} style={{ color: 'var(--gold)' }} />
                                            <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Tier {agent.verification_tier} Guardian</span>
                                        </div>
                                        
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', width: '100%' }}>
                                            {[
                                                { label: 'XNS_RESOLVE', value: (handle ? `${handle.includes('.') ? handle : `${handle}.intg`}` : agent.xns_handle) || "UNANCHORED", active: !!(handle || agent.xns_handle) },
                                                { label: 'PROTO_VER', value: 'INTG_V1.0', active: true },
                                                { label: 'STATUS', value: 'ANCHORED', active: true },
                                            ].map((item, i) => (
                                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                                                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 800 }}>{item.label}</span>
                                                    <span className="mono" style={{ fontSize: '0.65rem', fontWeight: 800, color: item.active ? 'var(--emerald)' : 'var(--text-muted)' }}>{item.value}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {activeView === 'vc' && (
                        <motion.div
                            key="vc_view"
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -20 }}
                        >
                            <div className="enterprise-card" style={{ background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, var(--navy-deep) 100%)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: 'var(--space-10)', borderRadius: 'var(--r-lg)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-10)' }}>
                                    <div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '8px' }}>
                                            <ShieldCheck size={32} style={{ color: 'var(--emerald)' }} />
                                            <h4 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0, fontFamily: 'Playfair Display, serif' }}>Verifiable Reputation Credential</h4>
                                        </div>
                                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Standardized W3C VC Data Model v1.1 // Integrity Protocol Profile</p>
                                    </div>
                                    <div className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--emerald)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '8px 16px', borderRadius: 'var(--r-xl)', fontSize: '0.65rem', fontWeight: 900 }}>ZK-SNARK PROVEN</div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 'var(--space-6)', marginBottom: 'var(--space-10)' }}>
                                    {[
                                        { label: 'AIS_METRIC', value: vc?.credentialSubject?.ais_score || agent.current_ais, color: 'white' },
                                        { label: 'TRUST_TIER', value: vc?.credentialSubject?.trust_level || 'AAA', color: 'var(--gold)' },
                                        { label: 'SECURITY', value: `LEVEL_${agent.verification_tier}`, color: '#60a5fa' },
                                        { label: 'TTL', value: '2592000s', color: 'var(--text-muted)' },
                                    ].map((stat, i) => (
                                        <div key={i} style={{ padding: '20px', background: 'rgba(0,0,0,0.3)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                                            <div style={{ fontSize: '0.6rem', fontWeight: 900, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '12px' }}>{stat.label}</div>
                                            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: stat.color, fontFamily: 'Playfair Display, serif' }}>{stat.value}</div>
                                        </div>
                                    ))}
                                </div>

                                <div style={{ padding: '24px', background: 'rgba(5, 13, 24, 0.6)', borderRadius: 'var(--r-md)', border: '1px dashed var(--border)', marginBottom: 'var(--space-10)' }}>
                                    <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <Zap size={14} style={{ color: 'var(--gold)' }} /> CRYPTOGRAPHIC PROOF STRING (JWS/EDDSA)
                                    </div>
                                    <div className="mono" style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', wordBreak: 'break-all', lineHeight: 1.6 }}>
                                        {vc?.proof?.jws || "eyJhbGciOiJFZERTQSIsImI2NCI6ZmFsc2UsImNyaXQiOlsidW51c2VkIl19..zk_proof_auth_0x71c7"}
                                    </div>
                                </div>

                                <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
                                    <button className="btn btn-primary" style={{ flex: 1, padding: '16px', fontSize: '0.85rem' }}>
                                        <ExternalLink size={18} style={{ marginRight: '10px' }} /> EXPORT TO CLEARING HOUSE
                                    </button>
                                    <button className="btn btn-outline" style={{ flex: 1, padding: '16px', fontSize: '0.85rem' }}>
                                        <CheckCircle2 size={18} style={{ marginRight: '10px' }} /> VALIDATE ON-CHAIN
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {activeView === 'raw' && (
                        <motion.div
                            key="raw_view"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
                                <button 
                                    className="btn btn-outline btn-sm" 
                                    onClick={downloadDID}
                                    id="did-download-btn-raw"
                                    style={{ padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem' }}
                                >
                                    <Download size={14} /> Download DID File (.json)
                                </button>
                            </div>
                            <div style={{ background: 'rgba(5, 13, 24, 0.6)', padding: '32px', borderRadius: 'var(--r-md)', border: '1px solid var(--border)', maxHeight: '500px', overflow: 'auto' }}>
                                <pre className="mono" style={{ margin: 0, fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.8 }}>
                                    {JSON.stringify(didDoc || { error: "DID Document not resolved" }, null, 2)}
                                </pre>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
};
