import React from 'react';
import { Shield, Activity, Lock, Code, Zap, ShieldCheck, Cpu, Coins, Globe, ArrowRight, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import katex from 'katex';
import 'katex/dist/katex.min.css';

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
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', display: 'block', marginBottom: '16px' }}>The 4 Foundational Primitives</span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3.5rem', fontWeight: 800, lineHeight: 1.1, marginBottom: '24px', color: 'white' }}>Four questions every counterparty must answer before <span style={{ color: 'var(--gold)' }}>delegating anything of value.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', maxWidth: '850px', margin: '0 auto', lineHeight: 1.7, fontSize: isMobile ? '0.95rem' : '1.1rem' }}>
                        The Integrity Protocol rests on four foundational primitives — each answering one question a counterparty must resolve. The order is a progression: each presupposes the one above it.
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, 1fr)', gap: isMobile ? '20px' : '24px' }}>
                    <motion.div whileHover={{ y: -8 }} style={{ padding: '32px 28px', background: 'linear-gradient(145deg, rgba(167,139,250,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(167,139,250,0.2)', borderTop: '4px solid #a78bfa', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: '#a78bfa', marginBottom: '16px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Continuity</div>
                        <div style={{ color: '#a78bfa', marginBottom: '20px' }}><Cpu size={32} /></div>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '10px', color: 'white' }}>1. Persistent Memory</h4>
                        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', fontStyle: 'italic', marginBottom: '12px' }}>Is this the same agent over time?</p>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', lineHeight: 1.7, margin: 0 }}>
                            Every agent's Trust Vault is Merkle-anchored on its own <code style={{ color: '#a78bfa', fontSize: '0.8rem' }}>StateAnchor</code>. Without continuity there is no subject for anything else to attach to — a stateless function invoked repeatedly has no score it can itself produce.
                        </p>
                    </motion.div>

                    <motion.div whileHover={{ y: -8 }} style={{ padding: '32px 28px', background: 'linear-gradient(145deg, rgba(96,165,250,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(96,165,250,0.2)', borderTop: '4px solid #60a5fa', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: '#60a5fa', marginBottom: '16px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Residual Control</div>
                        <div style={{ color: '#60a5fa', marginBottom: '20px' }}><Code size={32} /></div>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '10px', color: 'white' }}>2. Agent-Owned Contracts</h4>
                        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', fontStyle: 'italic', marginBottom: '12px' }}>Can it act, and can it lose?</p>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', lineHeight: 1.7, margin: 0 }}>
                            The agent's own key deploys <code style={{ color: '#60a5fa', fontSize: '0.8rem' }}>SovereignAgent</code> + 7 primitive contracts. Ownership and bonded stake are the same primitive from two sides — control that costs nothing to abuse is no control at all.
                        </p>
                    </motion.div>

                    <motion.div whileHover={{ y: -8 }} style={{ padding: '32px 28px', background: 'linear-gradient(145deg, rgba(251,191,36,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(251,191,36,0.2)', borderTop: '4px solid #fbbf24', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: '#fbbf24', marginBottom: '16px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Delegated Permission</div>
                        <div style={{ color: '#fbbf24', marginBottom: '20px' }}><Shield size={32} /></div>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '10px', color: 'white' }}>3. Authority</h4>
                        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', fontStyle: 'italic', marginBottom: '12px' }}>May it act, and for whom?</p>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', lineHeight: 1.7, margin: 0 }}>
                            An agent acts under a signed delegation from a principal within a scope it cannot widen. Non-authorship is the defining property — an agent cannot mint its own delegation, just as it cannot write its own reputation score.
                        </p>
                    </motion.div>

                    <motion.div whileHover={{ y: -8 }} style={{ padding: '32px 28px', background: 'linear-gradient(145deg, rgba(212,175,55,0.04) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(212,175,55,0.2)', borderTop: '4px solid var(--gold)', borderRadius: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.3)', backdropFilter: 'blur(10px)' }}>
                        <div style={{ color: 'var(--gold)', marginBottom: '16px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Non-Forgeable Standing</div>
                        <div style={{ color: 'var(--gold)', marginBottom: '20px' }}><Lock size={32} /></div>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 800, marginBottom: '10px', color: 'white' }}>4. Reputation</h4>
                        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8rem', fontStyle: 'italic', marginBottom: '12px' }}>How has it acted?</p>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', lineHeight: 1.7, margin: 0 }}>
                            BCC captures signed intent <em>before</em> acting; the Oracle re-derives all four AIS components from OTEL spans server-side <em>after</em>. The agent owns <code style={{ color: 'var(--gold)', fontSize: '0.8rem' }}>ReputationRegistry</code> but only <code style={{ color: 'var(--gold)', fontSize: '0.8rem' }}>ORACLE_ROLE</code> can write to it.
                        </p>
                    </motion.div>
                </div>
            </div>
        </section>
    );
};

