import { useState, useEffect } from 'react';
import { TopBar } from '../components/TopBar';
import { ArrowDownToLine, Send, Repeat, Plus, History, Wallet, Cpu, ShieldAlert, MoreHorizontal, XCircle } from 'lucide-react';
import { ActuarialHub } from '../components/ActuarialHub';
import { MarketsEscrowPanel } from '../components/finance/MarketsEscrowPanel';
import { useAgent } from '../contexts/AgentContext';
import { oracle, type TransactionDto } from '../services/oracle';
import { SeededDataBadge } from '../shared/SeededDataBadge';
import { AreaChart, Area, ResponsiveContainer, YAxis, Tooltip } from 'recharts';
import { useAccount } from 'wagmi';
import { formatUnits } from 'viem';
import { activeChain } from '../chain/wagmi';

// Mock data for wallet
const ASSETS = [
  { symbol: 'ETH', name: 'Ethereum', balance: '4.205', usdPrice: 3450.20, change24h: 2.4, color: '#627EEA' },
  { symbol: 'ITK', name: 'Integrity', balance: '12500', usdPrice: 1.25, change24h: 12.5, color: 'var(--color-brand-primary)' },
  { symbol: 'USDC', name: 'USD Coin', balance: '8450.00', usdPrice: 1.00, change24h: 0.01, color: '#2775CA' },
];

const PORTFOLIO_HISTORY = [
  { date: 'Mon', value: 24500 },
  { date: 'Tue', value: 26100 },
  { date: 'Wed', value: 25800 },
  { date: 'Thu', value: 28400 },
  { date: 'Fri', value: 29100 },
  { date: 'Sat', value: 30500 },
  { date: 'Sun', value: 31250 }
];

const TRANSACTIONS: TransactionDto[] = [
  { id: 'tx-1', type: 'Send', asset: 'ITK', amount: '-500', usd: '-$625.00', agent: 'mock-agent-alpha', status: 'Success', time: '2m ago' },
  { id: 'tx-2', type: 'Receive', asset: 'ETH', amount: '+1.5', usd: '+$5,175.30', agent: 'Human (You)', status: 'Success', time: '1h ago' },
  { id: 'tx-3', type: 'Swap', asset: 'USDC → ITK', amount: '1000 USDC', usd: null, agent: 'mock-agent-beta', status: 'Success', time: '5h ago' },
  { id: 'tx-4', type: 'Contract Deploy', asset: 'ETH', amount: '-0.02', usd: '-$69.00', agent: 'mock-agent-alpha', status: 'Success', time: '1d ago' },
  { id: 'tx-5', type: 'Send', asset: 'ITK', amount: '-10000', usd: '-$12,500.00', agent: 'mock-agent-gamma', status: 'Blocked (Limit)', time: '2d ago' },
];

const ALLOWANCES = [
  { agent: 'mock-agent-alpha', limit: '1000 ITK / week', spent: 500, status: 'Active' },
  { agent: 'mock-agent-beta', limit: '0.5 ETH / month', spent: 0.1, status: 'Active' },
  { agent: 'mock-agent-gamma', limit: '500 USDC / day', spent: 500, status: 'Exhausted' },
];

