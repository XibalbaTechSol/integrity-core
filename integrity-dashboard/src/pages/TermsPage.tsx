import React from 'react';

const TermsPage: React.FC = () => {
  return (
    <div className="card" style={{ padding: '3rem' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '2.5rem' }}>Terms of Service</h1>
      
      <div style={{ marginTop: '2rem' }}>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          By using the Integrity Protocol, you agree to abide by the smart contract terms deployed on Base Sepolia. Xibalba Solutions provides no guarantees for the uptime of third-party testnets.
        </p>

        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginTop: '2rem' }}>1. Protocol Usage</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          The Integrity Protocol is currently in beta. You may use the protocol for testing agentic workflows and registering Decentralized Identifiers (DIDs) on the XNS registry. Production use is strictly limited to whitelisted enterprise partners during this phase.
        </p>

        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginTop: '2rem' }}>2. Liability</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          Xibalba Solutions is not liable for financial losses incurred through agent-to-agent trading, options pricing errors, or smart contract vulnerabilities on the testnet. You are responsible for ensuring the correctness of your agent's inference models.
        </p>
      </div>
    </div>
  );
};

export default TermsPage;
