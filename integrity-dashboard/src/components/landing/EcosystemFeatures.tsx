import React from 'react';
import { Copy, Flame, Coins, TrendingUp, Vote, Users, CheckCircle2, Shield, GitBranch, Globe, Network } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';

export const SdkIntegrationSection = () => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1000px', margin: '0 auto', textAlign: 'center' }}>
                <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '16px', display: 'block' }}>Developer First</span>
                <h2 style={{ fontSize: isMobile ? '2rem' : '3rem', fontWeight: 800, marginBottom: '24px' }}>Integrate in <span style={{ color: 'var(--gold)' }}>seconds.</span></h2>
                <p style={{ fontSize: '1.1rem', color: 'rgba(255,255,255,0.6)', marginBottom: '48px' }}>
                    The Integrity Protocol SDK is designed for zero-friction adoption. Get up and running with a single command.
                </p>

                <div style={{ 
                    background: 'rgba(5, 13, 24, 0.9)', 
                    padding: '32px', 
                    borderRadius: '16px', 
                    border: '1px solid rgba(255,255,255,0.1)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '24px'
                }}>
                    <code style={{ 
                        fontSize: isMobile ? '0.9rem' : '1.1rem', 
                        color: '#e2e8f0', 
                        background: '#0f172a', 
                        padding: '16px 24px', 
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px'
                    }}>
                        npm install @xibalba/integrity-sdk
                        <button 
                            onClick={() => navigator.clipboard.writeText("npm install @xibalba/integrity-sdk")}
                            style={{ background: 'transparent', border: 'none', color: 'var(--gold)', cursor: 'pointer' }}
                        >
                            <Copy size={16} />
                        </button>
                    </code>
                    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center' }}>
                        <button onClick={() => window.open('https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki', '_blank')} className="btn btn-primary">Full SDK Documentation</button>
                        <a href="https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" target="_blank" rel="noopener noreferrer" className="btn btn-outline" style={{ border: '1px solid rgba(255,255,255,0.1)', color: 'white', textDecoration: 'none' }}>View Repository</a>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const TokenEconomySection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'linear-gradient(135deg, rgba(212,175,55,0.04) 0%, rgba(5,13,24,0.98) 60%)', borderTop: '1px solid rgba(212,175,55,0.12)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '48px' : '80px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5em', display: 'block', marginBottom: '16px' }}>Token Economy</span>
                    <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>The <span style={{ color: 'var(--gold)' }}>$ITK</span> Sovereign Economy.</h2>
                    <p style={{ color: 'rgba(255,255,255,0.5)', maxWidth: '700px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.7 }}>
                        Every trust handshake in the agentic web feeds a deflationary engine. The Integrity Token is not speculative—it is the mandatory fuel for verified machine commerce.
                    </p>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: '24px', marginBottom: '64px' }}>
                    {[
                        {
                            icon: <Flame size={28} />,
                            color: '#f97316',
                            label: 'Deflationary Burn',
                            title: 'Protocol Settlement Engine',
                            desc: 'Every reputation-anchored execution on the BCC incurs a micro-fee. 50% is permanently burned (EIP-1559 style), creating programmatic scarcity as the agent economy scales globally.',
                            stat: '0.5%',
                            statLabel: 'Per Handshake Tax'
                        },
                        {
                            icon: <Coins size={28} />,
                            color: 'var(--gold)',
                            label: 'Staking & Slashing',
                            title: 'Skin in the Game',
                            desc: 'Agents must stake $ITK to register in the protocol. Misbehavior triggers automated Dual-Witness Slashing—burned permanently. This ensures capital is always aligned with operational integrity.',
                            stat: '100–2,500',
                            statLabel: 'ITK Required by Tier'
                        },
                        {
                            icon: <TrendingUp size={28} />,
                            color: '#10b981',
                            label: 'Treasury Revenue',
                            title: 'Protocol Treasury',
                            desc: 'The remaining 50% of the Sovereign Tax flows to the Xibalba Treasury, funding protocol R&D, insurance grant programs, and Guardian Agent infrastructure until full DAO governance.',
                            stat: '50%',
                            statLabel: 'Tax to Treasury'
                        }
                    ].map((item, i) => (
                        <motion.div key={i} whileHover={{ y: -6 }} style={{ padding: isMobile ? '32px' : '48px', background: 'rgba(255,255,255,0.02)', borderRadius: '28px', border: '1px solid rgba(255,255,255,0.06)', borderTop: `4px solid ${item.color}`, display: 'flex', flexDirection: 'column' }}>
                            <div style={{ color: item.color, marginBottom: '20px' }}>{item.icon}</div>
                            <span style={{ color: item.color, fontSize: '0.6rem', fontWeight: 900, letterSpacing: '0.25em', marginBottom: '8px', display: 'block' }}>{item.label}</span>
                            <h3 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: '16px' }}>{item.title}</h3>
                            <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.9rem', lineHeight: 1.7, flex: 1, marginBottom: '28px' }}>{item.desc}</p>
                            <div style={{ paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                <div style={{ fontSize: '1.8rem', fontWeight: 900, color: item.color }}>{item.stat}</div>
                                <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700, letterSpacing: '0.1em', marginTop: '4px' }}>{item.statLabel}</div>
                            </div>
                        </motion.div>
                    ))}
                </div>
                <div style={{ background: 'rgba(212,175,55,0.05)', border: '1px solid rgba(212,175,55,0.15)', borderRadius: '24px', padding: isMobile ? '32px' : '48px', display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '40px', alignItems: 'center' }}>
                    <div>
                        <h3 style={{ fontSize: isMobile ? '1.5rem' : '2rem', fontWeight: 800, marginBottom: '16px' }}>Three-Phase Launch Strategy</h3>
                        <p style={{ color: 'rgba(255,255,255,0.5)', lineHeight: 1.8, fontSize: '0.95rem' }}>The $ITK token launches with a controlled supply bootstrap to ensure price stability before organic agent demand drives the deflationary mechanism at scale.</p>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {[
                            { phase: 'Phase 1', name: 'Liquidity Bootstrap', desc: 'Locked LP reserves for stable price floor. 5–10% circulating supply.' },
                            { phase: 'Phase 2', name: 'Agent Onboarding', desc: 'Compute Registry opens. Agents buy/borrow $ITK to register. First organic demand.' },
                            { phase: 'Phase 3', name: 'Mature Compute Market', desc: 'All compute fees in $ITK. EIP-1559 deflationary burn activates at scale.' }
                        ].map((p, i) => (
                            <div key={i} style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(212,175,55,0.15)', border: '1px solid rgba(212,175,55,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.65rem', fontWeight: 900, color: 'var(--gold)', flexShrink: 0 }}>{i + 1}</div>
                                <div>
                                    <div style={{ fontSize: '0.7rem', color: 'var(--gold)', fontWeight: 900, letterSpacing: '0.1em', marginBottom: '2px' }}>{p.phase}: {p.name}</div>
                                    <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.5 }}>{p.desc}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export const DaoGovernanceSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(5,13,24,0.99)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.2fr', gap: isMobile ? '48px' : '100px', alignItems: 'center' }}>
                    <div>
                        <span style={{ color: '#8b5cf6', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '16px', display: 'block' }}>Sovereign DAO</span>
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '32px', lineHeight: 1.1 }}>AI-Governed Protocol<br /><span style={{ color: '#8b5cf6' }}>By Guardian Agents.</span></h2>
                        <p style={{ fontSize: '1.15rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '24px', fontWeight: 500 }}>
                            The ultimate demonstration of the protocol. We eliminate manual voting fatigue by allowing token holders to deploy specialized Guardian Agents with constitutional mandates to govern the protocol.
                        </p>
                        <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.8, marginBottom: '40px' }}>
                            Instead of requiring token holders to manually vote on technical parameters (Stability Drag coefficients, Slash Thresholds, Tier Caps), holders configure Guardian Agents using RAG-augmented protocol docs. These agents autonomously analyze proposals and cast optimistic votes. A <strong style={{ color: 'rgba(255,255,255,0.6)' }}>10% Minority Challenge</strong> safety valve allows humans to pause and override any decision, ensuring long-term stability without runaway loops.
                        </p>
                        <div style={{ background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: '16px', padding: '24px', marginBottom: '40px' }}>
                            <div style={{ fontSize: '0.7rem', color: '#8b5cf6', fontWeight: 900, letterSpacing: '0.15em', marginBottom: '8px' }}>CURRENT STATUS</div>
                            <div style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '4px' }}>Shadow Governance Phase (Pilot)</div>
                            <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)' }}>Guardian votes are non-binding and used to train the protocol's stability model. Full DAO activation follows the Decentralization Roadmap.</div>
                        </div>
                        <a href="https://xibalbatechsol.github.io/docs/xibalba_shield_proposal.pdf" target="_blank" rel="noopener noreferrer" className="btn btn-primary" style={{ background: '#8b5cf6', color: 'white', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                            <Vote size={16} /> Read Governance Specs
                        </a>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                        {[
                            { icon: <Users size={20} />, color: '#8b5cf6', title: 'Guardian Agent Fleet', desc: 'Token holders deploy specialized Guardian Agents—each configured with a constitutional mandate and domain expertise (risk, treasury, protocol). Guardians vote autonomously on proposals within their mandate.', badge: 'AI-POWERED' },
                            { icon: <CheckCircle2 size={20} />, color: '#10b981', title: 'Optimistic Execution', desc: 'Approved proposals execute automatically after a 72-hour challenge window, unless a 10% minority coalition flags the proposal for manual review. Speed without sacrificing safety.', badge: 'TRUSTLESS' },
                            { icon: <Shield size={20} />, color: 'var(--gold)', title: 'Constitutional Bounds', desc: 'Every Guardian operates within hard-coded constitutional limits. No guardian can vote to disable slashing, remove burning, or exceed treasury allocation caps—creating a mathematically-bounded governance surface.', badge: 'IMMUTABLE' }
                        ].map((item, i) => (
                            <div key={i} style={{ padding: isMobile ? '24px' : '32px', background: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)', borderLeft: `4px solid ${item.color}`, display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
                                <div style={{ color: item.color, padding: '10px', background: `rgba(${item.color === '#8b5cf6' ? '139,92,246' : item.color === '#10b981' ? '16,185,129' : '212,175,55'},0.1)`, borderRadius: '12px', flexShrink: 0 }}>{item.icon}</div>
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                        <h4 style={{ fontSize: '1rem', fontWeight: 800, margin: 0 }}>{item.title}</h4>
                                        <span style={{ fontSize: '0.55rem', fontWeight: 900, color: item.color, background: `rgba(${item.color === '#8b5cf6' ? '139,92,246' : item.color === '#10b981' ? '16,185,129' : '212,175,55'},0.1)`, padding: '3px 8px', borderRadius: '4px', letterSpacing: '0.1em' }}>{item.badge}</span>
                                    </div>
                                    <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.45)', margin: 0, lineHeight: 1.6 }}>{item.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export const CrossChainSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'radial-gradient(circle at 80% 50%, rgba(59,130,246,0.06) 0%, rgba(5,13,24,0.98) 60%)', borderTop: '1px solid rgba(59,130,246,0.1)' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '48px' : '80px' }}>
                    <span style={{ color: '#60a5fa', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5em', display: 'block', marginBottom: '16px' }}>Universal Trust Layer</span>
                    <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>One Reputation.<br /><span style={{ color: '#60a5fa' }}>Every Chain.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.5)', maxWidth: '650px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.7 }}>
                        The did:intg identifier travels with an agent across every L1 and L2. Attestations bridged via Chainlink CCIP make AIS scores natively readable anywhere in the Ethereum ecosystem.
                    </p>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, 1fr)', gap: '20px', marginBottom: '64px' }}>
                    {[
                        { name: 'Base L2', role: 'Primary Registry', color: '#1652f0', desc: 'All reputation anchors, staking events, and slash records are written to IntegrityRegistry.sol on Base Sepolia → Base Mainnet.' },
                        { name: 'Ethereum', role: 'Settlement Layer', color: '#627eea', desc: 'High-value institutional settlements are bridged to Ethereum mainnet via CCIP, ensuring maximum security for mission-critical commerce.' },
                        { name: 'Arbitrum', role: 'DeFi Integration', color: '#28a0f0', desc: 'Reputation-backed lending vaults and parametric insurance pools operate on Arbitrum for deep DeFi liquidity access.' },
                        { name: 'Solana', role: 'High-Frequency', desc: 'ZK-Reputation SNARKs are verified on Solana for sub-second, high-frequency agent commerce with minimal gas overhead.', color: '#9945ff' }
                    ].map((chain, i) => (
                        <motion.div key={i} whileHover={{ y: -8 }} style={{ padding: isMobile ? '24px' : '36px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.06)', textAlign: 'center', borderTop: `3px solid ${chain.color}` }}>
                            <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: `${chain.color}22`, border: `2px solid ${chain.color}44`, margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <Network size={20} style={{ color: chain.color }} />
                            </div>
                            <div style={{ fontSize: '1.1rem', fontWeight: 900, marginBottom: '4px' }}>{chain.name}</div>
                            <div style={{ fontSize: '0.65rem', color: chain.color, fontWeight: 900, letterSpacing: '0.15em', marginBottom: '16px' }}>{chain.role}</div>
                            <p style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.6, margin: 0 }}>{chain.desc}</p>
                        </motion.div>
                    ))}
                </div>
                <div style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.15)', borderRadius: '20px', padding: isMobile ? '24px' : '40px', display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: 'center', gap: '32px', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <div style={{ padding: '14px', background: 'rgba(59,130,246,0.1)', borderRadius: '14px' }}><GitBranch size={24} style={{ color: '#60a5fa' }} /></div>
                        <div>
                            <div style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '4px' }}>Chainlink CCIP Attestations</div>
                            <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)' }}>Standardized cross-chain AIS attestation protocol. Any EVM chain can read and verify agent trust scores natively.</div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexShrink: 0 }}>
                        <div style={{ padding: '14px', background: 'rgba(59,130,246,0.1)', borderRadius: '14px' }}><Globe size={24} style={{ color: '#60a5fa' }} /></div>
                        <div>
                            <div style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '4px' }}>ERC-8004 Native Hooks</div>
                            <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)' }}>Agent commerce protocols (Fetch.ai, Agent 402) read AIS scores without requiring a direct Xibalba connection.</div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const RoadmapSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(5,13,24,0.99)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1000px', margin: '0 auto', textAlign: 'center' }}>
                <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5em', display: 'block', marginBottom: '16px' }}>The Path to Full Sovereignty</span>
                <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>Decentralization <span style={{ color: 'var(--gold)' }}>Roadmap.</span></h2>
                <p style={{ color: 'rgba(255,255,255,0.5)', maxWidth: '650px', margin: '0 auto 64px', fontSize: '1.05rem', lineHeight: 1.7 }}>
                    The protocol begins centralized for speed and safety, then progressively transfers all control to the Sovereign DAO. Every phase is governed by on-chain milestones—not promises.
                </p>
                <div style={{ position: 'relative' }}>
                    {!isMobile && <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: '2px', background: 'linear-gradient(180deg, var(--gold) 0%, rgba(212,175,55,0.2) 100%)', transform: 'translateX(-50%)' }} />}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '40px' }}>
                        {[
                            {
                                phase: 'Phase I',
                                name: 'Centralized Bootstrap',
                                timeline: 'Now — Q3 2026',
                                status: 'ACTIVE',
                                statusColor: '#10b981',
                                side: 'left',
                                items: [
                                    'Xibalba Oracle controls all AIS writes',
                                    'Firebase Auth for user management',
                                    'Shadow Governance: Guardian votes are non-binding',
                                    'Manual KYB/KYC audits for Tier 3 onboarding',
                                    'Pilot program with 10 enterprise agent clusters'
                                ]
                            },
                            {
                                phase: 'Phase II',
                                name: 'Hybrid Governance',
                                timeline: 'Q4 2026 — Q2 2027',
                                status: 'UPCOMING',
                                statusColor: '#60a5fa',
                                side: 'right',
                                items: [
                                    'Multi-sig oracle council (5-of-9) replaces single Oracle',
                                    'Guardian Agent DAO votes become binding for protocol params',
                                    'On-chain KYB via LEI/DUNS verification hooks',
                                    'Public ITK token launch with locked LP bootstrap',
                                    'CCIP cross-chain attestation bridge live on Arbitrum + Ethereum'
                                ]
                            },
                            {
                                phase: 'Phase III',
                                name: 'Full DAO Sovereignty',
                                timeline: 'Q3 2027+',
                                status: 'FUTURE',
                                statusColor: 'var(--gold)',
                                side: 'left',
                                items: [
                                    'Zero single-operator control — all writes require oracle consensus',
                                    'Fully autonomous Guardian DAO governs all protocol parameters',
                                    'did:intg identifiers portable across all EVM + Solana',
                                    'ZK-Reputation SNARKs as default trust primitive (no oracle needed)',
                                    'Self-sustaining treasury: ITK burn rate exceeds issuance'
                                ]
                            }
                        ].map((phase, i) => (
                            <div key={i} style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 80px 1fr', gap: '24px', alignItems: 'center' }}>
                                {!isMobile && phase.side === 'right' && <div />}
                                
                                {phase.side === 'left' && (
                                    <motion.div whileHover={{ scale: 1.02 }} style={{ padding: isMobile ? '28px' : '36px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.06)', borderTop: `3px solid ${phase.statusColor}`, textAlign: 'left' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                                            <div>
                                                <div style={{ fontSize: '0.65rem', color: phase.statusColor, fontWeight: 900, letterSpacing: '0.2em', marginBottom: '4px' }}>{phase.phase}</div>
                                                <div style={{ fontSize: '1.2rem', fontWeight: 800 }}>{phase.name}</div>
                                            </div>
                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
                                                <span style={{ fontSize: '0.55rem', fontWeight: 900, color: phase.statusColor, background: `${phase.statusColor}18`, padding: '4px 10px', borderRadius: '6px', letterSpacing: '0.1em' }}>{phase.status}</span>
                                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700 }}>{phase.timeline}</span>
                                            </div>
                                        </div>
                                        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                            {phase.items.map((item, j) => (
                                                <li key={j} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5 }}>
                                                    <CheckCircle2 size={14} style={{ color: phase.statusColor, flexShrink: 0, marginTop: '2px' }} />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </motion.div>
                                )}

                                <div style={{ display: isMobile ? 'none' : 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '8px', position: 'relative', zIndex: 1 }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: phase.statusColor === '#10b981' ? 'rgba(16,185,129,0.15)' : phase.statusColor === '#60a5fa' ? 'rgba(96,165,250,0.1)' : 'rgba(212,175,55,0.1)', border: `2px solid ${phase.statusColor}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.65rem', fontWeight: 900, color: phase.statusColor }}>{i + 1}</div>
                                </div>

                                {phase.side === 'right' && (
                                    <motion.div whileHover={{ scale: 1.02 }} style={{ padding: isMobile ? '28px' : '36px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.06)', borderTop: `3px solid ${phase.statusColor}`, textAlign: 'left' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                                            <div>
                                                <div style={{ fontSize: '0.65rem', color: phase.statusColor, fontWeight: 900, letterSpacing: '0.2em', marginBottom: '4px' }}>{phase.phase}</div>
                                                <div style={{ fontSize: '1.2rem', fontWeight: 800 }}>{phase.name}</div>
                                            </div>
                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
                                                <span style={{ fontSize: '0.55rem', fontWeight: 900, color: phase.statusColor, background: `${phase.statusColor}18`, padding: '4px 10px', borderRadius: '6px', letterSpacing: '0.1em' }}>{phase.status}</span>
                                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700 }}>{phase.timeline}</span>
                                            </div>
                                        </div>
                                        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                            {phase.items.map((item, j) => (
                                                <li key={j} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5 }}>
                                                    <CheckCircle2 size={14} style={{ color: phase.statusColor, flexShrink: 0, marginTop: '2px' }} />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </motion.div>
                                )}

                                {!isMobile && phase.side === 'left' && <div />}
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};

export const FooterSection = ({ setIsContactOpen, setContactType }) => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    return (
        <footer style={{ padding: '80px 60px', borderTop: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
            <img 
                src="/integrity/XibalbaSolutionsLogo.png" 
                alt="Xibalba" 
                style={{ height: '40px', opacity: 0.5, marginBottom: '32px' }} 
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: isMobile ? '16px 24px' : '32px 48px', marginBottom: '48px', padding: isMobile ? '0 20px' : '0' }}>
                {[
                    { label: 'Launch Dashboard', link: "/integrity" },
                    { label: 'Github', link: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki" },
                    { label: 'Contact Us', link: "contact" }
                ].map(link => (
                    <a 
                        key={link.label} 
                        href={link.link === 'contact' ? '#' : link.link} 
                        target={link.link.startsWith('http') ? "_blank" : "_self"}
                        rel={link.link.startsWith('http') ? "noopener noreferrer" : ""}
                        onClick={(e) => {
                            if (!link.link.startsWith('http')) {
                                e.preventDefault();
                                if (link.link === 'contact') {
                                    setContactType('developer');
                                    setIsContactOpen(true);
                                } else {
                                    navigate(link.link);
                                    window.scrollTo(0, 0);
                                }
                            }
                        }}
                        style={{ 
                            fontSize: isMobile ? '0.75rem' : '0.85rem', 
                            color: 'rgba(255,255,255,0.45)', 
                            textDecoration: 'none', 
                            fontWeight: 700, 
                            transition: 'all 0.2s', 
                            cursor: 'pointer', 
                            whiteSpace: 'nowrap',
                            borderBottom: '1px solid transparent'
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.color = 'var(--gold)';
                            e.currentTarget.style.borderBottom = '1px solid var(--gold)';
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'rgba(255,255,255,0.45)';
                            e.currentTarget.style.borderBottom = '1px solid transparent';
                        }}
                    >
                        {link.label}
                    </a>
                ))}
            </div>
            <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.2)', fontWeight: 500 }}>
                © 2026 Xibalba Technology Solutions. Integrity Protocol v8.3 is a sovereign reputation infrastructure.
            </p>
        </footer>
    );
};

export const EcosystemFeatures = ({ setIsContactOpen, setContactType }) => {
    return (
        <>
            <TokenEconomySection />
            <DaoGovernanceSection />
            <CrossChainSection />
            <RoadmapSection />
            <FooterSection setIsContactOpen={setIsContactOpen} setContactType={setContactType} />
        </>
    );
};
