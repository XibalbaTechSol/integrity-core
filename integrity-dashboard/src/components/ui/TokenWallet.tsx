import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ethers } from 'ethers';

import {
    Coins, ArrowDownLeft, Loader2,
    Copy, ShieldCheck, Landmark, X, ArrowUpRight, ArrowDownRight, Fingerprint
} from 'lucide-react';
import { ITK_TOKEN_ADDRESS } from '../../constants';
import { ERC20_ABI } from '../../chain/markets';

import { useDashboard } from '../../context/DashboardContext';
import { oracle, TransactionDto, CreditDto } from '../../services/oracle';
import { userapi, getToken } from '../../services/userapi';

function CreditSummary({ agentId }: { agentId?: string }) {
    const [credit, setCredit] = useState<CreditDto | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!agentId) { setLoading(false); return; }
        let active = true;
        oracle.getCredit(agentId)
            .then(c => { if (active) setCredit(c); })
            .catch(() => { if (active) setCredit(null); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [agentId]);

    return (
        <div style={{ textAlign: 'center' }}>
            <Landmark size={48} style={{ color: 'var(--theme-accent)', marginBottom: 'var(--space-6)' }} />
            <h3 style={{ marginTop: 0, marginBottom: 'var(--space-4)', fontSize: '1.5rem', fontWeight: 800, fontFamily: 'Playfair Display, serif' }}>Capital Allocation</h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 'var(--space-8)' }}>
                Real A2ACapitalPool credit position for this agent — allocation-based, not an interest-bearing loan.
            </p>
            {loading ? (
                <div className="skeleton" style={{ height: '80px', borderRadius: 'var(--r-md)' }} />
            ) : !credit ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No credit allocations for this agent yet.</div>
            ) : (
                <div style={{ background: 'var(--glass-surface-light)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--space-6)', textAlign: 'left' }}>
                    {[
                        ['Total Allocated', credit.total_allocated],
                        ['Escrowed', credit.escrowed],
                        ['Released', credit.released],
                        ['Clawed Back', credit.clawed_back],
                        ['Breached', credit.breached],
                    ].map(([label, value]) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
                            <span style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)' }}>{(label as string).toUpperCase()}</span>
                            <span style={{ fontSize: '0.7rem', fontWeight: 800, color: 'white' }}>{Number(ethers.formatEther(value)).toLocaleString()} ITK</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

interface Transaction {
    hash: string;
    type: string;
    value: string;
    isOut: boolean;
    status: string;
}

function toTransaction(t: TransactionDto): Transaction {
    const isOut = /send|withdraw|out|transfer_out|debit/i.test(t.type);
    // t.amount is a raw wei string (see oracle backend TransactionDto) — format for display.
    let value = t.amount;
    try { value = ethers.formatEther(t.amount); } catch { /* not a valid wei string, show as-is */ }
    return { hash: t.id, type: t.type, value, isOut, status: t.status };
}

export const TokenWallet = () => {
    const { selectedAgent, agents, addToast } = useDashboard() as any;
    const [balance, setBalance] = useState<string>('0.0');
    const [profileBalance, setProfileBalance] = useState<number | null>(null);
    const [appWalletAddress, setAppWalletAddress] = useState<string | null>(null);
    const [address, setAddress] = useState<string>('');
    const [recipient, setRecipient] = useState('');
    const [amount, setAmount] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isFetching, setIsFetching] = useState(true);
    const [isProfileLoading, setIsProfileLoading] = useState(true);
    const [txHistory, setTxHistory] = useState<Transaction[]>([]);
    const [activeTab, setActiveTab] = useState<'assets' | 'activity'>('assets');
    const [activeModal, setActiveModal] = useState<'send' | 'receive' | 'loan' | 'stake' | null>(null);

    // Real custodial app wallet (userapi's internal $ITK ledger) — only present once
    // the user has a session; there's no fabricated fallback balance otherwise.
    const fetchProfileData = useCallback(async () => {
        setIsProfileLoading(true);
        if (!getToken()) {
            setProfileBalance(null);
            setAppWalletAddress(null);
            setIsProfileLoading(false);
            return;
        }
        try {
            const w = await userapi.getWallet();
            setProfileBalance(w.balance);
            setAppWalletAddress(w.app_wallet_address);
        } catch {
            setProfileBalance(null);
            setAppWalletAddress(null);
        } finally {
            setIsProfileLoading(false);
        }
    }, []);

    const fetchWalletData = useCallback(async () => {
        if (!selectedAgent) { setIsFetching(false); return; }
        setIsFetching(true);
        try {
            const w = await oracle.getWallet(selectedAgent.eth_address);
            setAddress(w.sovereign_agent);
            // w.itk_balance is a raw wei string straight off the chain (U256::to_string()).
            setBalance(ethers.formatEther(w.itk_balance));
            setTxHistory((w.transaction_history || []).map(toTransaction));
        } catch {
            setAddress('');
            setBalance('0.0');
            setTxHistory([]);
        } finally {
            setIsFetching(false);
        }
    }, [selectedAgent?.eth_address]);

    useEffect(() => { fetchProfileData(); }, [fetchProfileData]);
    useEffect(() => { fetchWalletData(); }, [fetchWalletData]);

    const handleTransfer = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!amount || !recipient) return;
        const ethereum = (window as any).ethereum;
        if (!ethereum) {
            addToast?.('error', 'No Ethereum wallet found.');
            return;
        }
        setIsLoading(true);
        try {
            const provider = new ethers.BrowserProvider(ethereum);
            const signer = await provider.getSigner();
            const itk = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, signer);
            const tx = await itk.transfer(recipient, ethers.parseEther(amount));
            await tx.wait();
            addToast?.('success', `Sent ${amount} ITK — tx ${tx.hash.substring(0, 10)}...`);
            setActiveModal(null);
            setAmount('');
            setRecipient('');
            fetchWalletData();
        } catch (err: any) {
            addToast?.('error', `Transfer failed: ${err.shortMessage || err.message}`);
        } finally {
            setIsLoading(false);
        }
    };


    return (
        <div style={{ maxWidth: 'var(--max-width)', margin: '0 auto', width: '100%' }}>
            {/* Balance Overview Card */}
            <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="enterprise-card" 
                style={{ 
                    padding: 'var(--space-12) var(--space-8)', 
                    textAlign: 'center', 
                    marginBottom: 'var(--space-8)', 
                    position: 'relative', 
                    overflow: 'hidden',
                    background: 'linear-gradient(180deg, rgba(201, 168, 76, 0.08) 0%, var(--navy-deep) 100%)',
                    borderRadius: 'var(--r-lg)'
                }}
            >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'var(--theme-accent-muted)', padding: '6px 12px', borderRadius: 'var(--r-xl)', border: '1px solid var(--border)' }}>
                        <Fingerprint size={12} style={{ color: 'var(--theme-accent)' }} />
                        <span style={{ fontSize: '0.6rem', fontWeight: 800, color: 'var(--theme-accent)', letterSpacing: '0.2em', textTransform: 'uppercase' }}>
                            {parseFloat(balance) > 0 ? 'Protocol_L2_Vault' : 'Total Balance'}
                        </span>
                    </div>
                    
                    <div style={{ margin: 'var(--space-6) 0' }}>
                        {(isFetching || isProfileLoading) ? (
                            <div className="skeleton" style={{ height: '80px', width: '280px', margin: '0 auto var(--space-4)', borderRadius: 'var(--r-md)' }} />
                        ) : (
                            <div style={{ fontSize: '4.5rem', fontWeight: 700, color: 'white', fontFamily: 'Playfair Display, serif', lineHeight: 1 }}>
                                {(parseFloat(balance) > 0 ? parseFloat(balance) : (profileBalance ?? 0)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </div>
                        )}
                        <div style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--theme-accent)', letterSpacing: '0.4em', textTransform: 'uppercase', marginTop: 'var(--space-4)' }}>
                            ITK Balance (Testnet)
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', padding: '12px 20px', background: 'var(--glass-surface-light)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => { if(address) navigator.clipboard.writeText(address); }}>
                        <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{address ? `${address.substring(0, 12)}...${address.substring(34)}` : 'No Sovereign Agent Anchored'}</span>
                        <Copy size={14} style={{ color: 'var(--theme-accent)', opacity: 0.6 }} />
                    </div>
                    {selectedAgent && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', padding: '12px 20px', background: 'rgba(212, 175, 55, 0.05)', borderRadius: 'var(--r-md)', border: '1px solid var(--theme-accent)', cursor: 'pointer' }} onClick={() => { navigator.clipboard.writeText(selectedAgent.eth_address); }}>
                            <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--theme-accent)' }}>Agent {selectedAgent.alias}: {`${selectedAgent.eth_address.substring(0, 12)}...${selectedAgent.eth_address.substring(34)}`}</span>
                            <Copy size={14} style={{ color: 'var(--theme-accent)', opacity: 0.6 }} />
                        </div>
                    )}
                </div>

                {/* Primary Actions HUD */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)', marginTop: 'var(--space-12)', maxWidth: '400px', margin: 'var(--space-12) auto 0' }}>
                    {[
                        { id: 'send', label: 'Send', icon: ArrowUpRight },
                        { id: 'receive', label: 'Receive', icon: ArrowDownLeft },
                        { id: 'loan', label: 'Loan', icon: Landmark },
                        { id: 'stake', label: 'Stake', icon: ShieldCheck },
                    ].map(btn => (
                        <button 
                            key={btn.id}
                            onClick={() => setActiveModal(btn.id as any)}
                            style={{ background: 'none', border: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-3)', cursor: 'pointer' }}
                        >
                            <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'var(--theme-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'black', boxShadow: '0 8px 16px rgba(201, 168, 76, 0.2)' }}>
                                <btn.icon size={24} strokeWidth={2.5} />
                            </div>
                            <span style={{ fontSize: '0.7rem', fontWeight: 800, color: 'white', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{btn.label}</span>
                        </button>
                    ))}
                </div>
            </motion.div>

            {/* Asset & Activity Feed */}
            <div className="enterprise-card" style={{ padding: 0, overflow: 'hidden', borderRadius: 'var(--r-md)' }}>
                <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', background: 'var(--glass-surface-light)' }}>
                    {['assets', 'activity'].map(tab => (
                        <button 
                            key={tab}
                            onClick={() => setActiveTab(tab as any)}
                            style={{ flex: 1, padding: 'var(--space-4)', background: 'none', border: 'none', color: activeTab === tab ? 'var(--theme-accent)' : 'var(--text-muted)', borderBottom: activeTab === tab ? '2px solid var(--theme-accent)' : '2px solid transparent', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.15em', cursor: 'pointer' }}
                        >
                            {tab}
                        </button>
                    ))}
                </div>

                <div style={{ padding: 'var(--space-6)' }}>
                    {activeTab === 'assets' ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-4)', background: 'var(--glass-surface-light)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
                                <div style={{ width: '48px', height: '48px', background: 'var(--theme-accent)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'black' }}>
                                    <Coins size={24} />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 800, color: 'white', fontSize: '1rem' }}>Integrity Token</div>
                                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>ITK // ERC-20</div>
                                </div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                                <div style={{ fontWeight: 800, color: 'white', fontSize: '1.2rem' }}>{(parseFloat(balance) > 0 ? parseFloat(balance) : (profileBalance ?? 0)).toLocaleString()}</div>
                                <div style={{ fontSize: '0.65rem', color: 'var(--theme-accent)', fontWeight: 800, letterSpacing: '0.05em' }}>BASE_SEPOLIA</div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                            {isFetching ? (
                                [1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: '70px', borderRadius: 'var(--r-md)' }} />)
                            ) : txHistory.length > 0 ? txHistory.map((tx, i) => {
                                const isHash = /^0x[0-9a-fA-F]{64}$/.test(tx.hash);
                                const Wrapper = isHash ? 'a' : 'div';
                                return (
                                <Wrapper key={i} {...(isHash ? { href: `https://sepolia.basescan.org/tx/${tx.hash}`, target: '_blank', rel: 'noreferrer' } : {})} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-4)', background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)', textDecoration: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
                                        <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: tx.isOut ? 'rgba(244, 63, 94, 0.1)' : 'rgba(16, 185, 129, 0.1)', color: tx.isOut ? '#f43f5e' : 'var(--emerald)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            {tx.isOut ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
                                        </div>
                                        <div>
                                            <div style={{ fontWeight: 800, color: 'white', fontSize: '0.85rem' }}>{tx.type}</div>
                                            <div className="mono" style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '2px' }}>{tx.hash.substring(0, 16)}...</div>
                                        </div>
                                    </div>
                                    <div style={{ textAlign: 'right' }}>
                                        <div style={{ fontWeight: 800, color: tx.isOut ? 'white' : 'var(--emerald)', fontSize: '1rem' }}>
                                            {tx.isOut ? '-' : '+'}{parseFloat(tx.value).toLocaleString()}
                                        </div>
                                        <div style={{ fontSize: '0.6rem', color: 'var(--theme-accent)', fontWeight: 800, marginTop: '4px' }}>{tx.status}</div>
                                    </div>
                                </Wrapper>
                                );
                            }) : (
                                <div style={{ textAlign: 'center', padding: 'var(--space-12)', color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600 }}>No transaction history found.</div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Transaction Modals */}
            <AnimatePresence>
                {activeModal && (
                    <motion.div 
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        style={{ position: 'fixed', inset: 0, background: 'rgba(5, 13, 24, 0.9)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-6)', backdropFilter: 'var(--glass-blur)' }}
                        onClick={() => setActiveModal(null)}
                    >
                        <motion.div 
                            initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
                            className="enterprise-card"
                            style={{ width: '100%', maxWidth: '440px', padding: 'var(--space-10)', position: 'relative', background: 'var(--navy-deep)', border: '1px solid var(--border)' }}
                            onClick={e => e.stopPropagation()}
                        >
                            <button onClick={() => setActiveModal(null)} style={{ position: 'absolute', top: '24px', right: '24px', background: 'none', border: 'none', color: 'white', cursor: 'pointer' }}>
                                <X size={20} />
                            </button>

                            {activeModal === 'send' && (
                                <form onSubmit={handleTransfer}>
                                    <h3 style={{ marginTop: 0, marginBottom: 'var(--space-8)', fontSize: '1.5rem', fontWeight: 800, fontFamily: 'Playfair Display, serif' }}>Initiate Transfer</h3>
                                    <div style={{ marginBottom: 'var(--space-6)' }}>
                                        <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 800, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                                            Select Agent Recipient
                                        </label>
                                        <select 
                                            onChange={(e) => {
                                                if (e.target.value) setRecipient(e.target.value);
                                            }}
                                            value={recipient}
                                            style={{ width: '100%', padding: '16px', background: 'var(--glass-surface-light)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', color: 'white', outline: 'none', marginBottom: '12px', fontSize: '0.8rem', fontFamily: 'monospace' }}
                                        >
                                            <option value="" style={{ background: 'var(--navy-deep)' }}>-- Enter Custom Address or Select Agent --</option>
                                            {(agents || []).map((agent: any) => (
                                                <option key={agent.eth_address} value={agent.eth_address} style={{ background: 'var(--navy-deep)' }}>
                                                    {agent.alias} ({agent.eth_address.substring(0, 10)}...)
                                                </option>
                                            ))}
                                        </select>
                                        
                                        <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 800, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                                            Recipient Address
                                        </label>
                                        <input type="text" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="0x..." style={{ width: '100%', padding: '16px', background: 'var(--glass-surface-light)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', color: 'white', fontFamily: 'JetBrains Mono, monospace', outline: 'none' }} required />
                                    </div>
                                    <div style={{ marginBottom: 'var(--space-8)' }}>
                                        <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 800, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Amount (ITK)</label>
                                        <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" style={{ width: '100%', padding: '16px', background: 'var(--glass-surface-light)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', color: 'white', fontFamily: 'JetBrains Mono, monospace', outline: 'none' }} required />
                                    </div>
                                    <button type="submit" disabled={isLoading} className="btn btn-primary" style={{ width: '100%', padding: '16px', fontSize: '0.9rem', fontWeight: 800 }}>
                                        {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'CONFIRM TRANSACTION'}
                                    </button>
                                </form>
                            )}

                            {activeModal === 'receive' && (
                                <div style={{ textAlign: 'center' }}>
                                    <h3 style={{ marginTop: 0, marginBottom: 'var(--space-8)', fontSize: '1.5rem', fontWeight: 800, fontFamily: 'Playfair Display, serif' }}>Receive Assets</h3>
                                    <div style={{ background: 'white', padding: 'var(--space-6)', borderRadius: 'var(--r-md)', display: 'inline-block', marginBottom: 'var(--space-8)', boxShadow: '0 0 30px rgba(201, 168, 76, 0.2)' }}>
                                        <div style={{ width: '200px', height: '200px', background: '#f8fafc', borderRadius: 'var(--r-sm)' }} />
                                    </div>
                                    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--space-4)', marginBottom: 'var(--space-8)' }}>
                                        <div className="mono" style={{ fontSize: '0.85rem', color: 'white', wordBreak: 'break-all' }}>{address}</div>
                                    </div>
                                    <button onClick={() => { navigator.clipboard.writeText(address); addToast?.('success', 'Address copied'); }} className="btn btn-primary" style={{ width: '100%', padding: '16px' }}>COPY ADDRESS</button>
                                </div>
                            )}

                            {activeModal === 'loan' && (
                                <CreditSummary agentId={selectedAgent?.eth_address} />
                            )}

                            {activeModal === 'stake' && (
                                <div style={{ textAlign: 'center' }}>
                                    <ShieldCheck size={48} style={{ color: 'var(--emerald)', marginBottom: 'var(--space-6)' }} />
                                    <h3 style={{ marginTop: 0, marginBottom: 'var(--space-4)', fontSize: '1.5rem', fontWeight: 800, fontFamily: 'Playfair Display, serif' }}>Protocol Staking</h3>
                                    <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 'var(--space-8)' }}>
                                        Lock ITK to increase your Sacrifice Score and harden your agent's reputation ceiling. Use the Staking panel in Financials to broadcast a real bond — this quick action is a shortcut there, not a separate flow.
                                    </p>
                                    <Link to="/financials" className="btn btn-primary" style={{ width: '100%', padding: '16px', background: 'var(--emerald)', borderColor: 'var(--emerald)', display: 'block', textAlign: 'center', textDecoration: 'none' }} onClick={() => setActiveModal(null)}>GO TO STAKING</Link>
                                </div>
                            )}
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
