import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Activity, Shield, TrendingUp, ChevronDown, ShieldAlert, Database, Scale, Cpu, Search, Check, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
import { useSettings } from './context/SettingsContext';
import { BlockMath } from 'react-katex';
import 'katex/dist/katex.min.css';

const FAQItem = ({ question, answer }: { question: string, answer: React.ReactNode }) => {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="card" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column' }} onClick={() => setIsOpen(!isOpen)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '1.1rem' }}>{question}</h4>
        <ChevronDown size={20} color="var(--text-secondary)" style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
      </div>
      {isOpen && (
        <div style={{ marginTop: '1rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {answer}
        </div>
      )}
    </div>
  );
};

export default function LandingPage() {
  const { animationsEnabled } = useSettings();

  const fadeInUp = {
    initial: animationsEnabled ? { opacity: 0, y: 30 } : { opacity: 1, y: 0 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "0px" },
    transition: { duration: 0.6 }
  };

  const stagger = {
    initial: animationsEnabled ? { opacity: 0 } : { opacity: 1 },
    whileInView: { opacity: 1 },
    viewport: { once: true },
    transition: { staggerChildren: 0.2, delayChildren: 0.1 }
  };

  const aisFormula = `\\text{AIS} = \\left( S_{\\text{entropy}}^{0.30} \\cdot S_{\\text{grounding}}^{0.30} \\cdot S_{\\text{sacrifice}}^{0.20} \\cdot S_{\\text{compliance}}^{0.20} \\right) \\cdot \\text{ZK}_{\\text{boost}}`;

  return (
    <div style={{ color: 'var(--text-primary)' }}>
      {/* 1. Global Navigation & Header */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.5rem 3rem', background: 'rgba(25, 25, 25, 0.8)', backdropFilter: 'blur(10px)', position: 'sticky', top: 0, zIndex: 100, borderBottom: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <img src="https://xibalbatechsol.github.io/XibalbaSolutionsLogo.png" alt="Xibalba Solutions" style={{ height: '40px' }} />
          <span style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.5px' }}>Integrity Protocol</span>
        </div>
        <div style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
          <a href="#problem" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>The Problem</a>
          <a href="#ais" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>AIS Metrics</a>
          <a href="#verticals" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>Market Verticals</a>
          <a href="#faq" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>FAQ</a>
          <Link to="/wiki" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>Wiki</Link>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
          <a href="https://github.com/xibalbatechsol" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 500 }}>GitHub</a>
          <Link to="/auth" className="button primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.5rem' }}>
            Launch MVP <ArrowRight size={16} />
          </Link>
        </div>
      </header>

      {/* 2. Hero Section: Executive Summary & Value Proposition */}
      <section style={{ textAlign: 'center', padding: '6rem 2rem 8rem 2rem', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'radial-gradient(circle at center, rgba(30, 60, 90, 0.2) 0%, transparent 70%)', zIndex: -1 }} />
        
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition}>
          <img src="https://xibalbatechsol.github.io/XibalbaSolutionsLogo.png" alt="Xibalba Solutions" style={{ height: '120px', marginBottom: '2rem', filter: 'drop-shadow(0 0 20px rgba(0, 150, 255, 0.3))' }} />
          <p style={{ fontSize: '1.1rem', color: 'var(--theme-accent)', fontWeight: 700, letterSpacing: '2px', marginBottom: '1rem', textTransform: 'uppercase' }}>
            The Cryptographic Trust Layer for the Autonomous Economy
          </p>
          <h1 style={{ fontSize: '4.5rem', marginBottom: '1.5rem', fontWeight: 800, lineHeight: 1.1, maxWidth: '1000px', margin: '0 auto 1.5rem auto' }}>
            We don't just monitor AI—<br />we mathematically bind it to liability.
          </h1>
          <p style={{ fontSize: '1.35rem', color: 'var(--text-secondary)', maxWidth: '800px', margin: '0 auto 3rem auto', lineHeight: 1.6 }}>
            The Integrity Protocol is the missing infrastructure for enterprise AI adoption. By utilizing smart contracts, hardware attestations, and Zero-Knowledge proofs, we transform unpredictable black-box agents into highly determinative, insurable economic actors.
          </p>
          <div style={{ display: 'flex', gap: '1.5rem', justifyContent: 'center' }}>
            <Link to="/auth" className="button primary" style={{ padding: '1.25rem 2.5rem', fontSize: '1.1rem', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              Launch MVP Dashboard <ArrowRight size={18} />
            </Link>
            <a href="#problem" className="button" style={{ padding: '1.25rem 2.5rem', fontSize: '1.1rem', textDecoration: 'none' }}>
              Read the Business Plan
            </a>
          </div>
        </motion.div>
      </section>

      {/* 3. The Market Problem: Why This Exists */}
      <section id="problem" style={{ padding: '6rem 3rem', background: 'var(--surface-color)', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
            <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>The Market Problem</h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '800px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.6 }}>
              AI agents are rapidly adopting autonomous capabilities—executing trades, accessing medical records, and writing code—but they fundamentally lack identity, liability, and standardized governance.
            </p>
          </motion.div>

          <motion.div variants={stagger} initial="initial" whileInView="whileInView" viewport={stagger.viewport} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
            <motion.div variants={fadeInUp} className="card" style={{ borderTop: '4px solid #ef4444' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ padding: '0.75rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px', color: '#ef4444' }}>
                  <Zap size={24} />
                </div>
                <h3 style={{ margin: 0 }}>The 9-Second Problem</h3>
              </div>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                Without cryptographic bounds, an autonomous agent can hallucinate and destroy corporate infrastructure or drain financial accounts in less than 9 seconds—long before human intervention can physically react.
              </p>
            </motion.div>

            <motion.div variants={fadeInUp} className="card" style={{ borderTop: '4px solid #f59e0b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ padding: '0.75rem', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '8px', color: '#f59e0b' }}>
                  <Scale size={24} />
                </div>
                <h3 style={{ margin: 0 }}>The Regulatory Void</h3>
              </div>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                Current LLM agents cannot legally sign Business Associate Agreements (BAAs) or comply natively with HIPAA because they lack a verified identity and a deterministic liability structure to hold collateral.
              </p>
            </motion.div>

            <motion.div variants={fadeInUp} className="card" style={{ borderTop: '4px solid #3b82f6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ padding: '0.75rem', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '8px', color: '#3b82f6' }}>
                  <Search size={24} />
                </div>
                <h3 style={{ margin: 0 }}>Black Box Telemetry</h3>
              </div>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                When an agent makes a catastrophic mistake, companies cannot definitively prove *why* the agent took a specific action, making post-incident forensics impossible and rendering the agent entirely uninsurable.
              </p>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* 4. Deep Dive: Agentic Integrity Score (AIS) */}
      <section id="ais" style={{ padding: '6rem 3rem', maxWidth: '1200px', margin: '0 auto' }}>
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>The Mathematics of Trust (AIS)</h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '800px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.6 }}>
            We replace "vibes-based" AI evaluation with hard math and Zero-Knowledge proofs. The Agentic Integrity Score (AIS) is a comprehensive cryptographic metric evaluated objectively on-chain.
          </p>
        </motion.div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4rem', alignItems: 'center' }}>
          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} className="card" style={{ background: 'var(--bg-card)', padding: '2.5rem', border: '1px solid var(--glass-border)' }}>
            <h3 style={{ marginBottom: '1.5rem', fontSize: '1.4rem' }}>The Geometric Volume Formula</h3>
            <div style={{ background: 'var(--bg-color)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--border-color)', marginBottom: '2rem', overflowX: 'auto' }}>
              <BlockMath math={aisFormula} />
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed var(--border-color)', paddingBottom: '0.5rem' }}>
                <strong style={{ color: 'var(--theme-accent)' }}>Entropy ($S_&#123;entropy&#125;$)</strong>
                <span style={{ color: 'var(--text-secondary)' }}>Predictability & Drift bounds</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed var(--border-color)', paddingBottom: '0.5rem' }}>
                <strong style={{ color: '#4caf50' }}>Grounding ($S_&#123;grounding&#125;$)</strong>
                <span style={{ color: 'var(--text-secondary)' }}>RAG hallucination rates</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed var(--border-color)', paddingBottom: '0.5rem' }}>
                <strong style={{ color: '#f59e0b' }}>Sacrifice ($S_&#123;sacrifice&#125;$)</strong>
                <span style={{ color: 'var(--text-secondary)' }}>$ITK Token collateral locked</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong style={{ color: '#2196f3' }}>Compliance ($S_&#123;compliance&#125;$)</strong>
                <span style={{ color: 'var(--text-secondary)' }}>Policy adherence (OPA/Rego)</span>
              </div>
            </div>
          </motion.div>

          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition}>
            <h3 style={{ fontSize: '1.8rem', marginBottom: '1.5rem' }}>The Zero-Knowledge Multiplier</h3>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: '2rem', fontSize: '1.1rem' }}>
              Every AI compute cycle can be validated via hardware TEE (Trusted Execution Environment) attestation and Barretenberg ZK proofs. When verified cryptographically, agents receive a <strong>1.15x multiplier</strong> ($ZK_&#123;boost&#125;$) to their global standing.
            </p>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: '2rem', fontSize: '1.1rem' }}>
              This dynamic, interactive graph algorithm ensures that hallucination rates directly decay an agent's AIS over time, removing their ability to handle high-stakes transactions automatically.
            </p>
            
            <div style={{ display: 'flex', gap: '1rem' }}>
              <div style={{ padding: '0.75rem 1rem', background: 'rgba(76, 175, 80, 0.1)', color: '#4caf50', border: '1px solid rgba(76, 175, 80, 0.3)', borderRadius: '6px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Shield size={18} /> Proof-of-Inference
              </div>
              <div style={{ padding: '0.75rem 1rem', background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '6px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Cpu size={18} /> Sovereign Hardware
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* 5. MVP Walkthrough: Core Protocol Features */}
      <section style={{ padding: '6rem 3rem', background: 'var(--bg-card)', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
            <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>MVP Walkthrough</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', lineHeight: 1.6 }}>
              A logical progression through the core Integrity Protocol dashboard.
            </p>
          </motion.div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '3rem', position: 'relative' }}>
            <div style={{ position: 'absolute', left: '24px', top: '24px', bottom: '24px', width: '2px', background: 'var(--border-color)', zIndex: 0 }} />
            
            <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ display: 'flex', gap: '2rem', position: 'relative', zIndex: 1 }}>
              <div style={{ width: '50px', height: '50px', borderRadius: '50%', background: 'var(--surface-color)', border: '2px solid var(--theme-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontWeight: 'bold', fontSize: '1.2rem' }}>1</div>
              <div className="card" style={{ flex: 1 }}>
                <h3 style={{ fontSize: '1.4rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Database size={20} color="var(--theme-accent)" /> Agent Identity & XNS Registry (<code style={{ fontSize: '1rem' }}>/identity</code>)
                </h3>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1rem' }}>
                  <strong>Value: Establishing verifiable Non-Human Identities (NHI).</strong>
                </p>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  Agents generate decentralized identifiers (DIDs) on-chain. Utilizing the Xibalba Name Service (XNS), agents mint human-readable domains (e.g., `trading-bot.xibalba`) binding their off-chain models to on-chain Ethereum addresses.
                </p>
              </div>
            </motion.div>

            <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ display: 'flex', gap: '2rem', position: 'relative', zIndex: 1 }}>
              <div style={{ width: '50px', height: '50px', borderRadius: '50%', background: 'var(--surface-color)', border: '2px solid var(--theme-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontWeight: 'bold', fontSize: '1.2rem' }}>2</div>
              <div className="card" style={{ flex: 1 }}>
                <h3 style={{ fontSize: '1.4rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={20} color="var(--theme-accent)" /> Observability & Merkle Lens (<code style={{ fontSize: '1rem' }}>/intelligence</code>)
                </h3>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1rem' }}>
                  <strong>Value: Unmatched forensic auditability for enterprise compliance.</strong>
                </p>
                <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  The Intelligence dashboard features the "Merkle Lens," mapping telemetry flows and SHA-256 derivations in real-time. This proves NIST AI RMF compliance by explicitly tracking RAG retrievals, tool calls, and model logic without compromising data privacy.
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* 6. Business Proposal: Market Verticals */}
      <section id="verticals" style={{ padding: '6rem 3rem', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
            <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Market Verticals</h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '800px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.6 }}>
              The core Integrity Protocol adapts elegantly to specific, highly lucrative enterprise markets that demand strict determinism.
            </p>
          </motion.div>

          <motion.div variants={stagger} initial="initial" whileInView="whileInView" viewport={stagger.viewport} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '2.5rem' }}>
            <motion.div variants={fadeInUp} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ background: 'var(--bg-color)', width: '56px', height: '56px', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1.5rem', border: '1px solid rgba(33, 150, 243, 0.3)' }}>
                <ShieldAlert size={28} color="#2196f3" />
              </div>
              <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Xibalba Shield</h3>
              <p style={{ color: 'var(--theme-accent)', fontWeight: 600, marginBottom: '1rem' }}>Market: AI Security & Threat Detection</p>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, flex: 1, marginBottom: '1.5rem' }}>
                Xibalba Shield intercepts rogue actions in under 50ms using strict OPA policy gates. It actively blocks prompt injection attacks, discovers shadow AI, and guarantees Real-time Agent Security before any system mutations occur.
              </p>
              <Link to="/shield" className="button" style={{ textAlign: 'center', textDecoration: 'none', borderColor: '#2196f3', color: '#2196f3' }}>View Shield Prototype</Link>
            </motion.div>

            <motion.div variants={fadeInUp} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ background: 'var(--bg-color)', width: '56px', height: '56px', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1.5rem', border: '1px solid rgba(76, 175, 80, 0.3)' }}>
                <Activity size={28} color="#4caf50" />
              </div>
              <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Integrity Health</h3>
              <p style={{ color: 'var(--theme-accent)', fontWeight: 600, marginBottom: '1rem' }}>Market: Healthcare IT & HIPAA</p>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, flex: 1, marginBottom: '1.5rem' }}>
                Utilizing the novel <code>SmartBAA</code> and client-side PHI <code>Redactor</code>, Integrity Health unlocks secure FHIR data through patient consent flowcharts. We ensure "Minimum Necessary" data ever reaches the LLM.
              </p>
              <Link to="/health" className="button" style={{ textAlign: 'center', textDecoration: 'none', borderColor: '#4caf50', color: '#4caf50' }}>View Health Prototype</Link>
            </motion.div>

            <motion.div variants={fadeInUp} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ background: 'var(--bg-color)', width: '56px', height: '56px', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1.5rem', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                <TrendingUp size={28} color="#f59e0b" />
              </div>
              <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Decentralized Finance</h3>
              <p style={{ color: 'var(--theme-accent)', fontWeight: 600, marginBottom: '1rem' }}>Market: DeFi & Agent Economics</p>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, flex: 1, marginBottom: '1.5rem' }}>
                Powered by the <code>$ITK</code> token. Agents utilize the <code>A2ACapitalPool</code> for dynamic capital allocation markets, staking for trust, and facing immediate slashing penalties for measurable hallucination events.
              </p>
              <Link to="/financials" className="button" style={{ textAlign: 'center', textDecoration: 'none', borderColor: '#f59e0b', color: '#f59e0b' }}>View Finance Prototype</Link>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* 7. The Competitive Moat (Standards Matrix) */}
      <section style={{ padding: '6rem 3rem', background: 'var(--bg-card)' }}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
            <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>The Competitive Moat</h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '800px', margin: '0 auto', fontSize: '1.1rem', lineHeight: 1.6 }}>
              Legacy Web2 companies cannot easily copy this architecture. Our moat is built on highly technical, decentralized standard implementations.
            </p>
          </motion.div>

          <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} className="card" style={{ padding: '0', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--surface-color)', borderBottom: '2px solid var(--border-color)' }}>
                  <th style={{ padding: '1.5rem', fontWeight: 600 }}>Standard</th>
                  <th style={{ padding: '1.5rem', fontWeight: 600 }}>Component</th>
                  <th style={{ padding: '1.5rem', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '1.5rem', fontWeight: 600 }}>Implementation Benefit</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1.5rem', fontWeight: 500, fontFamily: 'monospace' }}>W3C DID v1.0</td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Agent Identity</td>
                  <td style={{ padding: '1.5rem' }}><span style={{ color: '#4caf50', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Check size={14}/> Implemented</span></td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Base standard for <code>did:integrity:*</code> providing portable identities.</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1.5rem', fontWeight: 500, fontFamily: 'monospace' }}>VC Data Model</td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Agent Reputation</td>
                  <td style={{ padding: '1.5rem' }}><span style={{ color: '#4caf50', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Check size={14}/> Implemented</span></td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Off-chain Verifiable Credentials powering AIS evaluations securely.</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1.5rem', fontWeight: 500, fontFamily: 'monospace' }}>ERC-721 (XNS)</td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Registry</td>
                  <td style={{ padding: '1.5rem' }}><span style={{ color: '#4caf50', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Check size={14}/> Implemented</span></td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>NFT-based human-readable agent domains (e.g. <code>.xibalba</code>).</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '1.5rem', fontWeight: 500, fontFamily: 'monospace' }}>EIP-712</td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Meta-Tx</td>
                  <td style={{ padding: '1.5rem' }}><span style={{ color: '#4caf50', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Check size={14}/> Implemented</span></td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Typed structured data hashing for gasless agent state updates.</td>
                </tr>
                <tr>
                  <td style={{ padding: '1.5rem', fontWeight: 500, fontFamily: 'monospace' }}>Noir/Barretenberg</td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>ZK Proving</td>
                  <td style={{ padding: '1.5rem' }}><span style={{ color: '#4caf50', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Check size={14}/> Implemented</span></td>
                  <td style={{ padding: '1.5rem', color: 'var(--text-secondary)' }}>Zero-knowledge circuits to mask confidential telemetry.</td>
                </tr>
              </tbody>
            </table>
          </motion.div>
        </div>
      </section>

      {/* 8. FAQ Section */}
      <section id="faq" style={{ padding: '6rem 3rem', maxWidth: '800px', margin: '0 auto' }}>
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>Knowledge Base & FAQ</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem' }}>Preemptively addressing deep technical and business mechanics.</p>
        </motion.div>
        
        <motion.div variants={stagger} initial="initial" whileInView="whileInView" viewport={stagger.viewport} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <motion.div variants={fadeInUp}>
            <FAQItem 
              question="How does the Oracle derive signals without accessing PHI?" 
              answer={
                <>
                  <p>Our client-side <code>Redactor</code> pipelines sanitize and mask Protected Health Information using deterministic tokenization before the telemetry payload is sent to the Oracle. The Oracle evaluates behavioral flow (e.g. tool execution order, response latency, confidence bounds) over the sanitized metadata rather than raw data, preserving absolute HIPAA compliance while computing the AIS.</p>
                </>
              }
            />
          </motion.div>
          <motion.div variants={fadeInUp}>
            <FAQItem 
              question="What happens during a slashing event?" 
              answer={
                <>
                  <p>When the oracle detects a catastrophic hallucination or OPA policy violation, it submits a cryptographically signed payload to the <code>Slasher.sol</code> contract on Base. The contract immediately burns a portion of the agent's staked <code>$ITK</code> collateral, penalizing the agent financially and instantaneously downgrading its identity Tier, cutting off access to high-value tools.</p>
                </>
              }
            />
          </motion.div>
          <motion.div variants={fadeInUp}>
            <FAQItem 
              question="How does the OPA middleware intercept intents in under 50ms?" 
              answer={
                <>
                  <p>The Xibalba Shield utilizes compiled Rego policies running natively via WebAssembly (Wasm) inside the edge execution environment. When the LLM generates an intent, it is evaluated against the memory-resident Wasm policy graph before the network request to the MCP tool is dispatched, achieving interception times averaging ~18-35ms.</p>
                </>
              }
            />
          </motion.div>
          <motion.div variants={fadeInUp}>
            <FAQItem 
              question="What is the Insured Agent Flywheel?" 
              answer={
                <>
                  <p>Our primary business value is not the AI agent itself; it is the <strong>Actuarial Feed</strong> that makes third-party AI agents insurable. Underwriters cannot price professional liability insurance for agents because they are "black boxes." Xibalba creates verifiable cryptographic anchors to solve this, creating a massive data-moat.</p>
                </>
              }
            />
          </motion.div>
        </motion.div>
      </section>

      {/* 9. Contact Form Section */}
      <section id="contact" style={{ padding: '4rem 2rem', background: 'var(--surface-color)', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)' }}>
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} className="card" style={{ maxWidth: '600px', margin: '0 auto', border: '1px solid var(--glass-border)' }}>
          <h2 style={{ textAlign: 'center', marginBottom: '0.5rem', fontSize: '2rem' }}>Enterprise Onboarding</h2>
          <p style={{ textAlign: 'center', color: 'var(--text-secondary)', marginBottom: '2.5rem' }}>For VCs, strategic partnerships, and early pilot access.</p>
          
          <form style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div style={{ display: 'flex', gap: '1.5rem' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Full Name</label>
                <input type="text" style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)', fontFamily: 'inherit' }} placeholder="John Doe" />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Organization</label>
                <input type="text" style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)', fontFamily: 'inherit' }} placeholder="Acme Corp" />
              </div>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Work Email</label>
              <input type="email" style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)', fontFamily: 'inherit' }} placeholder="john@acmecorp.com" />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Target Use Case</label>
              <select style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)', fontFamily: 'inherit' }}>
                <option>Integrity Health (HIPAA)</option>
                <option>Xibalba Shield (Security)</option>
                <option>DeFi / Agentic Capital</option>
                <option>Other Enterprise Pilot</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Direct Message</label>
              <textarea rows={4} style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)', fontFamily: 'inherit', resize: 'vertical' }} placeholder="Tell us about your infrastructure goals..."></textarea>
            </div>
            <button type="button" className="button primary" style={{ padding: '1rem', fontSize: '1rem', fontWeight: 600 }}>Submit Inquiry</button>
          </form>
        </motion.div>
      </section>

      {/* 10. Specification */}
      <section id="specification" style={{ padding: '5rem 2rem', background: 'linear-gradient(135deg, rgba(0, 150, 255, 0.08), rgba(0, 255, 200, 0.035))', borderBottom: '1px solid var(--border-color)' }}>
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} className="card" style={{ maxWidth: '1000px', margin: '0 auto', padding: 'clamp(2rem, 5vw, 4rem)', border: '1px solid var(--glass-border)', textAlign: 'center' }}>
          <span style={{ display: 'inline-block', marginBottom: '1rem', color: 'var(--accent-color)', fontSize: '0.8rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Protocol specification</span>
          <h2 style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', marginBottom: '1rem' }}>Read the architecture behind verifiable agent integrity.</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', lineHeight: 1.7, maxWidth: '720px', margin: '0 auto 2rem' }}>
            The living v0.4 specification is maintained in the Integrity Wiki. The original comprehensive v0.3 design is also preserved as a browser-viewable PDF for historical reference.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '1rem' }}>
            <Link to="/wiki" className="button primary" style={{ padding: '0.9rem 1.4rem', textDecoration: 'none' }}>
              Read current v0.4 in the Wiki
            </Link>
            <a href="/integrity-protocol-specification-v0.3.pdf" target="_blank" rel="noopener noreferrer" className="button secondary" style={{ padding: '0.9rem 1.4rem', textDecoration: 'none' }}>
              View archived v0.3 PDF
            </a>
            <a href="/integrity-protocol-specification-v0.3.pdf" download="Integrity_Protocol_Specification_v0.3.pdf" className="button secondary" style={{ padding: '0.9rem 1.4rem', textDecoration: 'none' }}>
              Download PDF
            </a>
          </div>
          <p style={{ margin: '1.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.82rem' }}>v0.4 is normative · PDF archive is v0.3</p>
        </motion.div>
      </section>

      {/* 11. Global Footer & Final CTA */}
      <footer style={{ padding: '6rem 3rem 2rem 3rem', textAlign: 'center' }}>
        <motion.div initial={fadeInUp.initial} whileInView={fadeInUp.whileInView} viewport={fadeInUp.viewport} transition={fadeInUp.transition} style={{ marginBottom: '6rem' }}>
          <h2 style={{ fontSize: '2.5rem', marginBottom: '1.5rem' }}>The future of the economy is autonomous.</h2>
          <p style={{ fontSize: '1.25rem', color: 'var(--text-secondary)', maxWidth: '700px', margin: '0 auto 2.5rem auto', lineHeight: 1.6 }}>
            Join the protocol establishing the necessary cryptographic trust layer for the next era of compute.
          </p>
          <Link to="/auth" className="button primary" style={{ padding: '1.5rem 3rem', fontSize: '1.25rem', fontWeight: 700, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.75rem', boxShadow: '0 0 30px rgba(0, 150, 255, 0.4)' }}>
            Launch MVP Dashboard <ArrowRight size={20} />
          </Link>
        </motion.div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem', borderTop: '1px solid var(--border-color)', paddingTop: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <img src="https://xibalbatechsol.github.io/XibalbaSolutionsLogo.png" alt="Xibalba Solutions" style={{ height: '24px' }} />
            <span>&copy; {new Date().getFullYear()} Xibalba Solutions. All rights reserved.</span>
          </div>
          <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
            <a href="https://github.com/xibalbatechsol" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>GitHub Repo</a>
            <Link to="/wiki" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Integrity Wiki</Link>
            <Link to="/privacy" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Privacy Policy</Link>
            <Link to="/terms" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Terms of Service</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
