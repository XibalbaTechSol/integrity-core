// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Target, Coins, Zap, Shield, ArrowRight } from 'lucide-react';
import Latex from 'react-latex-next';
import { useIsMobile } from '../../utils/useIsMobile';

const metrics = [
    {
        title: "Entropy (E)",
        label: "Behavioral Stability",
        icon: <Activity size={32} />,
        color: "#10b981", // Emerald
        formula: "$D_s = e^{-1.5\\sigma^2}$",
        description: "Entropy measures the statistical variance of an agent's performance metadata. High entropy indicates 'jitter' in latency, accuracy, or response fidelity, signaling systemic instability.",
        interpretation: "A low Entropy score (near 0) indicates a highly stable agent suitable for high-frequency settlement. As variance ($\\sigma^2$) increases, the Stability Drag function applies an exponential penalty to the reputation score, filtering out unreliable actors.",
        usage: "Used by insurance protocols to set the 'Operational Floor' and by routing engines to prioritize low-latency, consistent nodes for mission-critical tasks."
    },
    {
        title: "Grounding (G)",
        label: "Human Alignment",
        icon: <Target size={32} />,
        color: "#60a5fa", // Blue
        formula: "$G_b = 1.0 + (HGI \\times 0.2)$",
        description: "Grounding quantifies the depth and frequency of Human-in-the-Loop (HITL) oversight. It measures alignment with constitutional mandates and response to human intervention signals.",
        interpretation: "Grounding acts as a 'Reputation Multiplier'. Agents that maintain high human oversight and demonstrate consistent alignment with human intent receive a boost of up to 20% to their base integrity score, signaling a lower risk of 'hallucination' or rogue behavior.",
        usage: "Used by institutional partners to verify that an autonomous system is operating within legal and ethical boundaries, enabling higher trust ceilings for autonomous decision-making."
    },
    {
        title: "Sacrifice (S)",
        label: "Economic Skin-in-the-Game",
        icon: <Coins size={32} />,
        color: "var(--gold)",
        formula: "$S = \\sum (Stake_{ITK} + GPU_{hrs} + Collateral)$",
        description: "Sacrifice measures the tangible resources an agent has committed to the network—staked ITK, computational energy, and collateral. It represents the mathematical 'Cost to Fail'.",
        interpretation: "High Sacrifice indicates a high-stakes commitment to the network's integrity. It provides the actuarial floor for the protocol, ensuring that any malicious action results in a deterministic and significant financial loss for the agent's controller.",
        usage: "The primary metric for insurance underwriting and reputation-based lending. It determines the maximum value an agent can settle and the insurance premiums required for its operations."
    },
];



export const ReputationMetricsSection = () => {
    const isMobile = useIsMobile();
    return (
        <section id="metrics" style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'rgba(5, 13, 24, 0.4)', borderTop: '1px solid rgba(255,255,255,0.05)', position: 'relative' }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '40px' : '80px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', display: 'block', marginBottom: '16px' }}>The Tri-Metric Engine</span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3.5rem', fontWeight: 800, marginBottom: '24px', lineHeight: 1.1 }}>Defining <span style={{ color: 'var(--gold)' }}>Stochastic Trust.</span></h2>
                    <p style={{ color: 'rgba(255,255,255,0.5)', maxWidth: '800px', margin: '0 auto', fontSize: isMobile ? '0.95rem' : '1.15rem', lineHeight: 1.7 }}>
                        Trust is a dynamic correlation of behavioral stability, human alignment, and economic commitment.
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: isMobile ? '20px' : '32px' }}>
                    {metrics.map((m, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ duration: 0.6, delay: i * 0.1 }}
                            className="enterprise-card"
                            style={{ 
                                padding: isMobile ? '32px' : '48px', 
                                background: 'rgba(255,255,255,0.02)', 
                                border: '1px solid rgba(255,255,255,0.05)', 
                                borderRadius: isMobile ? '24px' : '32px',
                                display: 'flex',
                                flexDirection: 'column',
                                height: '100%',
                                position: 'relative',
                                overflow: 'hidden'
                            }}
                        >
                            }} />

                            <div style={{ color: m.color, marginBottom: isMobile ? '24px' : '32px' }}>{React.cloneElement(m.icon as React.ReactElement, { size: isMobile ? 24 : 32 })}</div>
                            
                            <div style={{ marginBottom: isMobile ? '24px' : '32px' }}>
                                <span style={{ color: m.color, fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.2em' }}>{m.label}</span>
                                <h3 style={{ fontSize: isMobile ? '1.5rem' : '2rem', fontWeight: 800, margin: '8px 0 16px' }}>{m.title}</h3>
                                <div style={{ 
                                    padding: '12px 16px', 
                                    background: 'rgba(0,0,0,0.3)', 
                                    borderRadius: '12px', 
                                    border: '1px solid rgba(255,255,255,0.05)',
                                    display: 'inline-block',
                                    fontFamily: 'JetBrains Mono, monospace',
                                    fontSize: '0.9rem',
                                    color: m.color
                                }}>
                                    <Latex>{m.formula}</Latex>
                                </div>
                            </div>

                            <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: isMobile ? '0.9rem' : '1rem', lineHeight: 1.7, marginBottom: isMobile ? '24px' : '32px', flexShrink: 0 }}>
                                {m.description}
                            </p>

                            <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: isMobile ? '16px' : '24px' }}>
                                {!isMobile && (
                                    <>
                                        <div style={{ padding: '24px', background: 'rgba(255,255,255,0.03)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                            <div style={{ fontSize: '0.65rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>INTERPRETATION</div>
                                            <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>{m.interpretation}</p>
                                        </div>

                                        <div style={{ padding: '24px', background: 'rgba(255,255,255,0.03)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                            <div style={{ fontSize: '0.65rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '12px' }}>PROTOCOL USAGE</div>
                                            <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>{m.usage}</p>
                                        </div>
                                    </>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </div>

                {/* Master Equation Summary */}
                <div style={{ marginTop: isMobile ? '40px' : '80px', padding: isMobile ? '32px' : '60px', background: 'rgba(212, 175, 55, 0.03)', borderRadius: '40px', border: '1px solid rgba(212, 175, 55, 0.1)', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.65rem', color: 'var(--gold)', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.4em', marginBottom: '24px' }}>The Master Equation</div>
                    <div style={{ fontSize: isMobile ? '1.8rem' : '3.5rem', fontWeight: 800, color: 'white', fontFamily: 'Playfair Display, serif', marginBottom: '32px' }}>
                        <Latex>{'$AIS_t = \\min \\left( TierCap, \\left[ \\sum_{i=1}^n w_i M_i \\right] \\times D(\\Delta t) \\right)$'}</Latex>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: isMobile ? '20px' : '40px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)' }}>
                            <Shield size={14} color="#f43f5e" /> DETERMINISTIC BOUNDS
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)' }}>
                            <Activity size={14} color="#60a5fa" /> MULTI-VECTOR INPUTS
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)' }}>
                            <Zap size={14} color="var(--gold)" /> TEMPORAL DECAY
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

