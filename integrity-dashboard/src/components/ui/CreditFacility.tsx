// @ts-nocheck
import React, { useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../../constants';

interface CreditFacilityProps {
    agentAddress: string;
    currentAIS: number;
}

export const CreditFacility: React.FC<CreditFacilityProps> = ({ agentAddress, currentAIS }) => {
    const [amount, setAmount] = useState('');
    const [status, setStatus] = useState('');

    const requestLoan = async () => {
        try {
            const token = localStorage.getItem('integrity_mock_token');
            const res = await axios.post(`${API_BASE}/v1/loan/request`, 
                { agent_address: agentAddress, amount: parseFloat(amount) },
                { headers: { Authorization: token } }
            );
            setStatus(`Loan Approved! ID: ${res.data.loan_id}`);
        } catch (e: any) {
            setStatus(e.response?.data?.detail || 'Loan Request Failed');
        }
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
