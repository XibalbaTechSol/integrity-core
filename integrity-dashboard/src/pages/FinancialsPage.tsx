import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DollarSign,
  TrendingUp,
  Lock,
  ShoppingCart,
  BarChart2,
  Wallet,
} from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { Panel } from '../components/shared/Panel';
import { StakingPanel } from '../components/tabs/StakingPanel';
import { CreditPanel } from '../components/tabs/CreditPanel';
import { ActuarialHub } from '../components/tabs/ActuarialHub';
import { TokenWallet } from '../components/ui/TokenWallet';
import { SubTabs } from '../components/ui/SubTabs';

// ─── Sub-nav tabs ─────────────────────────────────────────────────────────────
type FinanceTab = 'wallet' | 'staking' | 'credit' | 'markets' | 'stability';

const TABS: { id: FinanceTab; label: string; icon: React.ReactNode }[] = [
  { id: 'wallet',    label: 'Wallet',    icon: <Wallet       size={14} /> },
  { id: 'staking',   label: 'Staking',   icon: <Lock         size={14} /> },
  { id: 'credit',    label: 'Credit',    icon: <DollarSign   size={14} /> },
  { id: 'markets',   label: 'Markets',   icon: <ShoppingCart size={14} /> },
  { id: 'stability', label: 'Stability', icon: <BarChart2    size={14} /> },
];

// ─── Stat card ────────────────────────────────────────────────────────────────
interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
}

function StatCard({ icon, label, value }: StatCardProps) {
  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        flex: 1,
        minWidth: 0,
      }}
    >
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--primary-dim)',
          border: '1px solid var(--primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--primary)',
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: '0.7rem',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            marginBottom: '2px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {label}
        </div>
        <div
          style={{
            fontSize: '1.25rem',
            fontWeight: 700,
            color: 'var(--theme-accent)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {value}
        </div>
      </div>
    </div>
  );
}



// ─── Animation config ─────────────────────────────────────────────────────────
const sectionVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.18, ease: 'easeIn' } },
} as any;

// ─── FinancePage ──────────────────────────────────────────────────────────────
export default function FinancialsPage() {
  const { stats } = useDashboard() as any;
  const [activeTab, setActiveTab] = useState<FinanceTab>('wallet');

  // ── Stat strip values ──
  const tvl        = stats?.tvl                     ?? 0;
  const totalLoans = stats?.total_loans_volume       ?? 0;
  const stakedItk  = stats?.protocol_staked_itk      ?? 0;
  const marketVol  = stats?.total_marketplace_volume ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>



      {/* ── 4-stat strip ─────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
        <StatCard icon={<DollarSign   size={18} />} label="TVL"               value={tvl.toLocaleString()} />
        <StatCard icon={<TrendingUp   size={18} />} label="Total Loan Volume" value={totalLoans.toLocaleString()} />
        <StatCard icon={<Lock         size={18} />} label="Staked ITK"        value={stakedItk.toLocaleString()} />
        <StatCard icon={<ShoppingCart size={18} />} label="Market Volume"     value={marketVol.toLocaleString()} />
      </div>

      {/* ── Sub-navigation Tab Bar ───────────────────────────────────────── */}
      <div style={{ marginBottom: '16px', marginTop: '16px' }}>
        <SubTabs tabs={TABS as any} activeTab={activeTab} setActiveTab={setActiveTab as any} />
      </div>

      {/* ── Section content (Tabbed Component Mount) ────────────────────── */}
      <div style={{ marginTop: 'var(--space-2)' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            {activeTab === 'wallet' && <TokenWallet />}
            {activeTab === 'staking' && <StakingPanel />}
            {activeTab === 'credit' && <CreditPanel />}
            {activeTab === 'markets' && <ActuarialHub mode="markets" />}
            {activeTab === 'stability' && <ActuarialHub mode="stability" />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
