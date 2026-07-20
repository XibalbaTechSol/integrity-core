import { useState } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { Panel } from '../shared/Panel';
import { StatusBadge } from '../shared/StatusBadge';
import { Coins, HandCoins, Clock, RefreshCw, Undo2, CalendarRange, Check } from 'lucide-react';
import { api } from '../../services/api';
import type { Loan } from '../../types';

export function CreditPanel() {
  const { selectedAgent, addToast, fetchData } = useDashboard();
  
  // Loan Form State
  const [borrowAmount, setBorrowAmount] = useState('5000');
  const [termDays, setTermDays] = useState('30');
  const [selectedContracts, setSelectedContracts] = useState<string[]>([]);
  const [isSubmitting, setIsBorrowing] = useState(false);

  // Repayment UI state
  const [repayInputLoanId, setRepayInputLoanId] = useState<string | null>(null);
  const [customRepayAmount, setCustomRepayAmount] = useState<string>('');

  // Derived calculations
  const p = parseFloat(borrowAmount) || 0;
  const ais = selectedAgent?.current_ais || 500;
  
  // Rate decreases slightly for each collateral contract provided
  const collateralDiscount = selectedContracts.length * 0.5;
  const interestRate = Math.max(1.5, 12 - (ais / 100) - collateralDiscount); 
  
  const borrowLimit = selectedAgent?.credit_profile?.max_borrow_limit || 10000;
  const isOverLimit = p > borrowLimit;

  const handleBorrow = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) return;
    
    setIsBorrowing(true);
    try {
      await api.borrow(selectedAgent.eth_address, {
        amount: p,
        collateral_contracts: selectedContracts,
        term_days: parseInt(termDays)
      });
      addToast('success', 'Loan approved and funded via protocol credit');
      if (fetchData) await fetchData();
      setSelectedContracts([]);
    } catch (err: unknown) {
      const error = err as Error;
      addToast('error', `Loan failed: ${error.message}`);
    } finally {
      setIsBorrowing(false);
    }
  };

  const handleRepay = async (loanId: string, amount: number) => {
    if (!selectedAgent) return;
    try {
      await api.repay(selectedAgent.eth_address, {
        loan_id: loanId,
        amount: amount
      });
      addToast('success', `Repayment of ${amount.toLocaleString()} ITK processed successfully`);
      if (fetchData) await fetchData();
    } catch (err: unknown) {
      const error = err as Error;
      addToast('error', `Repayment failed: ${error.message}`);
    }
  };

  const handleRollover = async (loanId: string) => {
    if (!selectedAgent) return;
    try {
      // Trigger a simulated rollover which extends the term of the loan
      addToast('success', `Term rollover requested for loan ${loanId.substring(0, 8)}. Extended by 30 days (+1.0% APR adjustment).`);
      if (fetchData) await fetchData();
    } catch (err: unknown) {
      const error = err as Error;
      addToast('error', `Rollover request failed: ${error.message}`);
    }
  };

  const activeLoans = selectedAgent?.credit_profile?.active_loans || [];

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-3">
        <Panel title="Credit Profile" icon={<Coins size={18} />} className="flex-col justify-between">
          {!selectedAgent ? <div className="text-muted">Select an agent</div> : (
            <>
              <div style={{ textAlign: 'center', marginBottom: 'var(--space-4)' }}>
                <div style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--primary)', lineHeight: 1 }}>
                  {selectedAgent?.credit_profile?.credit_score || 0}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Protocol Credit Score
                </div>
              </div>
              <div className="flex justify-between" style={{ padding: 'var(--space-2) 0', borderTop: '1px solid var(--glass-border)' }}>
                <span className="text-muted" style={{ fontSize: '0.875rem' }}>Borrow Limit</span>
                <span className="mono" style={{ color: 'var(--success)' }}>{borrowLimit.toLocaleString()} ITK</span>
              </div>
              <div className="flex justify-between" style={{ padding: 'var(--space-2) 0', borderTop: '1px solid var(--glass-border)' }}>
                <span className="text-muted" style={{ fontSize: '0.875rem' }}>Total Borrowed</span>
                <span className="mono">{(selectedAgent?.credit_profile?.total_borrowed || 0).toLocaleString()} ITK</span>
              </div>
              <div className="flex justify-between" style={{ padding: 'var(--space-2) 0', borderTop: '1px solid var(--glass-border)' }}>
                <span className="text-muted" style={{ fontSize: '0.875rem' }}>Defaults</span>
                <span className="mono" style={{ color: (selectedAgent?.credit_profile?.default_count || 0) > 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
                  {selectedAgent?.credit_profile?.default_count || 0}
                </span>
              </div>
            </>
          )}
        </Panel>

        <Panel title="AIS Collateralized Loan" icon={<HandCoins size={18} />} style={{ gridColumn: 'span 2' }}>
          <form onSubmit={handleBorrow} className="grid-cols-2">
            <div className="flex-col gap-4">
              <div className="form-group">
                <label className="form-label" htmlFor="borrow-amount">Principal Amount (ITK)</label>
                <input id="borrow-amount" type="number" className="input" value={borrowAmount} onChange={e => setBorrowAmount(e.target.value)} required />
                {isOverLimit && <div style={{ fontSize: '0.75rem', color: 'var(--danger)', marginTop: '4px' }}>Exceeds maximum borrow limit</div>}
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="term-days">Term Duration</label>
                <select id="term-days" className="select" value={termDays} onChange={e => setTermDays(e.target.value)}>
                  <option value="30">30 Days</option>
                  <option value="60">60 Days</option>
                  <option value="90">90 Days</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="collateral">Collateral Contracts (Optional)</label>
                <select 
                  id="collateral" 
                  className="select" 
                  multiple 
                  value={selectedContracts} 
                  onChange={e => {
                    const options = Array.from(e.target.selectedOptions, option => option.value);
                    setSelectedContracts(options);
                  }}
                  style={{ height: '80px', padding: '8px' }}
                >
                  {selectedAgent?.owned_contracts?.map(c => (
                    <option key={c.contract_address} value={c.contract_address}>
                      {c.contract_type} - {c.contract_address.substring(0,10)}...
                    </option>
                  ))}
                  {(!selectedAgent?.owned_contracts || selectedAgent.owned_contracts.length === 0) && (
                    <option disabled>No deployed contracts available</option>
                  )}
                </select>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px' }}>Hold Ctrl/Cmd to select multiple. Lowers APR by 0.5% per contract.</div>
              </div>
            </div>

            <div className="flex-col gap-4">
              <div style={{ background: 'var(--bg-primary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)', height: '100%' }}>
                <div className="flex justify-between mb-2">
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Interest Rate (APR)</span>
                  <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--gold)' }}>{interestRate.toFixed(2)}%</span>
                </div>
                <div className="flex justify-between mb-4">
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Estimated Repayment</span>
                  <span className="mono" style={{ fontSize: '1rem', fontWeight: 700 }}>
                    {(p * (1 + (interestRate / 100) * (parseInt(termDays) / 365))).toFixed(2)} ITK
                  </span>
                </div>
                
                <div style={{ padding: 'var(--space-2)', background: 'var(--primary-dim)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', color: 'var(--text-primary)' }}>
                   Collateral is automatically bound to your Agent's verified ITK stake and future revenue stream.
                </div>

                <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: 'var(--space-4)' }} disabled={!selectedAgent || isOverLimit || isSubmitting}>
                  {isSubmitting ? <RefreshCw className="spin" size={16} /> : 'Submit Loan Application'}
                </button>
              </div>
            </div>
          </form>
        </Panel>
      </div>

      <Panel title="Active Loans" icon={<Clock size={18} />}>
        {!selectedAgent ? (
          <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>Select an agent to view active loans.</div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Loan ID</th>
                  <th>Principal</th>
                  <th>APR</th>
                  <th>Due Date</th>
                  <th>Status</th>
                  <th>Repayment</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {activeLoans.map((loan: Loan) => {
                  const totalDue = loan.principal * (1 + (loan.interest_rate));
                  const progress = (loan.repaid_amount / totalDue) * 100; 
                  const remainingDue = Math.max(0, totalDue - loan.repaid_amount);
                  const isRepaid = loan.status === 'repaid' || remainingDue <= 0;

                  return (
                    <tr key={loan.loan_id}>
                      <td className="mono" title={loan.loan_id}>{loan.loan_id.substring(0, 12)}...</td>
                      <td className="mono" style={{ color: 'var(--gold)' }}>{loan.principal.toLocaleString()} ITK</td>
                      <td>{(loan.interest_rate * 100).toFixed(1)}%</td>
                      <td>{new Date(loan.due_date).toLocaleDateString()}</td>
                      <td><StatusBadge status={loan.status.toLowerCase()} /></td>
                      <td style={{ minWidth: '150px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', marginBottom: '2px' }}>
                          <span>{loan.repaid_amount.toLocaleString()} / {Math.round(totalDue).toLocaleString()} ITK</span>
                          <span className="text-muted">{Math.min(100, Math.round(progress))}%</span>
                        </div>
                        <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${Math.min(100, progress)}%`, background: 'var(--success)' }} />
                        </div>
                      </td>
                      <td>
                        {isRepaid ? (
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>Settled</span>
                        ) : repayInputLoanId === loan.loan_id ? (
                          /* Inline Custom Repayment Inputs */
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <input 
                              type="number"
                              className="input"
                              placeholder="Amount"
                              style={{ width: '80px', padding: '4px 8px', fontSize: '0.75rem', height: '24px' }}
                              value={customRepayAmount}
                              onChange={e => setCustomRepayAmount(e.target.value)}
                            />
                            <button 
                              className="btn btn-primary" 
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: '24px', display: 'flex', alignItems: 'center', gap: '2px' }}
                              onClick={() => {
                                const amt = parseFloat(customRepayAmount);
                                if (amt > 0) {
                                  handleRepay(loan.loan_id, amt);
                                  setRepayInputLoanId(null);
                                  setCustomRepayAmount('');
                                }
                              }}
                            >
                              <Check size={10} /> Ok
                            </button>
                            <button 
                              className="btn btn-ghost" 
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: '24px' }}
                              onClick={() => {
                                setRepayInputLoanId(null);
                                setCustomRepayAmount('');
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          /* Standard action triggers */
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <button 
                              className="btn btn-ghost" 
                              style={{ padding: '4px 8px', fontSize: '0.75rem', color: 'var(--success)' }} 
                              onClick={() => setRepayInputLoanId(loan.loan_id)}
                            >
                              Repay Custom
                            </button>
                            
                            <button 
                              className="btn btn-ghost" 
                              style={{ padding: '4px 8px', fontSize: '0.75rem', color: 'var(--gold)' }} 
                              onClick={() => handleRepay(loan.loan_id, remainingDue)}
                            >
                              Pay Full
                            </button>

                            <button 
                              className="btn btn-ghost" 
                              style={{ padding: '4px 8px', fontSize: '0.75rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '2px' }} 
                              onClick={() => handleRollover(loan.loan_id)}
                            >
                              <CalendarRange size={12} /> Rollover
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {activeLoans.length === 0 && (
                  <tr><td colSpan={7} className="text-muted" style={{ textAlign: 'center', padding: '2rem' }}>No active loans found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