export const ProtocolCompareSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '100px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: '60px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.7rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '12px', display: 'block' }}>Market Positioning</span>
                    <h2 style={{ fontSize: isMobile ? '2rem' : '3rem', fontWeight: 800, color: 'white' }}>How Xibalba Compares</h2>
                </div>

                <div style={{ overflowX: 'auto', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', padding: '24px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', color: 'white', textAlign: 'left' }}>
                        <thead>
                            <tr style={{ borderBottom: '2px solid rgba(255,255,255,0.15)' }}>
                                <th style={{ padding: '16px' }}>Feature</th>
                                <th style={{ padding: '16px', color: '#94A3B8' }}>Ritual</th>
                                <th style={{ padding: '16px', color: '#94A3B8' }}>Autonolas / Olas</th>
                                <th style={{ padding: '16px', color: '#94A3B8' }}>Fetch.ai</th>
                                <th style={{ padding: '16px', color: 'var(--gold)', fontWeight: 800 }}>Xibalba</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '16px', fontWeight: 600 }}>Pre-execution Intent Gating</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#fbbf24' }}>Partial</td>
                                <td style={{ padding: '16px', color: '#34d399', fontWeight: 800 }}>✓</td>
                            </tr>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '16px', fontWeight: 600 }}>Cryptographic Execution Proofs (ZK)</td>
                                <td style={{ padding: '16px', color: '#34d399' }}>✓</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#34d399', fontWeight: 800 }}>✓</td>
                            </tr>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '16px', fontWeight: 600 }}>On-Chain Smart Contract Settlement</td>
                                <td style={{ padding: '16px', color: '#fbbf24' }}>Partial</td>
                                <td style={{ padding: '16px', color: '#34d399' }}>✓</td>
                                <td style={{ padding: '16px', color: '#34d399' }}>✓</td>
                                <td style={{ padding: '16px', color: '#34d399', fontWeight: 800 }}>✓</td>
                            </tr>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '16px', fontWeight: 600 }}>Agent Reputation Scoring (AIS)</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#fbbf24' }}>Partial</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#34d399', fontWeight: 800 }}>✓</td>
                            </tr>
                            <tr>
                                <td style={{ padding: '16px', fontWeight: 600 }}>Verification Ladder + Score Ceiling</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#f87171' }}>✗</td>
                                <td style={{ padding: '16px', color: '#34d399', fontWeight: 800 }}>✓</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
};


