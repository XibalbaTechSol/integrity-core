import React from 'react';
import { Shield, Activity, Lock, Code, Zap, ShieldCheck, Cpu, Coins, Globe, ArrowRight, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import fidelityImg from '../../assets/fidelity_graph.jpg';
import entropyImg from '../../assets/entropy_graph.jpg';
import solvencyImg from '../../assets/solvency_graph.jpg';
import { useIsMobile } from '../../utils/useIsMobile';

const MathExpr = ({ math, displayMode = false }: { math: string, displayMode?: boolean }) => {
    const html = katex.renderToString(math, { displayMode, throwOnError: false });
    return <span dangerouslySetInnerHTML={{ __html: html }} />;
};

export const AgentPrimitivesSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'var(--navy-deep)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '48px' : '80px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', display: 'block', marginBottom: '16px' }}>The 3 Fundamental Primitives</span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3.5rem', fontWeight: 800, lineHeight: 1.1, marginBottom: '24px', color: 'white' }}>Building the <span style={{ color: 'var(--gold)' }}>Agentic Web.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', maxWidth: '800px', margin: '0 auto', lineHeight: 1.7, fontSize: isMobile ? '0.95rem' : '1.1rem' }}>
                        The Integrity Protocol provides the foundational layer for autonomous systems by establishing three fundamental on-chain primitives: cryptographic reputation, programmable contract ownership, and persistent verified memory.
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: isMobile ? '20px' : '32px' }}>
                    <motion.div whileHover={{ y: -8 }} style={{ padding: '40px', background: 'linear-gradient(145deg, rgba(212,175,55,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(212,175,55,0.2)', borderTop: '4px solid var(--gold)', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: 'var(--gold)', marginBottom: '20px' }}><Shield size={36} /></div>
                        <h4 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: '16px', color: 'white' }}>1. Immutable Reputation</h4>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.95rem', lineHeight: 1.7, margin: 0 }}>
                            Real-time telemetry evaluates agent behavior to compute a globally accessible Agent Integrity Score (AIS). Base L2 smart contracts pre-verify this score before execution to ensure trustless accountability.
                        </p>
                    </motion.div>

                    <motion.div whileHover={{ y: -8 }} style={{ padding: '40px', background: 'linear-gradient(145deg, rgba(96,165,250,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(96,165,250,0.2)', borderTop: '4px solid #60a5fa', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: '#60a5fa', marginBottom: '20px' }}><Code size={36} /></div>
                        <h4 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: '16px', color: 'white' }}>2. Agent-Owned Contracts</h4>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.95rem', lineHeight: 1.7, margin: 0 }}>
                            Agents can programmatically deploy, fund, and manage their own smart contracts and SLAs (e.g. DeFi liquidity pools, task escrows) directly through the Sovereign Agent interface.
                        </p>
                    </motion.div>

                    <motion.div whileHover={{ y: -8 }} style={{ padding: '40px', background: 'linear-gradient(145deg, rgba(167,139,250,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(167,139,250,0.2)', borderTop: '4px solid #a78bfa', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: '#a78bfa', marginBottom: '20px' }}><Cpu size={36} /></div>
                        <h4 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: '16px', color: 'white' }}>3. Persistent Memory</h4>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.95rem', lineHeight: 1.7, margin: 0 }}>
                            Agents anchor their local semantic memories (RAG vectors, graphs) cryptographically to the blockchain via a State Anchor, ensuring knowledge untamperability and context continuity across sessions.
                        </p>
                    </motion.div>
                </div>
            </div>
        </section>
    );
};

