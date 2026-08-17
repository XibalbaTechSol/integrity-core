import React from 'react';

const PrivacyPage: React.FC = () => {
  return (
    <div className="card" style={{ padding: '3rem' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '2.5rem' }}>Privacy Policy</h1>
      
      <div style={{ marginTop: '2rem' }}>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          At Xibalba Solutions, we take your privacy seriously. All on-chain metrics are anonymized and processed via zero-knowledge proofs. No personally identifiable information (PII) is stored in the AIS ledger.
        </p>

        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginTop: '2rem' }}>1. Data Collection</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          We collect deterministic execution logs from registered agents solely for the purpose of computing the Agentic Integrity Score (AIS). We do not collect personal health information, financial secrets, or proprietary trading algorithms.
        </p>

        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginTop: '2rem' }}>2. Zero-Knowledge Processing</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          By utilizing Aztec Noir circuits, any sensitive computation remains entirely within the agent's Trusted Execution Environment (TEE). We only receive and verify the cryptographic proof of inference, ensuring strict compliance with data privacy regulations such as HIPAA.
        </p>
      </div>
    </div>
  );
};

export default PrivacyPage;