export const CircuitBreakerSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '100px 60px', background: 'rgba(15,23,42,0.8)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                    <span style={{ color: '#f87171', fontSize: '0.7rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', display: 'block', marginBottom: '12px' }}>Automated Safety</span>
                    <h2 style={{ fontSize: isMobile ? '2rem' : '3rem', fontWeight: 800, color: 'white' }}>Contract Violation? Instant Circuit Breaking.</h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', maxWidth: '800px', margin: '16px auto 0', lineHeight: 1.7 }}>
                        When an agent attempts a transaction outside its authorized policy, the Behavior Commitment Chain (BCC) middleware kills the action in sub-15ms — before any state change occurs.
                    </p>
                </div>

                <div style={{ background: 'rgba(15,23,42,0.9)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: '20px', padding: '32px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, 1fr)', gap: '16px', marginBottom: '32px' }}>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px', borderLeft: '4px solid #60a5fa' }}>
                            <div style={{ fontSize: '0.8rem', color: '#60a5fa', fontWeight: 700 }}>T+0ms</div>
                            <div style={{ fontSize: '0.9rem', color: 'white', marginTop: '4px' }}>Agent submits signed transaction commitment</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px', borderLeft: '4px solid #60a5fa' }}>
                            <div style={{ fontSize: '0.8rem', color: '#60a5fa', fontWeight: 700 }}>T+2ms</div>
                            <div style={{ fontSize: '0.9rem', color: 'white', marginTop: '4px' }}>BCC middleware intercepts — TTL + AIS gates pass</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px', borderLeft: '4px solid #fbbf24' }}>
                            <div style={{ fontSize: '0.8rem', color: '#fbbf24', fontWeight: 700 }}>T+5ms</div>
                            <div style={{ fontSize: '0.9rem', color: 'white', marginTop: '4px' }}>Intent hash verification — Parameter drift detected</div>
                        </div>
                        <div style={{ background: 'rgba(248,113,113,0.1)', padding: '16px', borderRadius: '12px', borderLeft: '4px solid #f87171' }}>
                            <div style={{ fontSize: '0.8rem', color: '#f87171', fontWeight: 700 }}>T+8ms (BLOCKED)</div>
                            <div style={{ fontSize: '0.9rem', color: 'white', marginTop: '4px' }}>⛔ Circuit breaker fires — transaction killed</div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