export const DevQuickstartSection = ({ setContactType, setIsContactOpen }: { setContactType: any, setIsContactOpen: any }) => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'radial-gradient(circle at top, rgba(212, 175, 55, 0.05) 0%, rgba(5,13,24,1) 80%)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.2fr', gap: isMobile ? '60px' : '100px', alignItems: 'center' }}>
                    <div>
                        <span style={{ color: 'var(--gold)', fontSize: '0.7rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '16px', display: 'block' }}>Developer Experience</span>
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>Start building instantly.<br />No hardware DID required.</h2>
                        <p style={{ fontSize: '1.15rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '24px', fontWeight: 500 }}>
                            Enter the agent economy today with our new <strong style={{ color: 'white' }}>Developer API Key</strong> testing mode. 
                        </p>
                        <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.8, marginBottom: '40px' }}>
                            We know that provisioning hardware-backed DIDs can slow down development. That's why we've introduced Developer API Keys. Simply generate a key from the dashboard and immediately start routing telemetry to the BCC. For safety, agents using this bypass are mathematically capped at a Trust Level (AIS) of 300, allowing you to build and test safely before moving to mainnet production.
                        </p>
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                            <button onClick={() => { setContactType('developer'); setIsContactOpen(true); }} className="btn btn-primary" style={{ padding: '16px 32px', fontSize: '1rem', boxShadow: '0 10px 30px rgba(212,175,55,0.2)' }}>
                                Request API Key
                            </button>
                            <a href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" target="_blank" rel="noopener noreferrer" className="btn btn-outline" style={{ padding: '16px 32px', border: '1px solid rgba(255,255,255,0.15)', color: 'white', textDecoration: 'none', fontSize: '1rem' }}>
                                Read the Docs
                            </a>
                        </div>
                    </div>
                    
                    <div style={{ background: 'linear-gradient(145deg, rgba(15,23,42,0.9) 0%, rgba(5,13,24,0.9) 100%)', border: '1px solid rgba(212, 175, 55, 0.2)', borderRadius: '24px', position: 'relative', boxShadow: '0 30px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)', overflow: 'hidden' }}>
                        {/* IDE Header */}
                        <div style={{ padding: '16px 24px', background: 'rgba(0,0,0,0.4)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#f87171', boxShadow: '0 0 10px #f87171' }} />
                                <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 10px #fbbf24' }} />
                                <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#34d399', boxShadow: '0 0 10px #34d399' }} />
                            </div>
                            <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.3)', fontWeight: 600, letterSpacing: '0.1em' }}>agent_runner.ts</span>
                        </div>
                        {/* IDE Body */}
                        <div style={{ padding: '32px', overflowX: 'auto' }}>
                            <pre style={{ margin: 0, color: '#e2e8f0', fontSize: '0.9rem', fontFamily: '"JetBrains Mono", monospace', lineHeight: 1.7 }}>
<code style={{ color: '#c678dd' }}>import</code> {'{'} IntegrityClient {'}'} <code style={{ color: '#c678dd' }}>from</code> <code style={{ color: '#98c379' }}>'@xibalba/integrity-sdk'</code>;

<code style={{ color: '#5c6370', fontStyle: 'italic' }}>// Initialize with your Developer API Key</code>
<code style={{ color: '#c678dd' }}>const</code> client = <code style={{ color: '#c678dd' }}>new</code> <code style={{ color: '#e5c07b' }}>IntegrityClient</code>({'{'}
  apiKey: "process.env.INTEGRITY_API_KEY",
  network: <code style={{ color: '#98c379' }}>'base-sepolia'</code>
{'}'});

<code style={{ color: '#5c6370', fontStyle: 'italic' }}>// Your agent's AIS is capped at 300 during dev</code>
<code style={{ color: '#5c6370', fontStyle: 'italic' }}>// Ask protocol if transaction is safe</code>
<code style={{ color: '#c678dd' }}>const</code> txRequest = <code style={{ color: '#56b6c2' }}>await</code> client.<code style={{ color: '#61afef' }}>proposeTransaction</code>(uniswapSwap);

<code style={{ color: '#c678dd' }}>if</code> (txRequest.isApproved) {'{'}
  <code style={{ color: '#5c6370', fontStyle: 'italic' }}>// Pre-Execution Gated by BCC!</code>
  <code style={{ color: '#56b6c2' }}>await</code> txRequest.<code style={{ color: '#61afef' }}>execute</code>();
{'}'} <code style={{ color: '#c678dd' }}>else</code> {'{'}
  console.<code style={{ color: '#61afef' }}>log</code>(<code style={{ color: '#98c379' }}>'Transaction blocked: Trust Ceiling exceeded'</code>);
{'}'}
                            </pre>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const ProgrammableEscrowsSection = () => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(5, 13, 24, 0.98)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.2fr 1fr', gap: isMobile ? '40px' : '100px', alignItems: 'center' }}>
                    <div>
                        <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '16px', display: 'block' }}>Programmable Agent Escrows</span>
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '32px', lineHeight: 1.1 }}>Programmable Trust.<br /><span style={{ color: 'var(--gold)' }}>On-Chain Enforcement.</span></h2>
                        <p style={{ fontSize: '1.15rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '32px', fontWeight: 500 }}>
                            Raw trust scores are valuable, but on-chain enforcement is definitive. The Integrity Protocol features a no-code engine for deploying reputation-backed smart contracts and SLA escrows.
                        </p>
                        <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.8, marginBottom: '40px' }}>
                            Our No-Code Factory allows developers and enterprises to wrap autonomous agent interactions in cryptographically enforceable contracts on Base L2. Whether ensuring an agent meets rigorous performance SLAs before an API payment is released, or dynamically increasing a DeFi borrowing limit based on real-time BCC telemetry, the Integrity Protocol provides the settlement floor for machine-to-machine commerce.
                        </p>

                        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '24px', marginBottom: '48px' }}>
                            <div className="enterprise-card" style={{ padding: '32px', background: 'rgba(255,255,255,0.01)', borderLeft: '4px solid #10b981' }}>
                                <div style={{ color: '#10b981', marginBottom: '16px' }}><Zap size={24} /></div>
                                <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '8px' }}>SLA Automated Escrows</h4>
                                <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>
                                    Conditionally release ITK task payments only when an agent maintains its AIS score above a defined threshold throughout the execution cycle.
                                </p>
                            </div>
                            <div className="enterprise-card" style={{ padding: '32px', background: 'rgba(255,255,255,0.01)', borderLeft: '4px solid #3b82f6' }}>
                                <div style={{ color: '#3b82f6', marginBottom: '16px' }}><ShieldCheck size={24} /></div>
                                <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '8px' }}>Parametric Insurance</h4>
                                <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>
                                    Deploy binary-outcome vaults that automatically pay out coverage to beneficiaries if an agent's performance entropy triggers a verifiable fault condition.
                                </p>
                            </div>
                            <div className="enterprise-card" style={{ padding: '32px', background: 'rgba(255,255,255,0.01)', borderLeft: '4px solid #a855f7' }}>
                                <div style={{ color: '#a855f7', marginBottom: '16px' }}><Cpu size={24} /></div>
                                <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '8px' }}>Agent-Owned Contracts</h4>
                                <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>
                                    Agents can deploy and natively own their own smart contracts (e.g., DeFi vaults, liquidity pools), programmatically governed by their real-time on-chain trust score.
                                </p>
                            </div>
                        </div>

                        <div style={{ display: 'flex', gap: '20px' }}>
                            <button 
                                onClick={() => navigate('/integrity')}
                                className="btn btn-primary" 
                            >
                                OPEN ESCROWS
                            </button>
                            <a 
                                href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="btn btn-outline" 
                                style={{ border: '1px solid rgba(255,255,255,0.1)', color: 'white', textDecoration: 'none' }}
                            >
                                READ ESCROW SPECS
                            </a>
                        </div>
                    </div>

                    <div className="enterprise-card" style={{ padding: 0, background: '#050d18', border: '1px solid rgba(212, 175, 55, 0.1)', overflow: 'hidden', boxShadow: '0 40px 100px rgba(0,0,0,0.4)', position: 'relative' }}>
                        <div style={{ padding: '16px 24px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <Code size={14} style={{ color: 'var(--gold)' }} />
                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>contracts/NoCodeFactory.sol</span>
                            </div>
                            <div className="badge badge-gold" style={{ fontSize: '0.5rem' }}>EIP-1167 PROXY</div>
                        </div>
                        <pre style={{ padding: '32px', margin: 0, overflowX: 'auto', fontSize: '0.85rem', lineHeight: 1.6, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
                            <code style={{ color: '#c9a84c' }}>function</code> <code style={{ color: '#10b981' }}>deploySLA</code>(<br />
                            {'  '}address _agent,<br />
                            {'  '}uint256 _minAIS,<br />
                            {'  '}uint256 _amount<br />
                            ) <code style={{ color: '#c9a84c' }}>external</code> returns (address) {'{\n'}
                            {'  '} <code style={{ color: 'rgba(255,255,255,0.3)' }}>// Pull real-time reputation from registry</code>{'\n'}
                            {'  '} (uint256 currentAIS, , , ) = registry.getAgent(_agent);{'\n'}
                            {'  '} <code style={{ color: '#c9a84c' }}>require</code>(currentAIS {'>='} _minAIS);{'\n\n'}
                            {'  '} <code style={{ color: 'rgba(255,255,255,0.3)' }}>// Clone pre-audited SLA template</code>{'\n'}
                            {'  '} address proxy = Clones.clone(slaTemplate);{'\n'}
                            {'  '} AISEscrowSLA(proxy).initialize(_agent, _minAIS);{'\n'}
                            {'  '} <code style={{ color: '#c9a84c' }}>emit</code> <code style={{ color: '#10b981' }}>SLADeployed</code>(proxy, _agent);{'\n'}
                            {'  '} <code style={{ color: '#c9a84c' }}>return</code> proxy;{'\n'}
                            {'}'}
                        </pre>
                        <div style={{ padding: '20px 32px', background: 'rgba(212, 175, 55, 0.05)', borderTop: '1px solid rgba(212, 175, 55, 0.1)', display: 'flex', justifyContent: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <div className="status-ping">
                                    <span className="status-ping-inner bg-gold-500"></span>
                                    <span className="status-ping-dot bg-gold-500"></span>
                                </div>
                                <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--gold)', letterSpacing: '0.1em' }}>FACTORY_ORACLE_ACTIVE // BASE_SEPOLIA</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const EconomicUseCasesSection = () => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(5, 13, 24, 0.8)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '40px' : '80px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em' }}>Market Applications</span>
                    <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginTop: '16px' }}>Economic Utility for the <span style={{ color: 'var(--gold)' }}>Agentic Web.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.7)', maxWidth: '900px', margin: '24px auto 0', lineHeight: 1.7, fontSize: '1.15rem', fontWeight: 500 }}>
                        The Integrity Protocol isn't just a score; it's a functional primitive that unlocks multi-billion dollar markets for autonomous systems. By converting mathematical reputation into institutional-grade risk ratings, we enable the first scalable infrastructure for insured agent commerce.
                    </p>
                    <p style={{ color: 'rgba(255,255,255,0.4)', maxWidth: '850px', margin: '24px auto 0', lineHeight: 1.8, fontSize: '1rem' }}>
                        Current decentralized ecosystems lack a bridge between raw performance data and financial responsibility. This gap prevents large-scale capital from flowing into the Agentic Web. Xibalba Solutions provides the actuarial feed required for professional underwriters, lenders, and global trade partners to price the risk of autonomous failure and reward consistently high-performing agents with lower costs of capital and priority market access.
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '32px' }}>
                    {[
                        {
                            title: "Autonomous Insurance",
                            subtitle: "DYNAMIC RISK UNDERWRITING",
                            desc: "Insurance protocols consume AIS feeds via ERC-8004 hooks to provide real-time risk coverage. High-reputation agents (AAA) qualify for negligible premiums, enabling the first insured autonomous treasury systems. This solves the 'lethal trifecta' of prompt injection, model collapse, and unauthorized actions by providing a neutral record for professional liability claims.",
                            icon: <ShieldCheck size={32} />,
                            color: "#10b981",
                            impact: "95% Reduction in Fraud Exposure"
                        },
                        {
                            title: "Reputation Lending",
                            subtitle: "SOFT-COLLATERAL CREDIT",
                            desc: "DeFi lending vaults utilize an agent's verified AIS history as 'soft collateral' to lower traditional over-collateralization requirements. Institutional-grade agents can access deep lines of credit for cross-chain arbitrage and yield farming based on their performance standing, dramatically increasing capital efficiency in a previously anonymous market.",
                            icon: <Coins size={32} />,
                            color: "var(--gold)",
                            impact: "Capital Efficiency Boost: 4.5x"
                        },
                        {
                            title: "Global Agent Commerce",
                            subtitle: "SYBIL-RESISTANT NETWORKS",
                            desc: "Using W3C DIDs and ZK-reputation badges, agents can settle trade agreements across fragmented L1/L2 ecosystems without manual KYC for every deal. Verified identity ensures that counterparties are backed by corporate entities, eliminating the risk of Single-Use Exit Scams (SUES) in permissionless global markets.",
                            icon: <Globe size={32} />,
                            color: "#60a5fa",
                            impact: "Permissionless Trust Anchoring"
                        }
                    ].map((useCase, i) => (
                        <motion.div
                            key={i}
                            whileHover={{ y: -10 }}
                            style={{ 
                                padding: '48px', 
                                background: 'rgba(255,255,255,0.02)', 
                                borderRadius: '32px', 
                                border: '1px solid rgba(255,255,255,0.05)',
                                display: 'flex',
                                flexDirection: 'column',
                                height: '100%'
                            }}
                        >
                            <div style={{ color: useCase.color, marginBottom: isMobile ? '24px' : '32px' }}>
                                {React.cloneElement(useCase.icon as React.ReactElement, { size: isMobile ? 24 : 32 } as any)}
                            </div>
                            <span style={{ color: useCase.color, fontSize: '0.65rem', fontWeight: 900, letterSpacing: '0.25em' }}>{useCase.subtitle}</span>
                            <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, margin: '12px 0 20px' }}>{useCase.title}</h3>
                            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: isMobile ? '0.9rem' : '0.95rem', lineHeight: 1.7, marginBottom: isMobile ? '24px' : '40px', flex: 1 }}>
                                {useCase.desc}
                            </p>
                            <div style={{ paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'rgba(255,255,255,0.3)' }}>PROJECTED IMPACT:</div>
                                <div style={{ fontSize: '0.8rem', fontWeight: 900, color: 'white' }}>{useCase.impact}</div>
                            </div>
                        </motion.div>
                    ))}
                </div>

                <div style={{ marginTop: '80px', textAlign: 'center' }}>
                    <button 
                        onClick={() => window.open('https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki', '_blank')}
                        className="btn btn-outline" 
                        style={{ padding: '16px 40px', fontSize: '0.8rem', fontWeight: 800 }}
                    >
                        EXPLORE MARKET VERTICALS <ArrowRight size={16} style={{ marginLeft: '12px' }} />
                    </button>
                </div>
            </div>
        </section>
    );
};

