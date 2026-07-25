// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    Landmark, LandmarkIcon, Coins, TrendingDown, ShieldCheck, 
    ArrowUpRight, Info, Loader2, Wallet, Banknote
} from 'lucide-react';

export const ReputationMarket = ({ selectedAgent }: { selectedAgent: any }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [marketStats, setMarketStats] = useState({
        totalLiquidity: 1250000,
        avgRate: 4.2
    });

    // Borrowing potential logic
    const ais = selectedAgent?.current_ais || 300;
    const ltv = ais < 600 ? 0 : 50 + ((ais - 600) * 40 / 400);
    const interestRate = ais < 600 ? 0 : 10 - ((ais - 600) * 8 / 400);

    return (
        <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="enterprise-card"
            style={{ padding: '32px', background: 'rgba(16, 185, 129, 0.02)', border: '1px solid rgba(16, 185, 129, 0.1)' }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
                        <LandmarkIcon size={20} />
                    </div>
                    <div>
                        <h3 style={{ fontSize: '1.1rem', fontWeight: 800, margin: 0 }}>Reputation Market</h3>
                        <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>REPUTATION-BASED DEFI POOL</div>
                    </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Pool Liquidity</div>
                    <div style={{ fontSize: '1rem', fontWeight: 900, color: '#10b981' }}>{marketStats.totalLiquidity.toLocaleString()} ITK</div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '32px' }}>
                <div style={{ padding: '20px', background: 'rgba(0,0,0,0.2)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <TrendingDown size={14} style={{ color: '#10b981' }} />
                        <span style={{ fontSize: '0.6rem', fontWeight: 800, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Your APR</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                        <span style={{ fontSize: '1.8rem', fontWeight: 900, color: 'white' }}>{interestRate === 0 ? '---' : interestRate.toFixed(2)}</span>
                        <span style={{ fontSize: '0.8rem', fontWeight: 800, color: '#10b981' }}>%</span>
                    </div>
                    <div style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.2)', marginTop: '8px' }}>Based on {ais} AIS</div>
                </div>

                <div style={{ padding: '20px', background: 'rgba(0,0,0,0.2)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <ShieldCheck size={14} style={{ color: '#10b981' }} />
                        <span style={{ fontSize: '0.6rem', fontWeight: 800, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Max LTV</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                        <span style={{ fontSize: '1.8rem', fontWeight: 900, color: 'white' }}>{ltv === 0 ? '---' : ltv.toFixed(0)}</span>
                        <span style={{ fontSize: '0.8rem', fontWeight: 800, color: '#10b981' }}>%</span>
                    </div>
                    <div style={{ fontSize: '0.55rem', color: 'rgba(255,255,255,0.2)', marginTop: '8px' }}>Collateral Boost active</div>
                </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '24px', borderRadius: '20px', border: '1px dashed rgba(255,255,255,0.1)', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                    <Banknote size={18} style={{ color: 'rgba(255,255,255,0.4)' }} />
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'white' }}>Borrow Liquidity</span>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <div style={{ flex: 1, background: 'rgba(0,0,0,0.3)', padding: '12px 16px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: 800, color: 'white' }}>0.00</span>
                        <span style={{ fontSize: '0.65rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)' }}>ITK</span>
                    </div>
                    <button 
                        disabled={ais < 600 || isLoading}
                        onClick={async () => {
                            setIsLoading(true);
                            // Simulate blockchain delay
                            await new Promise(r => setTimeout(r, 2000));
                            alert("Transaction Dispatched to Base Sepolia!");
                            setIsLoading(false);
                        }}
                        className="btn btn-primary" 
                        style={{ background: '#10b981', border: 'none', padding: '0 24px', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        {isLoading ? <Loader2 className="animate-spin" size={18} /> : 'BORROW'}
                    </button>
                </div>
                {ais < 600 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '12px' }}>
                        <Info size={12} color="#ef4444" />
                        <span style={{ fontSize: '0.6rem', color: '#ef4444', fontWeight: 700 }}>MINIMUM 600 AIS REQUIRED TO BORROW</span>
                    </div>
                )}
            </div>

            <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', lineHeight: 1.5 }}>
                <p>Reputation Lending allows Tier 2+ agents to access liquidity without full collateralization. Interest rates are algorithmically adjusted based on real-time performance entropy and grounding scores.</p>
            </div>
        </motion.div>
    );
};
