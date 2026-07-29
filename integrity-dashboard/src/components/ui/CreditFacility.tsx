// @ts-nocheck
import React, { useState } from 'react';

interface CreditFacilityProps {
    agentAddress: string;
    currentAIS: number;
}

export const CreditFacility: React.FC<CreditFacilityProps> = ({ agentAddress, currentAIS }) => {
    const [amount, setAmount] = useState('');
    const [status, setStatus] = useState('');

    const requestLoan = async () => {
        // Honest gap: the protocol has no agent-requested "loan" primitive. Credit is
        // provided as A2ACapitalPool allocations — an allocator escrows $ITK for an agent,
        // gated on live AIS (see Finance → Credit / Allocate Capital), not a loan request.
        void agentAddress; void amount;
        setStatus('Agent-requested loans are not a protocol primitive. Credit is provided as A2ACapitalPool allocations (Finance → Credit), gated on live AIS.');
    };

    return (
        <div style={{ background: 'var(--navy-deep)', padding: '20px', borderRadius: '10px', border: '1px solid var(--border)' }}>
            <h3>Credit Facility</h3>
            <p>AIS-based ITK Lending</p>
            <input 
                type="number" 
                value={amount} 
                onChange={(e) => setAmount(e.target.value)} 
                placeholder="Amount in ITK"
                style={{ background: 'rgba(255,255,255,0.1)', color: 'white', padding: '10px', width: '100%' }}
            />
            <button onClick={requestLoan} style={{ marginTop: '10px', padding: '10px', width: '100%', background: 'var(--gold)' }}>
                Request Loan
            </button>
            {status && <p style={{ marginTop: '10px', color: 'var(--gold)' }}>{status}</p>}
        </div>
    );
};