export const PrivacyArchitectureSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '100px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    style={{ 
                        background: 'rgba(255,255,255,0.03)', 
                        border: '1px solid rgba(255,255,255,0.1)', 
                        borderRadius: '16px', 
                        padding: isMobile ? '32px' : '48px',
                        textAlign: 'left',
                        boxShadow: '0 20px 40px rgba(0,0,0,0.2)'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                        <div style={{ background: 'rgba(212,175,55,0.1)', padding: '12px', borderRadius: '12px' }}>
                            <Shield size={32} color="var(--gold)" />
                        </div>
                        <div>
                            <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '8px', display: 'block' }}>Data Sovereignty</span>
                            <h3 style={{ margin: 0, fontSize: isMobile ? '1.5rem' : '2rem', fontFamily: 'Playfair Display, serif', fontWeight: 600 }}>Dual-Mode Privacy Architecture</h3>
                        </div>
                    </div>
                    <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '1.1rem', marginBottom: '40px', lineHeight: 1.7, maxWidth: '800px' }}>
                        The Integrity Protocol empowers developers with absolute control over their AI telemetry. Choose the exact level of cryptographic data sovereignty required for your specific vertical without sacrificing accountability.
                    </p>
                    
                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '24px' }}>
                        {/* Mode 1 */}
                        <div className="card-transparent-mode">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                                <Eye size={24} color="white" />
                                <strong style={{ fontSize: '1.2rem' }}>Transparent Mode <span style={{ opacity: 0.5, fontWeight: 400, fontSize: '1rem' }}>(Default)</span></strong>
                            </div>
                            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '1rem', lineHeight: 1.7, margin: 0 }}>
                                Full plaintext reasoning traces are transmitted to the Oracle for standard SaaS debugging and rapid AI alignment. Perfect for public or non-sensitive operations where maximum visibility is required.
                            </p>
                        </div>
                        
                        {/* Mode 2 */}
                        <div className="card-zk-mode">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                                <Lock size={24} color="var(--gold)" />
                                <strong style={{ fontSize: '1.2rem', color: 'var(--gold)' }}>Sovereign ZK-Mode <span style={{ opacity: 0.8, fontWeight: 400, fontSize: '1rem' }}>(Enterprise)</span></strong>
                            </div>
                            <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '1rem', lineHeight: 1.7, margin: 0 }}>
                                Traces never leave local hardware. The SDK generates a mathematical Zero-Knowledge Proof (ZK-Proof) to guarantee compliance without exposing sensitive data to the network. Essential for healthcare, finance, and confidential IP.
                            </p>
                        </div>
                    </div>
                </motion.div>
            </div>
        </section>
    );
};

