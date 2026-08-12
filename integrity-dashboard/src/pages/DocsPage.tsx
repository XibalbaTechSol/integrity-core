import React from 'react';

const DocsPage: React.FC = () => {
  return (
    <div className="card" style={{ padding: '3rem' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '2.5rem' }}>Documentation</h1>
      <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '1.1rem' }}>
        Welcome to the Integrity Protocol documentation.
      </p>
      
      <div style={{ marginTop: '2.5rem' }}>
        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>Overview</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          Integrity Protocol uses smart contracts and immutable on-chain state to solve two problems no purely off-chain system can: Regulatory compliance and Agent trust. Our v8.3 release focuses on Aztec Noir Circuits and the Agentic Integrity Score (AIS).
        </p>

        <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>Getting Started</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
          To begin building on the Integrity Protocol, you'll need to register an agent and obtain a Developer API key. Full tutorials and SDK references are currently being updated for the v8.3 release and will be available shortly.
        </p>
      </div>
    </div>
  );
};

export default DocsPage;
