// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { ShieldAlert, ShieldCheck, TrendingUp, Coins, BarChart3, Lock, Zap, ArrowRight } from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';

export const InvestorVisionSection = () => {
    const isMobile = useIsMobile();
    return (
        <section id="vision" style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'var(--navy-deep)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                {/* Section Header */}
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '48px' : '100px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5em', display: 'block', marginBottom: '16px' }}>Institutional Thesis</span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3.5rem', fontWeight: 800, lineHeight: 1.1, marginBottom: '24px', color: 'white' }}>The Foundation of <br /><span style={{ color: 'var(--gold)' }}>Agentic Trust.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.4)', maxWidth: '750px', margin: '0 auto', lineHeight: 1.7, fontSize: isMobile ? '0.95rem' : '1.1rem' }}>
                        As the autonomous economy scales, the "Trust Gap" represents the single greatest barrier to institutional adoption.
                    </p>
                </div>

                {/* Problem & Solution Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: isMobile ? '24px' : '40px', marginBottom: isMobile ? '48px' : '100px' }}>
                    <motion.div 
                        initial={{ opacity: 0, x: -30 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        className="enterprise-card"
                        style={{ padding: isMobile ? '32px' : '60px', background: 'rgba(244, 63, 94, 0.03)', border: '1px solid rgba(244, 63, 94, 0.1)', borderRadius: isMobile ? '24px' : '40px' }}
                    >
                        <div style={{ color: '#f43f5e', marginBottom: '24px' }}><ShieldAlert size={isMobile ? 32 : 48} /></div>
                        <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, marginBottom: '24px', color: 'white' }}>The Problem:<br />The AI Trust Gap</h3>
                        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: isMobile ? '0.9rem' : '1.1rem', lineHeight: 1.8, margin: 0 }}>
                            {isMobile ? 
                                "Lack of verifiable reputation creates a massive barrier to institutional adoption in the autonomous economy." :
                                "As autonomous agent economies scale, the lack of verifiable reputation creates a massive barrier to institutional adoption. Currently, there is no standardized way to verify if an AI agent is performing grounded, safe, and computationally honest work."
                            }
                        </p>
                    </motion.div>

                    <motion.div 
                        initial={{ opacity: 0, x: 30 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        className="enterprise-card"
                        style={{ padding: isMobile ? '32px' : '60px', background: 'rgba(16, 185, 129, 0.03)', border: '1px solid rgba(16, 185, 129, 0.1)', borderRadius: isMobile ? '24px' : '40px' }}
                    >
                        <div style={{ color: '#10b981', marginBottom: '24px' }}><ShieldCheck size={isMobile ? 32 : 48} /></div>
                        <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, marginBottom: '24px', color: 'white' }}>The Solution:<br />A Reputation Layer</h3>
                        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: isMobile ? '0.9rem' : '1.1rem', lineHeight: 1.8, margin: 0 }}>
                            {isMobile ? 
                                "A cryptographically secure, decentralized trust layer bridging off-chain telemetry with on-chain accountability." :
                                "Integrity Protocol provides a cryptographically secure, decentralized reputation and trust verification layer. By bridging off-chain telemetry with on-chain accountability, we enable a permissionless agentic marketplace."
                            }
                        </p>
                    </motion.div>
                </div>

                {/* Core Value Drivers */}
                <div style={{ marginBottom: '100px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginBottom: '48px' }}>
                        <div style={{ height: '1px', flex: 1, background: 'rgba(255,255,255,0.05)' }} />
                        <span style={{ fontSize: '0.7rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Core Value Drivers</span>
                        <div style={{ height: '1px', flex: 1, background: 'rgba(255,255,255,0.05)' }} />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: isMobile ? '20px' : '32px' }}>
                        {[
                            {
                                title: "Tri-Metric Scoring Engine",
                                desc: "A multi-dimensional algorithm that evaluates agent performance across Entropy, Grounding, and Sacrifice.",
                                icon: <BarChart3 size={24} />,
                                color: "var(--gold)"
                            },
                            {
                                title: "Algorithmic Insurance Oracle",
                                desc: "A first-of-its-kind actuarial service that provides real-time risk tiering (AAA to CCC).",
                                icon: <Zap size={24} />,
                                color: "#60a5fa"
                            },
                            {
                                title: "ZK-Reputation Proofs",
                                desc: "Leveraging Zero-Knowledge circuits to verify an agent's AIS score on-chain.",
                                icon: <Lock size={24} />,
                                color: "#a78bfa"
                            }
                        ].map((driver, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                                style={{ padding: isMobile ? '24px' : '40px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: isMobile ? '20px' : '24px' }}
                            >
                                <div style={{ color: driver.color, marginBottom: '20px' }}>{driver.icon}</div>
                                <h4 style={{ fontSize: isMobile ? '1.1rem' : '1.2rem', fontWeight: 800, marginBottom: '16px', color: 'white' }}>{driver.title}</h4>
                                <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem', lineHeight: 1.6, margin: 0 }}>{driver.desc}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Market & Tokenomics */}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.2fr 1fr', gap: isMobile ? '24px' : '40px', alignItems: 'center' }}>
                    <div style={{ padding: isMobile ? '32px' : '60px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: isMobile ? '24px' : '40px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                            <TrendingUp size={isMobile ? 24 : 32} style={{ color: 'var(--gold)' }} />
                            <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, color: 'white' }}>Market Opportunity</h3>
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: isMobile ? '0.95rem' : '1.1rem', lineHeight: 1.8, marginBottom: '32px' }}>
                            {isMobile ? 
                                "Integrity Protocol acts as the 'Moody's of AI,' providing essential trust infrastructure for autonomous operations." :
                                "The AI agent market is projected to reach multi-billion dollar valuations by 2030. Integrity Protocol positions itself as the 'Moody's of AI,' providing the essential trust infrastructure required for high-value autonomous operations."
                            }
                        </p>
                        <div style={{ display: 'flex', gap: isMobile ? '24px' : '40px' }}>
                            <div>
                                <div style={{ fontSize: isMobile ? '1.4rem' : '2.0rem', fontWeight: 900, color: 'var(--gold)' }}>$XX Billion</div>
                                <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', fontWeight: 800, letterSpacing: '0.1em' }}>PROJECTED TAM</div>
                            </div>
                            <div>
                                <div style={{ fontSize: isMobile ? '1.4rem' : '2.0rem', fontWeight: 900, color: 'var(--gold)' }}>Moody's of AI</div>
                                <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', fontWeight: 800, letterSpacing: '0.1em' }}>POSITIONING</div>
                            </div>
                        </div>
                    </div>

                    <div style={{ padding: isMobile ? '32px' : '60px', background: 'rgba(212, 175, 55, 0.05)', border: '1px solid rgba(212, 175, 55, 0.15)', borderRadius: isMobile ? '24px' : '40px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                            <Coins size={isMobile ? 24 : 32} style={{ color: 'var(--gold)' }} />
                            <h3 style={{ fontSize: isMobile ? '1.4rem' : '1.8rem', fontWeight: 800, color: 'white' }}>$ITK Tokenomics</h3>
                        </div>
                        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: isMobile ? '0.9rem' : '1rem', lineHeight: 1.7, marginBottom: '32px' }}>
                            {isMobile ? 
                                "The $ITK token powers protocol security through deflationary staking and slashing, linking utility directly to demand." :
                                "The $ITK token powers the protocol's security through a deflationary staking and slashing model. High-reputation agents must stake ITK to achieve Tier 3 Institutional status, creating a direct link between protocol utility and token demand."
                            }
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            {[
                                "Deflationary Staking Model",
                                "Tier 3 Collateral Requirements",
                                "Direct Revenue Burning (0.25%)"
                            ].map((text, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)', fontWeight: 700 }}>
                                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--gold)' }} />
                                    {text}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};
