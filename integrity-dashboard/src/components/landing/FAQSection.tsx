import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

const faqData = [
  {
    q: "How do agents sign and execute smart contracts through the Integrity Protocol?",
    a: "Every agent registered receives a hardware-bound DID identity linked to an on-chain wallet on Base L2. When an agent proposes a transaction, the SDK serializes the intended state, hashes it, and cryptographically signs it. The BCC middleware validates the commitment against the agent's Alignment Card policies before broadcast. Only verified, policy-compliant transactions reach on-chain execution."
  },
  {
    q: "Does the pre-execution gating add latency to agent transactions?",
    a: "No. The 4-gate validation pipeline runs locally via lightweight BCC middleware in under 15ms. The computationally heavy ZK-proof generation is processed completely asynchronously on a background queue and anchored to the chain after execution."
  },
  {
    q: "What blockchains and L2s does Xibalba support?",
    a: "Base L2 is the primary settlement and verification layer. The smart contracts are fully EVM-compatible, meaning deployment to Arbitrum, Optimism, Polygon, or Ethereum mainnet requires zero code changes."
  },
  {
    q: "How does on-chain verification work without exposing proprietary agent logic?",
    a: "ZK-proofs are essential here. Aztec Noir circuits generate a zero-knowledge proof that the agent's reasoning trace complied with its Alignment Card policies — without revealing prompts, model weights, or tool calls. Only the cryptographic proof and a commitment hash are published on-chain."
  },
  {
    q: "Can I define custom transaction policies beyond the default templates?",
    a: "Absolutely. The policy engine uses Rego (Open Policy Agent), giving you full declarative control over your agent's behavioral boundaries. Policies are version-controlled and hot-reloadable without redeploying your agent."
  },
  {
    q: "Is the SDK compatible with existing agent frameworks like LangChain, CrewAI, or AutoGen?",
    a: "Yes. The Integrity SDK operates at the function execution and network interface layers — framework-agnostic by design. We provide drop-in wrappers for popular agent frameworks (LangChain, LlamaIndex, AutoGen, CrewAI) and raw LLM providers (OpenAI, Anthropic, Gemini). We also integrate natively with on-chain agent standards like ERC-6551 (token-bound accounts). If your agent can execute in Python or Node.js and interact with an EVM chain, Xibalba can wrap it with verifiable execution in under five minutes."
  },
  {
    q: "What happens when an agent violates its policy in a live economic environment?",
    a: "The violation is caught pre-execution — before any transaction hits the chain. The circuit breaker fires in <15ms, killing the action and isolating the session. From there, configurable responses kick in: Self-Correction loops return the violation reasoning to the agent so it can reformulate a compliant transaction; Fallback Routing escalates to human-in-the-loop approval; or the agent is automatically downgraded to read-only mode. The violation is logged immutably, the agent's on-chain AIS score is slashed, and counterparties are notified via the Reputation Registry. No bad transaction ever reaches settlement."
  },
  {
    q: "How does the Agent Integrity Score (AIS) reputation system work on-chain?",
    a: "Every agent's AIS (0–1000) is a domain-weighted composite of four on-chain metrics: behavioral entropy (how predictable and stable are its actions?), grounding (how often does a human need to intervene?), computational sacrifice (verified GPU-hours), and compliance (regulatory health). The score is recalculated in real-time by the Rust Axum telemetry engine and anchored to the ReputationRegistry.sol contract on Base L2. Counterparties can query any agent's AIS before entering a contract. Below 600, the agent operates pseudonymously with limited transaction scope. Above 700, it qualifies for institutional credit lines. At 850+, it earns TEE-bound institutional trust — the on-chain equivalent of a AAA credit rating for autonomous systems."
  },
  {
    q: "How does Xibalba compare to Ritual, Autonolas, Fetch.ai, and Phala Network?",
    a: "Ritual focuses on on-chain inference verification — proving a model produced a specific output. Autonolas/Olas provides a framework for composing multi-agent services with token incentives. Fetch.ai builds an agent-to-agent communication and discovery layer. Phala Network offers TEE-based confidential compute for smart contracts. Xibalba is none of these — and complementary to all of them. We are the pre-execution trust layer: the gating, reputation, and policy enforcement infrastructure that sits between an agent's intent and its on-chain action. Ritual verifies what happened; we prevent what shouldn't happen. Olas orchestrates agent services; we ensure each agent in the swarm is policy-compliant before it transacts. We integrate with these ecosystems rather than compete with them."
  },
  {
    q: "What's the go-to-market strategy? Why start with healthcare?",
    a: "Healthcare is our first vertical, not our identity. We chose it because HIPAA creates the highest regulatory bar for autonomous agent behavior — if our protocol can enforce compliance for an AI agent writing to an EHR with PHI exposure rules, it can enforce policy for any agent in any domain. The wedge is healthcare (HIPAA-compliant agent gating), but the platform is horizontal: DeFi agents executing swaps within risk parameters, insurance agents processing claims against policy rules, supply-chain agents committing to SLAs on-chain. Every vertical where an autonomous agent needs to prove it acted within boundaries before transacting is our market. The autonomous agent economy needs trust infrastructure the same way e-commerce needed SSL."
  }
];

export const FAQSection = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const toggleFaq = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <div style={{ padding: '80px 20px', background: 'var(--navy-dark)' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <h2 style={{ fontSize: '2.5rem', fontWeight: 800, color: 'white' }}>Frequently Asked Questions</h2>
          <p style={{ color: 'rgba(255,255,255,0.6)' }}>Everything you need to know about the Integrity Protocol.</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {faqData.map((faq, index) => (
            <div 
              key={index}
              style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid rgba(255,255,255,0.05)',
                borderRadius: '8px',
                overflow: 'hidden'
              }}
            >
              <button 
                onClick={() => toggleFaq(index)}
                style={{
                  width: '100%',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '20px',
                  background: 'none',
                  border: 'none',
                  color: 'white',
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: '1.1rem',
                  fontWeight: 500
                }}
              >
                <span>{faq.q}</span>
                {openIndex === index ? <ChevronUp size={20} color="var(--gold-primary)" /> : <ChevronDown size={20} color="rgba(255,255,255,0.4)" />}
              </button>
              {openIndex === index && (
                <div style={{ padding: '0 20px 20px 20px', color: 'rgba(255,255,255,0.7)', lineHeight: '1.6' }}>
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
