// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { 
    Cpu, Radio, BarChart3, Lock, Globe, ShieldCheck, 
    Landmark, FileCheck, ArrowDown, Fingerprint, Layers,
    ExternalLink
} from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';

const getSteps = (isMobile: boolean) => [
    {
        phase: "PHASE 1",
        title: "Agent Registration & Identity Binding",
        icon: <Fingerprint size={28} />,
        color: "#60a5fa",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ? 
            "Agents register unique Ethereum addresses, initiating the creation of W3C-compliant DIDs that act as permanent, self-sovereign digital anchors." :
            "Every autonomous agent begins by registering a unique Ethereum address on the Integrity Protocol. This process initiates the creation of a W3C-compliant Decentralized Identifier (DID) using the did:intg method, which acts as the agent's permanent, self-sovereign digital anchor.",
        technical: [
            "Agent submits Ethereum address + alias via /v1/agent/register",
            "PostgreSQL Trust Vault creates AgentRecord with owner_uid binding",
            "W3C Decentralized Identifier (DID) Document auto-generated: did:intg:<eth_address>",
            "Initial Agent Integrity Score (AIS) set to 850 with Tier 1 (Sovereign) ceiling of 600"
        ],
        endpoints: ["POST /v1/agent/register", "GET /did/{agent_address}"]
    },
    {
        phase: "PHASE 2",
        title: "Telemetry Ingestion & SDK Interception",
        icon: <Radio size={28} />,
        color: "var(--gold)",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "The Xibalba SDK intercepts performance data from AI frameworks like OpenAI and LangChain, capturing metadata without exposing sensitive prompts." :
            "The Xibalba Software Development Kit (SDK) acts as a high-fidelity interceptor, capturing granular performance data at the point of execution. By wrapping core AI frameworks like OpenAI and LangChain, the SDK captures metadata from every inference call, providing the raw material for the Tri-Metric Scoring Engine.",
        technical: [
            "OpenAI/LangChain SDK interceptors capture metadata per-call",
            "Telemetry batched via /v1/telemetry/batch endpoint",
            "Each event records: latency_ms, accuracy, tokens_in/out, was_intervened",
            "Human-in-the-Loop (HITL) signals feed the Grounding metric"
        ],
        endpoints: ["POST /v1/telemetry/batch", "POST /v1/transactions/report"]
    },
    {
        phase: "PHASE 3",
        title: "Tri-Metric Scoring Engine",
        icon: <BarChart3 size={28} />,
        color: "#10b981",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "Raw telemetry is processed by the Tri-Metric Engine—evaluating behavioral stability (Entropy), human alignment (Grounding), and economic commitment (Sacrifice)." :
            "Raw telemetry is processed by the Tri-Metric Scoring Engine—a proprietary multiplicative correlation model designed to calculate stochastic trust. The engine evaluates agents across three orthogonal vectors: Entropy, Grounding, and Sacrifice.",
        technical: [
            "Entropy: σ(latency) × σ(accuracy) — lower variance = higher score",
            "Grounding: Human-in-the-Loop intervention depth × oversight frequency × fidelity",
            "Sacrifice: staked_ratio × gpu_hours × collateral_locked",
            "Agent Integrity Score (AIS) = f(Entropy, Grounding, Sacrifice) × TierCeiling × DecayFunction"
        ],
        formula: "AIS(t) = min(TierCap, Σ[wₑE(t) + w_gG(t) + w_sS(t)] × D(Δt))",
        endpoints: ["Internal: TriMetricScoringEngine.calculate_ais()"]
    },
    {
        phase: "PHASE 4",
        title: "Zero-Knowledge Reputation Proof Generation",
        icon: <Lock size={28} />,
        color: "#a78bfa",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "Noir-designed ZK circuits generate cryptographic reputation badges, proving an agent meets AIS thresholds without exposing underlying data." :
            "To resolve the paradox of transparency, the protocol utilizes Zero-Knowledge (ZK) circuits designed in Noir to generate cryptographic reputation badges. These proofs allow agents to mathematically demonstrate their Integrity Score meets a specific threshold without revealing underlying telemetry data.",
        technical: [
            "Noir circuit verifies: 0 ≤ AIS ≤ TierCeiling",
            "Proof includes: commitment hash of telemetry batch + scoring weights",
            "Recursive proof composition for multi-epoch reputation windows",
            "Verifier deployed as Solidity contract on Base Layer 2 (L2)"
        ],
        endpoints: ["Internal: ZKProofGenerator.generate_reputation_proof()"]
    },
    {
        phase: "PHASE 5",
        title: "Dual-Witness Oracle Consensus",
        icon: <Globe size={28} />,
        color: "#f59e0b",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "A Dual-Witness model ensures decentralized audit integrity by comparing telemetry commitments from both performing agents and consuming counterparties." :
            "The protocol employs a decentralized Dual-Witness model to eliminate single points of failure. Both the performing agent and the consuming counterparty submit independent, cryptographically signed telemetry commitments for every transaction, maintaining the actuarial integrity of the network.",
        technical: [
            "Provider submits metrics via /v1/transactions/report → integrity_hash",
            "Consumer independently verifies via /v1/transactions/verify",
            "XibalbaDisputeResolver compares: |Δlatency| > 20% OR |Δaccuracy| > 0.15",
            "Dispute resolution: slash penalty_points, reduce AIS, flag for review"
        ],
        endpoints: ["POST /v1/transactions/report", "POST /v1/transactions/verify"]
    },
    {
        phase: "PHASE 6",
        title: "On-Chain Settlement (Base Layer 2)",
        icon: <Layers size={28} />,
        color: "#60a5fa",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "Validated state is anchored to Base L2 for immutable finality. Every event triggers a sovereign protocol tax and burns ITK supply." :
            "The validated reputational state is anchored to the ReputationRegistry smart contract on Base (Ethereum Layer 2). Settlement includes a sovereign protocol tax, with 0.25% of the transaction value burned from the ITK supply and 0.25% routed to the treasury.",
        technical: [
            "anchorReputation(address, uint256, bytes) called by Oracle",
            "0.25% sovereign tax burned from Integrity Token (ITK) supply per transaction",
            "0.25% routed to Xibalba Treasury for protocol sustainability",
            "ERC-8004 hooks enable external smart contract reputation queries"
        ],
        endpoints: ["Contract: ReputationRegistry.anchorReputation()"]
    },
    {
        phase: "PHASE 7",
        title: "Actuarial Risk Classification",
        icon: <Landmark size={28} />,
        color: "#f43f5e",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "Mathematical reputation is converted into actionable actuarial profiles, allowing automated underwriting of agent failure risk." :
            "In the final stage, mathematical reputation is converted into actionable actuarial profiles. Insurance underwriters query the protocol's oracle to generate real-time risk ratings ranging from AAA to D, enabling automated failure risk underwriting.",
        technical: [
            "AAA (Prime): Integrity Score ≥ 850 → 120 basis points premium",
            "AA (Secure): Integrity Score ≥ 750 → 250 basis points premium",
            "BBB (Standard): Integrity Score ≥ 600 → 450 basis points premium",
            "CCC (Subprime): Integrity Score ≥ 400 → 900 bps | D (Toxic): uninsurable"
        ],
        endpoints: ["POST /v1/insurance/quote"]
    },
    {
        phase: "PHASE 8",
        title: "Verifiable Credential Export",
        icon: <FileCheck size={28} />,
        color: "#10b981",
        docLink: "https://github.com/XibalbaTechSol/integrity-master/tree/master/docs/wiki",
        description: isMobile ?
            "Certified reputation is exported as a portable W3C Verifiable Credential, bridged to other networks via Chainlink CCIP." :
            "The agent's certified reputation is exported as a W3C-standard Verifiable Credential. This portable, self-sovereign 'reputation passport' can be bridged across any enterprise system or blockchain using Chainlink CCIP.",
        technical: [
            "Verifiable Credential issued by did:intg:xibalba-oracle-01 (Xibalba Identity Oracle)",
            "credentialSubject embeds: Integrity Score, tier, trust_level, last_audit",
            "JsonWebSignature2020 proof using Oracle's verification key",
            "Chainlink Cross-Chain Interoperability Protocol (CCIP) bridging for multi-chain portability"
        ],
        endpoints: ["GET /vc/ais/{agent_address}"]
    }
];

