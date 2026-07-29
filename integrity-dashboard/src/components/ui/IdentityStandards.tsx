// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { Fingerprint, Shield, Globe, Lock, CheckCircle2, ExternalLink, Key, Search } from 'lucide-react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { RegistryExplorer } from './RegistryExplorer';
import { useIsMobile } from '../../utils/useIsMobile';

const DEMO_AGENT = "0xTestAgentV8";

export const IdentityStandards = () => {
    const [didDoc, setDidDoc] = useState<any>(null);
    const [registryOpen, setRegistryOpen] = useState(false);
    const [vc, setVc] = useState<any>(null);
    const isMobile = useIsMobile();

    useEffect(() => {
        const fetchIdentityData = async () => {
            {
                // Illustrative W3C DID / Verifiable-Credential example — this component
                // documents the identity STANDARD (format/shape), it is not live agent data.
                // Real per-agent DID documents render on the Identity page (DIDExplorer).
                setDidDoc({
                    "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/jws-2020/v1"],
                    "id": "did:intg:0xTestAgentV8",
                    "verificationMethod": [{ "id": "did:intg:0xTestAgentV8#key-1", "type": "JsonWebKey2020", "controller": "did:intg:0xTestAgentV8", "blockchainAccountId": "eip155:8453:0xTestAgentV8" }],
                    "authentication": ["did:intg:0xTestAgentV8#key-1"],
                    "service": [{ "id": "did:intg:0xTestAgentV8#integrity-oracle", "type": "AgentTrustOracle", "serviceEndpoint": "https://api.xibalba.solutions/v1/agent/0xTestAgentV8" }]
                });
                setVc({
                    "@context": ["https://www.w3.org/2018/credentials/v1", "https://xibalba.solutions/contexts/agent-trust/v1"],
                    "type": ["VerifiableCredential", "AgentIntegrityCredential"],
                    "issuer": "did:intg:xibalba-oracle-01",
                    "credentialSubject": { "id": "did:intg:0xTestAgentV8", "ais_score": 880, "verification_tier": 3, "trust_level": "AAA" },
                    "proof": { "type": "JsonWebSignature2020", "verificationMethod": "did:intg:xibalba-oracle-01#key-1" }
                });
            }
        };
        fetchIdentityData();
    }, []);

    const standards = [
        {
            title: "W3C DID (did:intg)",
            desc: "Native implementation of Decentralized Identifiers. Every agent is assigned a sovereign DID anchored to the Xibalba Root of Trust.",
            icon: <Fingerprint size={24} />,
            color: "var(--gold)",
            explanation: "Decentralized Identifiers (DIDs) are the bedrock of sovereign identity. By assigning every agent a did:intg URI, we decouple reputation from specific platforms or blockchains. This ensures that an agent's trust history remains portable, verifiable, and entirely under the control of its owner, preventing 'de-platforming' risk in autonomous commerce.",
            link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki"
        },
        {
            title: "ERC-8004 Registry",
            desc: "On-chain reputation hooks. Enables smart contracts to query agent trust scores for insurance and collateral decisions in real-time.",
            icon: <Shield size={24} />,
            color: "#60a5fa",
            explanation: "ERC-8004 provides the standard interface for on-chain trust queries. By indexing Agent Integrity Scores (AIS) in a decentralized registry, we allow DeFi protocols and insurance smart contracts to execute logic based on trust data. This bridges the gap between off-chain telemetry and on-chain financial finality, enabling automated risk mitigation.",
            link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki"
        },
        {
            title: "Verifiable Credentials",
            desc: "Zero-Knowledge proofs of AIS history. Share your reputation without exposing private telemetry or commercial transaction data.",
            icon: <Lock size={24} />,
            color: "#10b981",
            explanation: "Verifiable Credentials (VCs) allow agents to prove their reputation without leaking sensitive business logic. Using ZK-proofs, an agent can demonstrate it has an AIS above 800 without revealing its specific transaction history or commercial partners. This preserves privacy while maintaining the highest standards of verifiable accountability.",
            link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki"
        },
        {
            title: "Verification Tiers",
            desc: "Hierarchical accountability levels. Tier-based trust ceilings ensure that high-reputation nodes are backed by legal and domain standing.",
            icon: <Key size={24} />,
            color: "#f59e0b",
            explanation: "Verification Tiers enforce a 'Skin in the Game' model. By mathematically capping scores based on the level of identity binding (Sovereign, Linked, or Institutional), we prevent anonymous agents from reaching institutional trust levels. This protects the network from Sybil attacks and ensures that high-value transactions only occur between verified entities.",
            link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki"
        }
    ];

    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(0,0,0,0.3)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '40px' : '80px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em' }}>Protocol Standardization</span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3rem', fontWeight: 800, marginTop: '16px', lineHeight: 1.1 }}>Identity Sovereignty by Design.</h2>
                    <p style={{ color: 'rgba(255,255,255,0.4)', maxWidth: '700px', margin: '24px auto 0', lineHeight: 1.6, fontSize: isMobile ? '0.9rem' : '1rem' }}>
                        Integrity Protocol integrates with global identity standards to ensure that agent reputation is portable, verifiable, and institutional-grade.
                    </p>
                </div>

                {/* Standard Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, 1fr)', gap: isMobile ? '24px' : '32px' }}>
                    {standards.map((s, i) => (
                        <motion.div 
                            key={i}
                            whileHover={isMobile ? {} : { y: -10 }}
                            className="enterprise-card"
                            style={{ padding: isMobile ? '24px' : '32px', border: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)' }}
                        >
                            <div style={{ color: s.color, marginBottom: '20px' }}>{s.icon}</div>
                            <h3 style={{ fontSize: '1.2rem', marginBottom: '12px' }}>{s.title}</h3>
                            <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, lineHeight: 1.5, marginBottom: '16px' }}>{s.desc}</p>
                            <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.75rem', lineHeight: 1.6, marginBottom: '24px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px' }}>
                                {isMobile ? (s.explanation.length > 100 ? s.explanation.slice(0, 100) + '...' : s.explanation) : s.explanation}
                            </p>
                            <a 
                                href={s.link} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                style={{ display: 'flex', alignItems: 'center', gap: '8px', color: s.color, fontSize: '0.7rem', fontWeight: 700, cursor: 'pointer', textDecoration: 'none', marginTop: 'auto' }}
                            >
                                VIEW DOCUMENTATION <ExternalLink size={14} />
                            </a>
                        </motion.div>
                    ))}
                </div>

                {/* Live Identity Vault Preview */}
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    style={{ marginTop: isMobile ? '40px' : '80px' }}
                >
                    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: '16px', marginBottom: '32px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                            <div style={{ padding: '10px', background: 'rgba(212, 175, 55, 0.1)', borderRadius: '12px', color: 'var(--gold)' }}>
                                <Key size={20} />
                            </div>
                            <div>
                                <h3 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0 }}>Live Identity Vault</h3>
                                <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', margin: '4px 0 0' }}>Real-time DID Document & VC output.</p>
                            </div>
                        </div>
                        <div style={{ marginLeft: isMobile ? '0' : 'auto' }}>
                            <div className="badge badge-gold" style={{ fontSize: '0.6rem' }}>W3C COMPLIANT</div>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: isMobile ? '20px' : '32px' }}>
                        {/* DID Document Panel */}
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <Globe size={16} style={{ color: 'var(--gold)' }} />
                                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase' }}>did:intg Document</span>
                                </div>
                                <div style={{ display: 'flex', gap: '6px' }}>
                                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ff5f56' }} />
                                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ffbd2e' }} />
                                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#27c93f' }} />
                                </div>
                            </div>
                            <div style={{ padding: '24px', maxHeight: '360px', overflow: 'auto' }}>
                                <pre style={{ margin: 0, fontSize: '0.7rem', fontFamily: 'JetBrains Mono, monospace', color: '#10b981', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                                    {didDoc ? JSON.stringify(didDoc, null, 2) : '// Resolving DID...'}
                                </pre>
                            </div>
                        </div>

                        {/* Verifiable Credential Panel */}
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <CheckCircle2 size={16} style={{ color: '#10b981' }} />
                                    <span style={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Verifiable Credential</span>
                                </div>
                                <div className="badge badge-gold" style={{ fontSize: '0.55rem', padding: '4px 10px' }}>SIGNED</div>
                            </div>
                            <div style={{ padding: '24px', maxHeight: '360px', overflow: 'auto' }}>
                                <pre style={{ margin: 0, fontSize: '0.7rem', fontFamily: 'JetBrains Mono, monospace', color: 'var(--gold)', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                                    {vc ? JSON.stringify(vc, null, 2) : '// Generating VC...'}
                                </pre>
                            </div>
                        </div>
                    </div>

                    {/* Resolver Info Bar */}
                    <div style={{ marginTop: '32px', padding: isMobile ? '20px' : '28px 32px', background: 'rgba(212, 175, 55, 0.05)', border: '1px solid rgba(212, 175, 55, 0.15)', borderRadius: '20px', display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: isMobile ? '20px' : '32px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                            <div style={{ width: '48px', height: '48px', flexShrink: 0, borderRadius: '12px', background: 'rgba(212, 175, 55, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <Fingerprint size={24} style={{ color: 'var(--gold)' }} />
                            </div>
                            {isMobile && <h4 style={{ fontSize: '1.1rem', margin: 0 }}>XNS Service</h4>}
                        </div>
                        <div style={{ flex: 1 }}>
                            {!isMobile && (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                                    <h4 style={{ fontSize: '1.1rem', margin: 0 }}>Xibalba Name Service (XNS) — <span style={{ color: 'var(--gold)' }}>Free for All Agents</span></h4>
                                </div>
                            )}
                            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', margin: 0, lineHeight: 1.6 }}>
                                Every registered agent receives a globally resolvable <code style={{ color: 'var(--gold)' }}>did:intg</code> identifier at no cost.
                            </p>
                        </div>
                        <button 
                            onClick={() => setRegistryOpen(true)}
                            style={{ 
                                width: isMobile ? '100%' : 'auto',
                                whiteSpace: 'nowrap', border: '1px solid var(--gold)', 
                                color: 'var(--gold)', padding: '14px 28px', borderRadius: '14px', 
                                background: 'rgba(212, 175, 55, 0.08)', cursor: 'pointer', 
                                fontSize: '0.8rem', fontWeight: 800, letterSpacing: '0.05em',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
                                transition: 'all 0.2s'
                            }}
                        >
                            <Search size={16} />
                            Explore Registry
                        </button>
                    </div>
                </motion.div>
            </div>

            <RegistryExplorer isOpen={registryOpen} onClose={() => setRegistryOpen(false)} />
        </section>
    );
};