export const FinancePage = () => {
  const [activeTab, setActiveTab] = useState<'wallet' | 'markets' | 'stability'>('wallet');
  const { selectedAgent } = useAgent();
  const { address } = useAccount();
  const explorerUrl = activeChain.blockExplorers?.default.url;
  const [itkBalance, setItkBalance] = useState<string | null>(null);
  const [transactions, setTransactions] = useState(TRANSACTIONS);
  const [allowances, setAllowances] = useState(ALLOWANCES);

  useEffect(() => {
    if (!selectedAgent) return;
    let cancelled = false;
    oracle.getWallet(selectedAgent.id).then(w => { 
        if (!cancelled) {
            setItkBalance(w.itk_balance);
            if (w.transaction_history) setTransactions(w.transaction_history);
            if (w.allowances) setAllowances(w.allowances);
        }
    }).catch(() => { 
        if (!cancelled) setItkBalance(null); 
    });
    return () => { cancelled = true; };
  }, [selectedAgent]);

  // If we have live ITK balance, merge it into our ASSETS mock. `itk_balance` from
  // GET /v1/agent/{id}/wallet is the raw on-chain U256 wei string (18 decimals, same
  // as the ERC-20 IntegrityToken contract) — must be scaled down before display.
  const displayAssets = ASSETS.map(a => {
    if (a.symbol === 'ITK' && itkBalance) {
      return { ...a, balance: Number(formatUnits(BigInt(itkBalance), 18)).toLocaleString() };
    }
    return a;
  });

  const totalUsdValue = displayAssets.reduce((sum, asset) => {
    return sum + (parseFloat(asset.balance.replace(/,/g, '')) * asset.usdPrice);
  }, 0);

  return (
    <div className="main-content" style={{ backgroundColor: 'var(--bg-main)', minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar title="Shared Agent Crypto Wallet" />
      
      <div style={{ padding: '0 24px', display: 'flex', gap: '24px', borderBottom: '1px solid var(--border-color)', marginBottom: '16px', flexShrink: 0 }}>
        {[
          { id: 'wallet', label: 'Wallet & Portfolio' },
          { id: 'markets', label: 'A2A Markets & Escrow' },
          { id: 'stability', label: 'Stability & Certification' }
        ].map(tab => (
          <div 
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{ 
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
              borderBottom: activeTab === tab.id ? '2px solid var(--accent-primary)' : '2px solid transparent',
              paddingBottom: '12px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: activeTab === tab.id ? 600 : 400,
              transition: 'all 0.2s ease'
            }}
          >
            {tab.label}
          </div>
        ))}
      </div>

      <div className="custom-scrollbar" style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px 24px' }}>
        
        {activeTab === 'wallet' && (
          <div style={{ maxWidth: '1000px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            {/* HERO WALLET SECTION */}
            <div className="card" style={{ padding: '40px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', background: 'linear-gradient(180deg, rgba(20,20,22,1) 0%, rgba(30,30,35,1) 100%)', border: '1px solid var(--border-color)', position: 'relative', overflow: 'hidden' }}>
              {/* Subtle background glow */}
              <div style={{ position: 'absolute', top: '-50px', left: '50%', transform: 'translateX(-50%)', width: '200px', height: '100px', background: 'var(--accent-primary)', filter: 'blur(80px)', opacity: 0.15, borderRadius: '50%' }}></div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 12px', background: 'var(--bg-surface)', borderRadius: '20px', border: '1px solid var(--border-color)', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)' }}></div>
                Base L2 Network
                <div style={{ width: '1px', height: '12px', background: 'var(--border-color)', margin: '0 4px' }}></div>
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  {address ? `${address.slice(0, 6)}...${address.slice(-4)}` : 'Not connected'}
                </span>
              </div>

              <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 600, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '8px' }}>
                TOTAL PORTFOLIO VALUE
                <SeededDataBadge label="ETH/USDC balances, prices & trend are seeded — only ITK is real" />
              </div>
              <div style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ color: 'var(--text-muted)' }}>$</span>
                {totalUsdValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={{ color: 'var(--success)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '32px' }}>
                + $1,240.50 (4.2%) <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Today (seeded)</span>
              </div>

              {/* TREND CHART — seeded, no historical portfolio-value endpoint exists */}
              <div style={{ width: '100%', height: '120px', marginBottom: '40px', marginTop: '-10px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={PORTFOLIO_HISTORY} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <YAxis domain={['dataMin - 1000', 'dataMax + 1000']} hide />
                    <Tooltip 
                        contentStyle={{ backgroundColor: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
                        itemStyle={{ color: 'var(--text-primary)' }}
                        formatter={(value: any) => [`$${Number(value).toLocaleString()}`, 'Portfolio Value']}
                    />
                    <Area type="monotone" dataKey="value" stroke="var(--accent-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* ACTION BUTTONS */}
              <div style={{ display: 'flex', gap: '24px' }}>
                {[
                  { icon: <ArrowDownToLine size={20} />, label: 'Receive', color: 'var(--accent-primary)', reason: 'No wallet-address / QR display is wired yet.' },
                  { icon: <Send size={20} />, label: 'Send', color: 'var(--text-primary)', reason: 'No real transfer transaction is wired yet.' },
                  { icon: <Repeat size={20} />, label: 'Swap', color: 'var(--text-primary)', reason: 'No DEX/swap integration exists anywhere in this stack.' },
                  { icon: <Plus size={20} />, label: 'Buy', color: 'var(--text-primary)', reason: 'No fiat on-ramp integration exists anywhere in this stack.' },
                ].map((action, i) => (
                  <div
                    key={i}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'not-allowed', opacity: 0.5 }}
                    title={`Not yet implemented: ${action.reason}`}
                  >
                    <div style={{ width: '48px', height: '48px', borderRadius: '24px', background: action.color === 'var(--accent-primary)' ? 'var(--accent-primary)' : 'var(--bg-surface)', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: action.color === 'var(--accent-primary)' ? '#000' : 'var(--text-primary)' }}>
                      {action.icon}
                    </div>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>{action.label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px' }}>
              
              {/* ASSETS LIST */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <div className="card">
                  <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                    <Wallet size={18} /> Tokens & Assets
                  </h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {displayAssets.map((asset, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', border: '1px solid transparent', cursor: 'pointer', transition: 'border 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.border = '1px solid var(--border-color)'} onMouseLeave={(e) => e.currentTarget.style.border = '1px solid transparent'}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: asset.color, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: '14px', boxShadow: '0 4px 12px rgba(0,0,0,0.2)' }}>
                            {asset.symbol.substring(0, 3)}
                          </div>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {asset.name}
                              {asset.symbol !== 'ITK' && <SeededDataBadge label="No ETH/USDC balance or price-feed endpoint exists yet" />}
                            </div>
                            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{asset.balance} {asset.symbol}</div>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontWeight: 700, fontSize: '15px' }}>${(parseFloat(asset.balance.replace(/,/g, '')) * asset.usdPrice).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div style={{ fontSize: '13px', color: asset.change24h >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                            {asset.change24h >= 0 ? '+' : ''}{asset.change24h}%
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* TRANSACTION HISTORY */}
                <div className="card">
                  <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                    <History size={18} /> Recent Activity
                    {/* Real when GET /v1/agent/{id}/wallet returns transaction_history for the
                        selected agent; falls back to this seeded list when it doesn't. */}
                    {transactions === TRANSACTIONS && <SeededDataBadge label="No real transaction history for this agent yet" />}
                  </h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {transactions.map((tx, i) => (
                      <div key={tx.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 0', borderBottom: i < transactions.length - 1 ? '1px solid var(--border-color)' : 'none' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-primary)' }}>
                            {tx.type === 'Send' || tx.type === 'Contract Deploy' ? <ArrowDownToLine size={16} style={{ transform: 'rotate(180deg)' }} /> : tx.type === 'Receive' ? <ArrowDownToLine size={16} /> : <Repeat size={16} />}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              {tx.type} {tx.asset}
                              {tx.status === 'Blocked (Limit)' && <ShieldAlert size={14} color="var(--danger)" />}
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Cpu size={12} /> {tx.agent} • {tx.time}
                            </div>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontWeight: 600, fontSize: '14px', color: tx.status === 'Blocked (Limit)' ? 'var(--text-muted)' : 'var(--text-primary)', textDecoration: tx.status === 'Blocked (Limit)' ? 'line-through' : 'none' }}>
                            {tx.amount}
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{tx.status === 'Success' ? tx.usd : tx.status}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <button
                    className="btn btn-outline"
                    style={{ width: '100%', marginTop: '16px', fontSize: '13px' }}
                    disabled={!explorerUrl || !address}
                    onClick={() => explorerUrl && address && window.open(`${explorerUrl}/address/${address}`, '_blank', 'noopener,noreferrer')}
                    title={!address ? 'Connect a wallet first' : !explorerUrl ? `No block explorer configured for ${activeChain.name}` : `Open ${activeChain.name} explorer for ${address}`}
                  >
                    View Explorer
                  </button>
                </div>
              </div>

              {/* AGENT ALLOWANCES PANEL */}
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="card" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <h2 className="card-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldAlert size={18} /> Agent Allowances
                    </h2>
                    <SeededDataBadge />
                  </div>
                  
                  <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '20px', lineHeight: 1.5 }}>
                    Manage spend limits for autonomous agents operating from this shared treasury.
                  </p>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {allowances.map((allowance, i) => {
                      const limitNum = parseFloat(allowance.limit.split(' ')[0]);
                      const percentage = Math.min((allowance.spent / limitNum) * 100, 100);
                      const isExhausted = allowance.status === 'Exhausted';

                      return (
                        <div key={i} style={{ padding: '16px', background: 'var(--bg-main)', borderRadius: 'var(--radius-md)', border: isExhausted ? '1px solid var(--danger)' : '1px solid var(--border-color)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600 }}>
                              <Cpu size={14} color="var(--primary)" /> {allowance.agent}
                            </div>
                            <MoreHorizontal size={16} color="var(--text-muted)" style={{ cursor: 'pointer' }} />
                          </div>
                          
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '8px' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Limit: {allowance.limit}</span>
                            <span style={{ fontWeight: 600, color: isExhausted ? 'var(--danger)' : 'var(--text-primary)' }}>{allowance.spent} spent</span>
                          </div>

                          {/* Progress Bar */}
                          <div style={{ width: '100%', height: '6px', background: 'var(--bg-panel)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div style={{ width: `${percentage}%`, height: '100%', background: isExhausted ? 'var(--danger)' : 'var(--accent-primary)' }}></div>
                          </div>
                          
                          {isExhausted && (
                            <div style={{ marginTop: '12px', fontSize: '12px', color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <XCircle size={12} /> Limit Reached. Transactions Blocked.
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <button
                    className="btn btn-secondary"
                    style={{ width: '100%', marginTop: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', opacity: 0.5, cursor: 'not-allowed' }}
                    disabled
                    title="OPA policies (bcc_middleware/policies/*.rego) are static files today, not dynamically editable via a UI -- there is no backend to create a new allowance rule against."
                  >
                    <Plus size={16} /> New Allowance Rule
                  </button>
                </div>
              </div>

            </div>
          </div>
        )}

        {activeTab === 'markets' && <MarketsEscrowPanel />}
        {activeTab === 'stability' && <ActuarialHub mode="stability" />}

      </div>
    </div>
  );
};