export const ProtocolArchitecture = () => {
    const isMobile = useIsMobile();
    const steps = getSteps(isMobile);
    return (
        <section style={{ padding: isMobile ? '60px 20px' : '120px 60px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                {/* Section Header */}
                <div style={{ textAlign: 'center', marginBottom: isMobile ? '48px' : '100px' }}>
                    <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.5em', display: 'block', marginBottom: '16px' }}>
                        Technical Architecture
                    </span>
                    <h2 style={{ fontSize: isMobile ? '2.2rem' : '3rem', fontWeight: 800, lineHeight: 1.1, marginBottom: '24px' }}>
                        The Integrity Pipeline:<br />A <span style={{ color: 'var(--gold)' }}>Technical Breakdown.</span>
                    </h2>
                    <p style={{ color: 'rgba(255,255,255,0.4)', maxWidth: '750px', margin: '0 auto', lineHeight: 1.7, fontSize: isMobile ? '0.9rem' : '1.05rem' }}>
                        How we transform ephemeral agent behavior into verifiable reputation.
                    </p>
                </div>

                {/* Step-by-Step Pipeline */}
                <div style={{ position: 'relative' }}>
                    {/* Vertical connecting line */}
                    <div style={{ 
                        position: 'absolute', 
                        left: '31px', 
                        top: '40px', 
                        bottom: '40px', 
                        width: '2px', 
                        background: 'linear-gradient(to bottom, var(--gold), rgba(212, 175, 55, 0.1))',
                        zIndex: 0 
                    }} />

                    {steps.map((step, idx) => (
                        <motion.div
                            key={idx}
                            initial={{ opacity: 0, x: -30 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true, margin: "-50px" }}
                            transition={{ duration: 0.5, delay: idx * 0.05 }}
                            style={{ 
                                display: 'grid', 
                                gridTemplateColumns: '64px 1fr', 
                                gap: '40px', 
                                marginBottom: idx < steps.length - 1 ? '48px' : '0',
                                position: 'relative',
                                zIndex: 1
                            }}
                        >
                            {/* Step Number Node */}
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                <div style={{ 
                                    width: '64px', 
                                    height: '64px', 
                                    borderRadius: '20px', 
                                    background: `rgba(255,255,255,0.03)`,
                                    border: `2px solid ${step.color}30`,
                                    display: 'flex', 
                                    alignItems: 'center', 
                                    justifyContent: 'center',
                                    color: step.color,
                                    boxShadow: `0 0 30px ${step.color}10`,
                                    position: 'relative'
                                }}>
                                    {step.icon}
                                </div>
                            </div>

                            {/* Step Content Card */}
                            <div style={{ 
                                background: 'rgba(255,255,255,0.02)', 
                                border: '1px solid rgba(255,255,255,0.05)', 
                                borderRadius: isMobile ? '20px' : '24px', 
                                padding: isMobile ? '24px' : '40px',
                                transition: 'border-color 0.3s'
                            }}
                                onMouseEnter={(e) => e.currentTarget.style.borderColor = `${step.color}30`}
                                onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)'}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
                                    <a 
                                        href={step.docLink}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ 
                                            fontSize: '0.6rem', 
                                            fontWeight: 900, 
                                            color: step.color, 
                                            letterSpacing: '0.3em',
                                            padding: '4px 12px',
                                            background: `${step.color}10`,
                                            borderRadius: '6px',
                                            textDecoration: 'none',
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            gap: '6px',
                                            transition: 'all 0.2s'
                                        }}
                                        onMouseEnter={(e) => e.currentTarget.style.background = `${step.color}20`}
                                        onMouseLeave={(e) => e.currentTarget.style.background = `${step.color}10`}
                                    >
                                        {step.phase} <ExternalLink size={10} style={{ opacity: 0.5 }} />
                                    </a>
                                </div>
                                
                                <h3 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '16px', lineHeight: 1.2 }}>
                                    {step.title}
                                </h3>
                                
                                <p style={{ 
                                    color: 'rgba(255,255,255,0.5)', 
                                    fontSize: '0.95rem', 
                                    lineHeight: 1.7, 
                                    marginBottom: '28px',
                                    maxWidth: '800px'
                                }}>
                                    {step.description}
                                </p>

                                {/* Technical Details */}
                                <div style={{ 
                                    background: 'rgba(0,0,0,0.3)', 
                                    borderRadius: '16px', 
                                    padding: '24px',
                                    border: '1px solid rgba(255,255,255,0.03)'
                                }}>
                                    <div style={{ 
                                        fontSize: '0.6rem', 
                                        fontWeight: 800, 
                                        color: 'rgba(255,255,255,0.3)', 
                                        textTransform: 'uppercase', 
                                        letterSpacing: '0.2em', 
                                        marginBottom: '16px',
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center'
                                    }}>
                                        <span>IMPLEMENTATION DETAILS</span>
                                        <a 
                                            href={step.docLink}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            style={{ color: 'var(--gold)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '6px', letterSpacing: '0.1em' }}
                                        >
                                            VIEW DOCS <ArrowDown size={10} />
                                        </a>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                        {step.technical.map((detail, i) => (
                                            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                                <div style={{ 
                                                    width: '6px', 
                                                    height: '6px', 
                                                    borderRadius: '50%', 
                                                    background: step.color, 
                                                    marginTop: '7px',
                                                    flexShrink: 0,
                                                    opacity: 0.7
                                                }} />
                                                <span style={{ 
                                                    fontSize: '0.8rem', 
                                                    color: 'rgba(255,255,255,0.6)', 
                                                    lineHeight: 1.5,
                                                    fontFamily: detail.includes('/v1/') || detail.includes('()') || detail.includes('σ(') ? 'JetBrains Mono, monospace' : 'inherit'
                                                }}>
                                                    {detail}
                                                </span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Formula highlight if present */}
                                    {step.formula && (
                                        <div style={{ 
                                            marginTop: '20px', 
                                            padding: '16px 20px', 
                                            background: 'rgba(212, 175, 55, 0.05)', 
                                            borderRadius: '12px',
                                            border: '1px solid rgba(212, 175, 55, 0.15)',
                                            fontFamily: 'JetBrains Mono, monospace',
                                            fontSize: '0.8rem',
                                            color: 'var(--gold)',
                                            letterSpacing: '0.02em'
                                        }}>
                                            {step.formula}
                                        </div>
                                    )}

                                    {/* API Endpoints */}
                                    <div style={{ 
                                        marginTop: '20px', 
                                        display: 'flex', 
                                        flexWrap: 'wrap', 
                                        gap: '8px' 
                                    }}>
                                        {step.endpoints.map((ep, i) => (
                                            <span key={i} style={{ 
                                                fontSize: '0.65rem', 
                                                fontFamily: 'JetBrains Mono, monospace',
                                                padding: '6px 12px', 
                                                background: 'rgba(255,255,255,0.03)',
                                                border: '1px solid rgba(255,255,255,0.06)',
                                                borderRadius: '8px',
                                                color: 'rgba(255,255,255,0.4)',
                                                fontWeight: 600
                                            }}>
                                                {ep}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>

                {/* Summary Stats Bar */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    style={{ 
                        marginTop: isMobile ? '40px' : '80px', 
                        display: 'grid', 
                        gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', 
                        gap: isMobile ? '16px' : '24px' 
                    }}
                >
                    {[
                        { label: "API Endpoints", value: "14+", sub: "RESTful" },
                        { label: "Smart Contracts", value: "4", sub: "Base L2" },
                        { label: "Open Standards", value: "3", sub: "W3C / ERC / VC" },
                        { label: "Latency", value: "<2s", sub: "End-to-End" }
                    ].map((stat, i) => (
                        <div key={i} style={{ 
                            textAlign: 'center', 
                            padding: isMobile ? '20px' : '32px', 
                            background: 'rgba(255,255,255,0.02)', 
                            borderRadius: '20px',
                            border: '1px solid rgba(255,255,255,0.05)'
                        }}>
                            <div style={{ fontSize: isMobile ? '1.5rem' : '2rem', fontWeight: 900, color: 'var(--gold)', marginBottom: '4px' }}>{stat.value}</div>
                            <div style={{ fontSize: isMobile ? '0.7rem' : '0.85rem', fontWeight: 700, marginBottom: '4px' }}>{stat.label}</div>
                            <div style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>{stat.sub}</div>
                        </div>
                    ))}
                </motion.div>
            </div>
        </section>
    );
};