export const AisMathSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'linear-gradient(to bottom, var(--navy-deep), #050d18)', position: 'relative' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: '64px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.7rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em' }}>Agent Integrity Score (AIS)</span>
                    <h2 style={{ fontSize: isMobile ? '2rem' : '3rem', fontWeight: 800, marginTop: '16px', color: 'white' }}>
                        The Mathematics of Trust
                    </h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', maxWidth: '700px', margin: '24px auto', fontSize: '1.1rem', lineHeight: 1.7 }}>
                        Unlike arbitrary rating systems, the AIS acts as an absolute mathematical volume guaranteeing true "all-aroundness". A failure in one dimension collapses the entire score, providing a safety ceiling that professional underwriters demand.
                    </p>
                </div>

                {/* Main Geometric Math Formula */}
                <div style={{ padding: '40px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(212,175,55,0.15)', marginBottom: '40px', textAlign: 'center', boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}>
                    <h3 style={{ fontSize: '1.1rem', color: 'rgba(255,255,255,0.5)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: '24px' }}>GEOMETRIC AGENT VOLUME</h3>
                    <div style={{ fontSize: isMobile ? '1.5rem' : '2.2rem', color: 'var(--gold)', padding: '24px', background: 'rgba(0,0,0,0.4)', borderRadius: '16px' }}>
                        <MathExpr displayMode math="\text{AIS} = 1000 \times (S_f)^{0.4} \times (S_e)^{0.3} \times (S_c)^{0.3}" />
                    </div>
                    <p style={{ fontSize: '0.95rem', color: 'rgba(255,255,255,0.5)', marginTop: '24px', fontStyle: 'italic' }}>
                        Where <MathExpr math="S_f" /> is Fidelity, <MathExpr math="S_e" /> is Entropy, and <MathExpr math="S_c" /> is Economic Solvency. Any score nearing 0 forces the entire AIS to approach 0.
                    </p>
                </div>

                {/* 3 Metric Columns with Math */}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '28px' }}>
                    
                    {/* Fidelity */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(16,185,129,0.03) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(16,185,129,0.2)', overflow: 'hidden', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ width: '100%', height: '230px', backgroundImage: `url(${fidelityImg})`, backgroundSize: 'cover', backgroundPosition: 'center', borderBottom: '1px solid rgba(16,185,129,0.15)', position: 'relative' }}>
                            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(15,23,42,0.9), transparent 60%)' }} />
                        </div>
                        <div style={{ padding: '32px', position: 'relative', marginTop: '-20px' }}>
                            <h4 style={{ color: 'white', fontSize: '1.25rem', fontWeight: 800, marginBottom: '16px' }}>1. Fidelity (<MathExpr math="S_f" />)</h4>
                            <div style={{ fontSize: '1.25rem', color: '#10b981', marginBottom: '20px', padding: '16px', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: '12px', textAlign: 'center', boxShadow: '0 0 20px rgba(16,185,129,0.1)' }}>
                                <MathExpr displayMode math="S_f(x) = \frac{1}{1 + e^{-k(x - x_0)}}" />
                            </div>
                            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem', lineHeight: 1.6, margin: 0 }}>
                                A logistic growth function modeling SLA success over time. Requires sustained positive feedback before unlocking higher limits (k = growth rate).
                            </p>
                        </div>
                    </motion.div>

                    {/* Entropy */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(59,130,246,0.03) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(59,130,246,0.2)', overflow: 'hidden', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ width: '100%', height: '230px', backgroundImage: `url(${entropyImg})`, backgroundSize: 'cover', backgroundPosition: 'center', borderBottom: '1px solid rgba(59,130,246,0.15)', position: 'relative' }}>
                            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(15,23,42,0.9), transparent 60%)' }} />
                        </div>
                        <div style={{ padding: '32px', position: 'relative', marginTop: '-20px' }}>
                            <h4 style={{ color: 'white', fontSize: '1.25rem', fontWeight: 800, marginBottom: '16px' }}>2. Entropy (<MathExpr math="S_e" />)</h4>
                            <div style={{ fontSize: '1.25rem', color: '#3b82f6', marginBottom: '20px', padding: '16px', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '12px', textAlign: 'center', boxShadow: '0 0 20px rgba(59,130,246,0.1)' }}>
                                <MathExpr displayMode math="S_e(H) = e^{-\lambda H}" />
                            </div>
                            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem', lineHeight: 1.6, margin: 0 }}>
                                An exponential decay curve where H is uncertainty/hallucination rate. Strictly penalizes unpredictable agents (λ = severity scalar).
                            </p>
                        </div>
                    </motion.div>

                    {/* Solvency */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(168,85,247,0.03) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(168,85,247,0.2)', overflow: 'hidden', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ width: '100%', height: '230px', backgroundImage: `url(${solvencyImg})`, backgroundSize: 'cover', backgroundPosition: 'center', borderBottom: '1px solid rgba(168,85,247,0.15)', position: 'relative' }}>
                            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(15,23,42,0.9), transparent 60%)' }} />
                        </div>
                        <div style={{ padding: '32px', position: 'relative', marginTop: '-20px' }}>
                            <h4 style={{ color: 'white', fontSize: '1.25rem', fontWeight: 800, marginBottom: '16px' }}>3. Solvency (<MathExpr math="S_c" />)</h4>
                            <div style={{ fontSize: '1.15rem', color: '#a855f7', marginBottom: '20px', padding: '16px', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(168,85,247,0.3)', borderRadius: '12px', textAlign: 'center', boxShadow: '0 0 20px rgba(168,85,247,0.1)' }}>
                                <MathExpr displayMode math="S_c(t) = \frac{\int_{0}^{t} (T_{\text{in}} - T_{\text{out}}) \, dt}{T_{\text{stake}}}" />
                            </div>
                            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem', lineHeight: 1.6, margin: 0 }}>
                                A calculus integral over time of the agent's net token inflows normalized by its staked reserves. Measures sustained economic viability.
                            </p>
                        </div>
                    </motion.div>

                </div>
            </div>
        </section>
    );
};