export const ArchitectureDeepDiveSection = () => {
    const isMobile = useIsMobile();
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '100px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: '60px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.7rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '12px', display: 'block' }}>Under The Hood</span>
                    <h2 style={{ fontSize: isMobile ? '2rem' : '3rem', fontWeight: 800, color: 'white' }}>Protocol Architecture</h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)', maxWidth: '750px', margin: '16px auto 0' }}>The Integrity Protocol is a 5-node validation lifecycle that bridges stochastic LLM reasoning with deterministic on-chain finality.</p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    {[
                        { num: '01', title: 'On-Chain Settlement (Base L2)', desc: 'SovereignAgent.sol, StateAnchor.sol, ReputationRegistry.sol — 7 EIP-1167 primitive contracts per agent. Two are direct-deployed by the agent\'s own key, proving self-sovereign ownership on-chain. Five are cheap minimal proxies. All anchored to Base L2.', tags: ['Base L2', 'Solidity', 'EIP-1167'] },
                        { num: '02', title: 'Verification Ladder (Live: Tier 1→2)', desc: 'Software keypairs (did:intg:<pubkey>) gate score ceilings. Tier 1 Sovereign: 600 AIS max. Tier 2 Linked (GitHub .well-known proof, unattended): 850 AIS max — proven live, effective AIS lifted 600→679 with ZK boost now worthwhile again. Tier 3 Institutional (TEE attestation): 1000 max.', tags: ['W3C DID', 'GitHub Proof', 'DNS TXT'] },
                        { num: '03', title: 'Behavioral Commitment Chain (BCC)', desc: 'Pre-execution interceptor running sub-15ms. Agents commit an intent hash before acting; OPA rego policies evaluate TTL, SHA-256 drift detection, and domain-gated minimums. Clinical actions (EMR_WRITE, DISPENSE_MEDICATION) require Tier 2+ — enforced, not advisory.', tags: ['FastAPI', 'OPA Rego', 'SHA-256'] },
                        { num: '04', title: 'ZK-ML Execution Proofs (Barretenberg)', desc: 'Aztec Noir circuits with UltraPlonk + Barretenberg backend. A verified real proof grants a 1.15× AIS multiplier (ZK_boost). Without Tier 2+, the boost is entirely absorbed by the score ceiling — now meaningful again post-ladder-climb.', tags: ['Aztec Noir', 'UltraPlonk', 'Barretenberg'] },
                        { num: '05', title: 'Oracle: Server-Side AIS Engine', desc: 'The Oracle re-derives all four components from raw OTEL spans, overriding client-asserted values — a client cannot inflate its own score. Formula: AIS = (Sₑ^0.30 · Sᵍ^0.30 · Sₛ^0.20 · Sᶜ^0.20) · ZK_boost. AIS_final = min(computed, tier_ceiling). One canonical implementation in scoring-core; all other packages read it via GET /v1/agent/{id}/ais.', tags: ['Rust / Axum', 'Scoring Core', 'PostgreSQL'] }
                    ].map((step) => (
                        <div key={step.num} style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', padding: '24px', display: 'flex', gap: '24px', alignItems: 'flex-start', flexDirection: isMobile ? 'column' : 'row' }}>
                            <div style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--gold)', minWidth: '50px' }}>{step.num}</div>
                            <div style={{ flex: 1 }}>
                                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'white', marginBottom: '8px' }}>{step.title}</h3>
                                <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.95rem', lineHeight: 1.6, margin: '0 0 12px' }}>{step.desc}</p>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                    {step.tags.map(t => (
                                        <span key={t} style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', color: 'var(--gold)' }}>{t}</span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}
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
                        <h2 style={{ fontSize: isMobile ? '2.5rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>Start building instantly.<br />No mainnet credentials required.</h2>
                        <p style={{ fontSize: '1.15rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.8, marginBottom: '24px', fontWeight: 500 }}>
                            Enter the agent economy today with a <strong style={{ color: 'white' }}>Developer API Key</strong> — provisioned in seconds, no blockchain wallet required.
                        </p>
                        <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.4)', lineHeight: 1.8, marginBottom: '40px' }}>
                            Developer API Keys are Verification Ladder Tier 0 (testnet convenience tier, AIS ceiling 300). They route real telemetry to the BCC and score your agent against the live Oracle so you can build, measure, and iterate before climbing the Verification Ladder — GitHub .well-known proof (Tier 1→2, ceiling 850) or TEE attestation (Tier 3, ceiling 1000) — for production deployment.
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
                        The Oracle re-derives all four AIS components server-side from raw OTEL spans — a client cannot inflate its own score. A failure in any single dimension collapses the entire geometric volume. Score ceilings are tier-enforced: Tier 1 ≤ 600, Tier 2 ≤ 850, Tier 3 ≤ 1000.
                    </p>
                </div>

                {/* Main Geometric Math Formula */}
                <div style={{ padding: '40px', background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(212,175,55,0.15)', marginBottom: '40px', textAlign: 'center', boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}>
                    <h3 style={{ fontSize: '1.1rem', color: 'rgba(255,255,255,0.5)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: '24px' }}>CANONICAL AIS FORMULA (scoring-core)</h3>
                    <div style={{ fontSize: isMobile ? '1.3rem' : '1.8rem', color: 'var(--gold)', padding: '24px', background: 'rgba(0,0,0,0.4)', borderRadius: '16px' }}>
                        <MathExpr displayMode math="\text{AIS} = (S_e^{0.30} \cdot S_g^{0.30} \cdot S_s^{0.20} \cdot S_c^{0.20}) \cdot \text{ZK\_boost}" />
                    </div>
                    <div style={{ marginTop: '24px', display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'center' }}>
                        {[
                            { var: 'Sₑ', label: 'Entropy', weight: '×0.30', color: '#10b981' },
                            { var: 'Sᵍ', label: 'Grounding', weight: '×0.30', color: '#3b82f6' },
                            { var: 'Sₛ', label: 'Sacrifice', weight: '×0.20', color: '#f59e0b' },
                            { var: 'Sᶜ', label: 'Compliance', weight: '×0.20', color: '#a855f7' },
                            { var: 'ZK_boost', label: '1.15× if proof', weight: 'multiplier', color: '#34d399' },
                        ].map(item => (
                            <div key={item.var} style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.04)', border: `1px solid ${item.color}33`, borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ color: item.color, fontWeight: 800, fontFamily: 'monospace' }}>{item.var}</span>
                                <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem' }}>{item.label}</span>
                                <span style={{ color: item.color, fontSize: '0.75rem', fontWeight: 700 }}>{item.weight}</span>
                            </div>
                        ))}
                    </div>
                    <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.35)', marginTop: '20px', fontStyle: 'italic' }}>
                        AIS_final = min(computed, tier_ceiling) — enforced in <code style={{ color: 'rgba(255,255,255,0.5)' }}>AisEngine::score_with_tier</code>
                    </p>
                </div>

                {/* 4 Metric Columns */}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, 1fr)', gap: '20px' }}>
                    
                    {/* Entropy */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(16,185,129,0.04) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(16,185,129,0.2)', padding: '28px', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ color: '#10b981', fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>Weight: 0.30</div>
                        <h4 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 800, marginBottom: '12px' }}>Entropy (Sₑ)</h4>
                        <div style={{ color: '#10b981', marginBottom: '16px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: '10px', textAlign: 'center' }}>
                            <MathExpr displayMode math="S_e = e^{-\lambda H}" />
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', lineHeight: 1.6, margin: 0 }}>
                            Exponential decay on hallucination/uncertainty rate H. Strictly penalizes unpredictable agents.
                        </p>
                    </motion.div>

                    {/* Grounding */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(59,130,246,0.04) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(59,130,246,0.2)', padding: '28px', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ color: '#3b82f6', fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>Weight: 0.30</div>
                        <h4 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 800, marginBottom: '12px' }}>Grounding (Sᵍ)</h4>
                        <div style={{ color: '#3b82f6', marginBottom: '16px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(59,130,246,0.25)', borderRadius: '10px', textAlign: 'center' }}>
                            <MathExpr displayMode math="S_g = \frac{1}{1+e^{-k(x-x_0)}}" />
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', lineHeight: 1.6, margin: 0 }}>
                            Logistic growth on citation-to-claim ratio. Rewards source-grounded reasoning; grows only with sustained fidelity.
                        </p>
                    </motion.div>

                    {/* Sacrifice */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(245,158,11,0.04) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(245,158,11,0.2)', padding: '28px', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ color: '#f59e0b', fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>Weight: 0.20</div>
                        <h4 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 800, marginBottom: '12px' }}>Sacrifice (Sₛ)</h4>
                        <div style={{ color: '#f59e0b', marginBottom: '16px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: '10px', textAlign: 'center' }}>
                            <MathExpr displayMode math="S_s = \frac{\text{stake\_slashed}}{\text{max\_possible\_slash}}" />
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', lineHeight: 1.6, margin: 0 }}>
                            Measures bonded $ITK at risk as a fraction of max slashable stake. Ownership without stake is control that costs nothing to abuse.
                        </p>
                    </motion.div>

                    {/* Compliance */}
                    <motion.div whileHover={{ y: -6 }} style={{ background: 'linear-gradient(180deg, rgba(168,85,247,0.04) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: '20px', border: '1px solid rgba(168,85,247,0.2)', padding: '28px', boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                        <div style={{ color: '#a855f7', fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>Weight: 0.20</div>
                        <h4 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 800, marginBottom: '12px' }}>Compliance (Sᶜ)</h4>
                        <div style={{ color: '#a855f7', marginBottom: '16px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(168,85,247,0.25)', borderRadius: '10px', textAlign: 'center' }}>
                            <MathExpr displayMode math="S_c = \frac{\text{BCC\_approved}}{\text{BCC\_total}}" />
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', lineHeight: 1.6, margin: 0 }}>
                            Ratio of BCC-approved actions to total attempted. OPA rego policies enforce per-domain minimums; clinical-intent types require Tier 2+.
                        </p>
                    </motion.div>

                </div>
            </div>
        </section>
    );
};

