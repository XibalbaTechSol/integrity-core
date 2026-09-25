/* eslint-disable @typescript-eslint/no-unused-vars */
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
import { FleetWalletOverview } from '../components/ui/FleetWalletOverview';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import { AgentRiskContext } from '../components/control/AgentRiskContext';

// ─── Sub-nav tabs ─────────────────────────────────────────────────────────────
type FinanceTab = 'wallet' | 'staking' | 'credit' | 'markets' | 'stability';

const TABS: ControlTab<FinanceTab>[] = [
  { id: 'wallet',    label: 'Wallet',    icon: Wallet },
  { id: 'staking',   label: 'Staking',   icon: Lock },
  { id: 'credit',    label: 'Credit',    icon: DollarSign },
  { id: 'markets',   label: 'Markets',   icon: ShoppingCart },
  { id: 'stability', label: 'Stability', icon: BarChart2 },
];

// ─── Stat card ────────────────────────────────────────────────────────────────
// ─── Animation config ─────────────────────────────────────────────────────────
const sectionVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.18, ease: 'easeIn' } },
} as any;

// ─── FinancePage ──────────────────────────────────────────────────────────────
export default function TreasuryControlPage() {
  const { stats } = useDashboard() as any;
  const [activeTab, setActiveTab] = useState<FinanceTab>('wallet');

  // ── Stat strip values ──
  const tvl        = stats?.tvl                     ?? 0;
  const totalLoans = stats?.total_loans_volume       ?? 0;
  const stakedItk  = stats?.protocol_staked_itk      ?? 0;
  const marketVol  = stats?.total_marketplace_volume ?? 0;

  return (
    <div className="control-page control-page-full treasury-page">
      <ControlHeader
        eyebrow="Wallet and financial control"
        title="Wallet & Finance"
        description="One dedicated surface for operator wallets, agent-linked capital, staking, credit, markets, and stability controls."
      />
      <ControlTabs tabs={TABS} active={activeTab} onChange={setActiveTab} label="Treasury control views" />
      <div className="control-metric-grid treasury-metric-grid" aria-label="Treasury metrics">
        <div className="control-metric"><span><DollarSign size={14} /> Total value locked</span><strong>{tvl.toLocaleString()}</strong><small>Protocol TVL</small></div>
        <div className="control-metric"><span><TrendingUp size={14} /> Loan volume</span><strong>{totalLoans.toLocaleString()}</strong><small>Total issued volume</small></div>
        <div className="control-metric"><span><Lock size={14} /> Staked ITK</span><strong>{stakedItk.toLocaleString()}</strong><small>Protocol stake</small></div>
        <div className="control-metric"><span><ShoppingCart size={14} /> Market volume</span><strong>{marketVol.toLocaleString()}</strong><small>Marketplace volume</small></div>
      </div>
      <div className="control-page-body treasury-page-body">
        <AgentRiskContext purpose="funds" />
        <div className="control-hub-content">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            {activeTab === 'wallet' && (
              <>
                <FleetWalletOverview />
                <TokenWallet />
              </>
            )}
            {activeTab === 'staking' && <StakingPanel />}
            {activeTab === 'credit' && <CreditPanel />}
            {activeTab === 'markets' && <ActuarialHub mode="markets" />}
            {activeTab === 'stability' && <ActuarialHub mode="stability" />}
          </motion.div>
        </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
