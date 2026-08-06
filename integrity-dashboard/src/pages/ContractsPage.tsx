import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDashboard } from '../context/useDashboard';
import { Panel } from '../components/shared/Panel';
import { FactoryPanel } from '../components/tabs/FactoryPanel';
import { ZKProverPanel } from '../components/tabs/ZKProverPanel';
import { OracleRegistryPanel } from '../components/tabs/OracleRegistryPanel';
import { ImmutableLedger } from '../components/ui/ImmutableLedger';
import { VisualTopologyMap } from '../components/ui/VisualTopologyMap';
import {
  Code2,
  Shield,
  Database,
  Layers,
  FileCode,
  Activity,
  Network
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

type ProtocolTab = 'map' | 'factory' | 'zk' | 'oracle' | 'ledger';

interface TabConfig {
  id: ProtocolTab;
  icon: React.ReactNode;
  label: string;
}

// ─── Sub-components ──────────────────────────────────────────────────────────

const StatCard = ({
  label,
  value,
  icon,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
}) => (
  <div
    style={{
      flex: 1,
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-4)',
      padding: 'var(--space-4) var(--space-5)',
      background: 'var(--bg-card)',
      border: '1px solid var(--glass-border)',
      borderRadius: 'var(--radius-md)',
    }}
  >
    <div
      style={{
        width: '40px',
        height: '40px',
        borderRadius: 'var(--radius-sm)',
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
    <div>
      <div
        style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          color: 'var(--text-primary)',
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          marginTop: '4px',
          letterSpacing: '0.04em',
          textTransform: 'uppercase' as const,
        }}
      >
        {label}
      </div>
    </div>
  </div>
);

// ─── Sub-nav tabs ─────────────────────────────────────────────────────────────
const TABS: { id: ProtocolTab; label: string; icon: React.ReactNode }[] = [
  { id: 'map',     label: 'Topology Map', icon: <Network size={14} /> },
  { id: 'factory', label: 'Factory', icon: <FileCode size={14} /> },
  { id: 'zk',      label: 'ZK Prover', icon: <Shield size={14} /> },
  { id: 'oracle',  label: 'Oracle', icon: <Database size={14} /> },
  { id: 'ledger',  label: 'Ledger', icon: <Layers size={14} /> },
];

// ─── Main Page ────────────────────────────────────────────────────────────────

export function ContractsPage() {
  const { stats, activeTab, setActiveTab } = useDashboard() as any;

  const totalContracts = stats?.total_contracts ?? '—';
  const activeNodes = stats?.active_nodes ?? '—';
  const activeDisputes = stats?.active_disputes ?? '—';

  const isFactory = activeTab === 'factory';
  
  // Set default tab if not set or invalid
  const currentTab = TABS.some(t => t.id === activeTab) ? activeTab : 'map';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: isFactory ? '0' : 'var(--space-6)',
        padding: isFactory ? '0' : 'var(--space-6)',
        flex: isFactory ? 1 : undefined,
        minHeight: '100%',
      }}
    >
      {/* ── 3-stat strip ── */}
      {!isFactory && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.06, ease: 'easeOut' }}
          style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}
        >
          <StatCard
            label="Total Contracts"
            value={totalContracts}
            icon={<FileCode size={18} />}
          />
          <StatCard
            label="Active Nodes"
            value={activeNodes}
            icon={<Database size={18} />}
          />
          <StatCard
            label="Active Disputes"
            value={activeDisputes}
            icon={<Shield size={18} />}
          />
        </motion.div>
      )}

      {/* ── Tab Switcher for non-factory tab modes ── */}
      {!isFactory && (
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '8px' }}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                background: currentTab === tab.id ? 'var(--primary-dim)' : 'transparent',
                border: `1px solid ${currentTab === tab.id ? 'var(--primary)' : 'transparent'}`,
                borderRadius: 'var(--radius-sm)',
                color: currentTab === tab.id ? 'var(--primary)' : 'var(--text-muted)',
                fontSize: '0.8rem',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* ── Section Content (Tabbed) ── */}
      <div style={{ marginTop: isFactory ? 0 : 'var(--space-2)', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={currentTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
          >
            {currentTab === 'map' && (
              <VisualTopologyMap />
            )}

            {currentTab === 'factory' && (
              <FactoryPanel />
            )}

            {currentTab === 'oracle' && (
              <Panel
                title="Oracle Registry"
                icon={<Database size={18} />}
                style={{ background: 'transparent', border: 'none', padding: 0 } as React.CSSProperties}
              >
                <OracleRegistryPanel />
              </Panel>
            )}

            {currentTab === 'zk' && <ZKProverPanel />}

            {currentTab === 'ledger' && (
              <Panel title="Immutable Settlement Ledger" icon={<Layers size={18} />}>
                <ImmutableLedger />
              </Panel>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
