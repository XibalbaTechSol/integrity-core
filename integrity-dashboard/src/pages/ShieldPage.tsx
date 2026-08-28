import { useState } from 'react';
import { Server, FlaskConical } from 'lucide-react';
import { SubTabs, type TabItem } from '../components/ui/SubTabs';
import ShieldFleetOverview from '../components/shield/ShieldFleetOverview';
import ShieldAttackSimulator from '../components/shield/ShieldAttackSimulator';

// Xibalba Shield: the AI agent security platform (see xibalba-shield/CLAUDE.md) -- a
// fleet-level enforcement/detection product (real devices, real OPA/SLM decisions, real
// SIEM/SOAR export), not a single-machine attack demo. Fleet Overview (real backend data) is
// the default tab; the live attack simulator is a secondary, clearly-labeled optional demo of
// the Tier-2 SLM escalation path.
type ShieldTab = 'fleet' | 'simulator';

const TABS: TabItem[] = [
  { id: 'fleet', label: 'Fleet Overview', icon: <Server size={16} /> },
  { id: 'simulator', label: 'Live Attack Demo', icon: <FlaskConical size={16} /> },
];

export default function ShieldPage() {
  const [activeTab, setActiveTab] = useState<ShieldTab>('fleet');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <SubTabs tabs={TABS} activeTab={activeTab} setActiveTab={(id) => setActiveTab(id as ShieldTab)} />
      <div style={{ padding: 'var(--space-4)' }}>
        {activeTab === 'fleet' && <ShieldFleetOverview />}
        {activeTab === 'simulator' && <ShieldAttackSimulator />}
      </div>
    </div>
  );
}
