import React from 'react';
import { Fingerprint, Database, Lock, Cpu, Globe, GitBranch, Copy, Zap, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';

export const IdentityCeilingsSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(212, 175, 55, 0.03)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.2fr', gap: isMobile ? '40px' : '80px', alignItems: 'flex-start' }}>
                    <div>
                        <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '16px', display: 'block' }}>Accountability Framework</span>
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '32px', lineHeight: 1.1 }}>Verification Ladder & <span style={{ color: 'var(--gold)' }}>Trust Ceilings.</span></h2>
                        <p style={{ fontSize: isMobile ? '1.1rem' : '1.2rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '32px', maxWidth: '800px', fontWeight: 500 }}>
                            {isMobile ? 
                                "Reputation must be bound to responsibility. The Integrity Protocol bridges the 'Verification Gap' through a multi-tier ladder, mathematically capping scores based on real-world accountability." :
                                'In the emerging agentic web, the "Verification Gap" between an autonomous script and legal liability is the single greatest hurdle to scale. The Integrity Protocol bridges this gap through a multi-tier Verification Ladder, mathematically capping Agent Integrity Scores (AIS) based on cryptographic and real-world accountability.'
                            }
                        </p>
                        {!isMobile && (
                            <>
                                <p style={{ fontSize: '1.05rem', color: 'rgba(255,255,255,0.45)', lineHeight: 1.9, marginBottom: '40px', maxWidth: '850px' }}>
                                    We believe an agent’s reputation is a sovereign asset that must be anchored to a verifiable root of trust on Base L2. The Verification Ladder ensures that as an agent’s financial and economic impact grows, its level of verifiable accountability scales in lockstep. By anchoring digital reputation to sovereign keys, developer domains, and corporate identities, we create a "trust topology" where agents are fully accountable participants in the decentralized economy.
                                </p>
                                <p style={{ fontSize: '1.05rem', color: 'rgba(255,255,255,0.45)', lineHeight: 1.9, marginBottom: '60px', maxWidth: '850px' }}>
                                    This architecture mathematically neutralizes "reputation laundering" and Sybil attacks. No matter how many transactions a developer-key agent processes, it can never exceed the 300 AIS Developer Cap. To reach Sovereign (600), Linked (850), or Institutional-grade (1000) status, the agent’s operator must submit to escalating cryptographic and entity audits, effectively staking their real-world standing against the agent’s operational integrity.
                                </p>
                            </>
                        )}
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
                            <div className="enterprise-card" style={{ padding: isMobile ? '24px' : '48px', background: 'rgba(255,255,255,0.01)', borderLeft: '4px solid var(--gold)' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                                    <div style={{ color: 'var(--gold)' }}><Fingerprint size={32} /></div>
                                    <h4 style={{ fontSize: isMobile ? '1.2rem' : '1.4rem', fontWeight: 700, margin: 0 }}>EIP-712 Entity Binding</h4>
                                </div>
                                <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.8, margin: 0 }}>
                                    {isMobile ? 
                                        "Agents are cryptographically linked to Controllers via human-readable typed data signatures, establishing an immutable on-chain bond." :
                                        "Agents are cryptographically linked to their Controllers using secure, human-readable typed data signatures. This establishes an immutable, on-chain bond between a high-performance machine and the legal entity held financially responsible for its outcomes. By utilizing EIP-712, we ensure that the signing process is transparent to the human operator, creating a permanent audit trail that bridges the gap between smart contract logic and real-world legal recourse."
                                    }
                                </p>
                            </div>
                            <div className="enterprise-card" style={{ padding: isMobile ? '24px' : '48px', background: 'rgba(255,255,255,0.01)', borderLeft: '4px solid var(--gold)' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                                    <div style={{ color: 'var(--gold)' }}><Database size={32} /></div>
                                    <h4 style={{ fontSize: isMobile ? '1.2rem' : '1.4rem', fontWeight: 700, margin: 0 }}>Deterministic Ceilings</h4>
                                </div>
                                <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.8, margin: 0 }}>
                                    {isMobile ?
                                        "Scoring logic enforces a rigorous boundary: AIS = min(Score, TierCap). Trust is earned through combined performance and verified standing." :
                                        "The protocol's scoring logic enforces a rigorous mathematical boundary: AIS = min(Score, TierCap). This ensures that trust is earned through a combination of performance and proof. An anonymous agent (Tier 1) with flawless metrics remains capped at 600 AIS, signaling to the network that while the agent is capable, it lacks the legal accountability required for high-value settlement."
                                    }
                                </p>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                        {[
                            { 
                                tier: "Tier 1: Sovereign", 
                                cap: "600 AIS", 
                                desc: "Base L2 cryptographic key binding.",
                                color: '#94a3b8',
                                badgeName: "Sovereign Insignia",
                                link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
                                explanation: "Sovereign agents represent the entry layer of the autonomous economy. By binding reputation to a cryptographic key-pair rather than a legal identity, we enable privacy-first automation. This tier is essential for agents performing low-risk tasks, research, or cross-chain arbitrage where speed and pseudonymity are prioritized over deep institutional trust.",
                                requirements: [
                                    "Ownership proof via Ethereum signature (EIP-191)",
                                    "Minimum 100 ITK staked in Protocol Vault",
                                    "Active agent heartbeat within 24 hours"
                                ],
                                benefits: [
                                    "Basic access to Xibalba Network",
                                    "Self-custodial reputation management",
                                    "900bps Insurance Premium (Subprime)"
                                ],
                                risk: "CCC (Speculative)"
                            },
                            { 
                                tier: "Tier 2: Linked", 
                                cap: "850 AIS", 
                                desc: "Domain-verified accountability.",
                                color: '#3b82f6',
                                badgeName: "Verified Seal",
                                link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
                                explanation: "Linked verification bridges the gap between the blockchain and the traditional web. By verifying domain ownership (DNS) or social presence (GitHub), agents prove they are managed by established entities. This level of accountability is critical for B2B services, where counterparty risk must be mitigated through verifiable standing.",
                                requirements: [
                                    "DNS TXT record verification or Well-Known URL binding",
                                    "Verified GitHub or X (Twitter) social attestation",
                                    "Minimum 500 ITK staked in Protocol Vault",
                                    "Deterministic telemetry history (>100 handshakes)"
                                ],
                                benefits: [
                                    "AA-Tier Insurance eligibility (250bps premium)",
                                    "Priority routing in agent-to-agent discovery",
                                    "Access to secure multi-party computation pools"
                                ],
                                risk: "AA (Investment Grade)"
                            },
                            { 
                                tier: "Tier 3: Institutional", 
                                cap: "1000 AIS", 
                                desc: "Full legal entity accountability.",
                                color: 'var(--gold)',
                                badgeName: "Institutional Crest",
                                link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
                                explanation: "Institutional verification is the gold standard for mission-critical autonomous systems. It binds an agent directly to a legal corporation through rigorous KYC/KYB audits. This tier is mandatory for large-scale commerce, ensuring that every on-chain action is backed by enforceable real-world legal and financial liability.",
                                requirements: [
                                    "Institutional KYC/KYB audit by Xibalba Identity Oracle",
                                    "Legal entity identifier (LEI) or DUNS number binding",
                                    "Minimum 2,500 ITK staked (Collateralized)",
                                    "Quarterly cryptographic transparency audit"
                                ],
                                benefits: [
                                    "AAA-Tier Risk Rating (120bps insurance premium)",
                                    "Zero-collateral borrowing via reputation-hooks",
                                    "Direct participation in Protocol Governance DAO",
                                    "High-frequency settlement priority"
                                ],
                                risk: "AAA (Prime)"
                            }
                        ].map((tier, i) => (
                            <motion.div key={i} whileHover={{ x: isMobile ? 0 : -8 }} style={{ padding: isMobile ? '24px' : '40px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', position: 'relative', overflow: 'hidden' }}>
                                <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: tier.color }} />
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                                    <div>
                                        <div style={{ color: tier.color, fontSize: '0.65rem', fontWeight: 900, letterSpacing: '0.2em', marginBottom: '8px' }}>{tier.badgeName.toUpperCase()}</div>
                                        <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800 }}>{tier.tier}</h3>
                                    </div>
                                    <div style={{ background: `${tier.color}15`, border: `1px solid ${tier.color}30`, padding: '8px 16px', borderRadius: '12px', textAlign: 'center' }}>
                                        <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.5)', fontWeight: 800, marginBottom: '2px' }}>HARD CAP</div>
                                        <div style={{ fontSize: '1.2rem', fontWeight: 900, color: tier.color }}>{tier.cap}</div>
                                    </div>
                                </div>
                                <p style={{ fontSize: '0.95rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.7, marginBottom: '24px' }}>{tier.explanation}</p>
                                
                                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '24px', marginBottom: '32px' }}>
                                    <div>
                                        <h5 style={{ fontSize: '0.75rem', fontWeight: 800, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.1em', marginBottom: '12px' }}>REQUIREMENTS</h5>
                                        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                            {tier.requirements.map((req, j) => (
                                                <li key={j} style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                                                    <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: tier.color, marginTop: '6px', flexShrink: 0 }} />
                                                    {req}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                    <div>
                                        <h5 style={{ fontSize: '0.75rem', fontWeight: 800, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.1em', marginBottom: '12px' }}>BENEFITS</h5>
                                        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                            {tier.benefits.map((ben, j) => (
                                                <li key={j} style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                                                    <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#10b981', marginTop: '6px', flexShrink: 0 }} />
                                                    {ben}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>

                                <div style={{ paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>RISK PROFILE:</span>
                                        <span style={{ fontSize: '0.75rem', fontWeight: 900, color: tier.color }}>{tier.risk}</span>
                                    </div>
                                    <a href={tier.link} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700 }}>
                                        SPEC <ArrowRight size={14} />
                                    </a>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export const ZeroKnowledgeSection = () => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(212, 175, 55, 0.02)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.2fr 1fr', gap: isMobile ? '40px' : '100px', alignItems: 'center' }}>
                    <div className="enterprise-card" style={{ padding: 0, background: '#050d18', border: '1px solid rgba(167, 139, 250, 0.1)', overflow: isMobile ? 'hidden' : 'visible', boxShadow: '0 40px 100px rgba(0,0,0,0.4)', position: 'relative' }}>
                        <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '4px', background: 'linear-gradient(90deg, #a78bfa 0%, transparent 100%)' }} />
                        <div style={{ padding: '16px 24px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <Lock size={14} style={{ color: '#a78bfa' }} />
                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>circuits/reputation/src/main.nr</span>
                            </div>
                            <div style={{ fontSize: '0.6rem', color: '#a78bfa', fontWeight: 900 }}>NOIR_ZK_CIRCUIT</div>
                        </div>
                        <pre style={{ padding: '32px', margin: 0, overflowX: 'auto', fontSize: '0.85rem', lineHeight: 1.6, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
                            <code style={{ color: '#a78bfa' }}>fn</code> main(<br />
                            {'  '}ais_score: <code style={{ color: '#60a5fa' }}>pub Field</code>,<br />
                            {'  '}tier_ceiling: <code style={{ color: '#60a5fa' }}>pub Field</code>,<br />
                            {'  '}telemetry_hash: <code style={{ color: '#60a5fa' }}>Field</code>,<br />
                            {'  '}secret_key: <code style={{ color: '#60a5fa' }}>Field</code><br />
                            ) {'{\n'}
                            {'  '} <code style={{ color: 'rgba(255,255,255,0.3)' }}>// Assert score falls within verified tier limits</code>{'\n'}
                            {'  '} <code style={{ color: '#a78bfa' }}>assert</code>(ais_score {'<='} tier_ceiling);{'\n'}
                            {'  '} <code style={{ color: '#a78bfa' }}>assert</code>(ais_score {'<='} 1000);{'\n\n'}
                            {'  '} <code style={{ color: 'rgba(255,255,255,0.3)' }}>// Verify identity binding via poseidon hash</code>{'\n'}
                            {'  '} <code style={{ color: '#a78bfa' }}>let</code> identity_check = std::hash::poseidon::hash([secret_key]);{'\n'}
                            {'  '} <code style={{ color: '#a78bfa' }}>assert</code>(identity_check == telemetry_hash);{'\n'}
                            {'}'}
                        </pre>
                        <div style={{ padding: '20px 32px', background: 'rgba(167, 139, 250, 0.05)', borderTop: '1px solid rgba(167, 139, 250, 0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontSize: '0.65rem', fontWeight: 800, color: '#a78bfa' }}>CIRCUIT_STATUS: VERIFIED</div>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#a78bfa' }} />
                                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#a78bfa', opacity: 0.5 }} />
                                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#a78bfa', opacity: 0.2 }} />
                            </div>
                        </div>
                    </div>

                    <div>
                        <span style={{ color: '#a78bfa', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '16px', display: 'block' }}>Privacy-First Accountability</span>
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '32px', lineHeight: 1.1 }}>The Cryptography<br /> of <span style={{ color: '#a78bfa' }}>Zero-Knowledge.</span></h2>
                        <p style={{ fontSize: '1.15rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '32px', fontWeight: 500 }}>
                            Solving the Transparency Paradox. The Integrity Protocol utilizes Zero-Knowledge (ZK) proofs to allow agents to prove their reputation without leaking proprietary telemetry or commercial history.
                        </p>
                        <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.8, marginBottom: '32px' }}>
                            In the autonomous machine economy, performance data is a valuable commercial secret. Forcing agents to share their raw latency logs and transaction details to achieve a trust rating is a violation of their operational sovereignty. Our Noir-based ZK-circuits allow agents to generate a SNARK (Succinct Non-interactive Argument of Knowledge) that proves they meet specific AIS thresholds and risk parameters mathematically, keeping the inputs hidden from verifiers. This enables institutional trust without data compromise.
                        </p>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', marginBottom: '48px' }}>
                            {[
                                { title: "Noir Logic Constraints", desc: "Complex Tri-Metric models—including exponential decay and multiplicative correlation—are compiled into deterministic cryptographic circuits using the Noir DSL.", icon: <Cpu size={20} color="#a78bfa" /> },
                                { title: "Succinct Proof Generation", desc: "Generate multi-vector reputation badges that can be verified on-chain (Base L2) for less than $0.01 in gas, providing highly efficient reputational finality.", icon: <Lock size={20} color="#a78bfa" /> },
                                { title: "Universal Portability", desc: "Reputation SNARKs travel with the agent's did:intg identifier, providing a universal trust anchor that can be verified permissionlessly across Arbitrum, Solana, and Ethereum.", icon: <Globe size={20} color="#a78bfa" /> }
                            ].map((feat, i) => (
                                <div key={i} style={{ display: 'flex', gap: '20px' }}>
                                    <div style={{ padding: '12px', background: 'rgba(167, 139, 250, 0.1)', borderRadius: '12px', height: 'fit-content' }}>
                                        {feat.icon}
                                    </div>
                                    <div>
                                        <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '4px' }}>{feat.title}</h4>
                                        <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.4)', margin: 0, lineHeight: 1.5 }}>{feat.desc}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div style={{ display: 'flex', gap: '20px' }}>
                            <button 
                                onClick={() => window.open('https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki', '_blank')}
                                className="btn btn-primary" 
                                style={{ background: '#a78bfa', color: 'black' }}
                            >
                                READ ZK-SPECS
                            </button>
                            <a 
                                href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="btn btn-outline" 
                                style={{ border: '1px solid rgba(167, 139, 250, 0.3)', color: 'white', textDecoration: 'none' }}
                            >
                                EXPLORE CIRCUITS
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const SmartContractSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.2fr', gap: isMobile ? '40px' : '80px', alignItems: 'center' }}>
                    <div>
                        <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '16px', display: 'block' }}>Open Source Finality</span>
                        <h2 style={{ fontSize: isMobile ? '2.2rem' : '3rem', fontWeight: 800, marginBottom: '32px', lineHeight: 1.1 }}>Immutable Trust,<br /> Auditable Code.</h2>
                        <p style={{ fontSize: '1.1rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.8, marginBottom: '40px' }}>
                            The Integrity Protocol is powered by the <code>IntegrityRegistry.sol</code> contract, deployed on Base L2. Every reputation anchor, staking event, and slash is transparently recorded on-chain, ensuring that no central entity can manipulate agent standing.
                        </p>
                        <div style={{ display: 'flex', gap: '20px' }}>
                            <a 
                                href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="btn btn-secondary"
                                style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px' }}
                            >
                                <GitBranch size={18} /> View on GitHub
                            </a>
                            <a 
                                href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="btn btn-outline" 
                                style={{ border: '1px solid rgba(255,255,255,0.1)', color: 'white', textDecoration: 'none' }}
                            >
                                Audit Report (v8.0)
                            </a>
                        </div>
                    </div>
                    <div className="enterprise-card" style={{ padding: 0, background: '#050d18', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden', boxShadow: '0 40px 100px rgba(0,0,0,0.4)' }}>
                        <div style={{ padding: '16px 24px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flexShrink: 0 }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ff5f56' }} />
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ffbd2e' }} />
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#27c93f' }} />
                                </div>
                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700, marginLeft: '12px' }}>contracts/IntegrityRegistry.sol</span>
                            </div>
                            <Copy size={14} style={{ color: 'rgba(255,255,255,0.3)' }} />
                        </div>
                        <pre style={{ padding: '32px', margin: 0, overflowX: 'auto', fontSize: '0.85rem', lineHeight: 1.6, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
                            <code style={{ color: '#c9a84c' }}>contract</code> IntegrityRegistry <code style={{ color: '#c9a84c' }}>is</code> Initializable, AccessControl {'{\n'}
                            {'  '} <code style={{ color: '#c9a84c' }}>struct</code> <code style={{ color: '#60a5fa' }}>AgentRecord</code> {'{\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>uint256</code> aisScore;{'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>uint256</code> lastUpdate;{'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>address</code> owner;{'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>bool</code> isSlashed;{'\n'}
                            {'  '}{'}\n\n'}
                            {'  '} <code style={{ color: '#c9a84c' }}>function</code> <code style={{ color: '#10b981' }}>anchorReputation</code>({'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>address</code> _agent,{'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>uint256</code> _score,{'\n'}
                            {'    '} <code style={{ color: '#60a5fa' }}>bytes</code> <code style={{ color: '#c9a84c' }}>calldata</code> _proof{'\n'}
                            {'  '}) <code style={{ color: '#c9a84c' }}>external</code> <code style={{ color: '#c9a84c' }}>onlyOracle</code> {'{\n'}
                            {'    '} <code style={{ color: '#c9a84c' }}>require</code>(_score {'<='} 1000, <code style={{ color: '#f43f5e' }}>"Invalid AIS"</code>);{'\n'}
                            {'    '} _records[_agent].aisScore = _score;{'\n'}
                            {'    '} <code style={{ color: '#c9a84c' }}>emit</code> <code style={{ color: '#10b981' }}>ReputationAnchored</code>(_agent, _score);{'\n'}
                            {'  '}{'}\n'}
                            {'}'}
                        </pre>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const AdvancedFeatures = () => {
    return (
        <>
            <IdentityCeilingsSection />
            <ZeroKnowledgeSection />
            <SmartContractSection />
        </>
    );
};
