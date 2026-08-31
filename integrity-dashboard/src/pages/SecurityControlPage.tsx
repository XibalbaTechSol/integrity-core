import { useState } from 'react';
import { GitCompare, GitMerge, Network, ShieldCheck } from 'lucide-react';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import ShieldPage from './ShieldPage';
import KernelPage from './KernelPage';
import KernelIntentPage from './KernelIntentPage';
import { AgentRiskContext } from '../components/control/AgentRiskContext';
import CorrelationPage from './CorrelationPage';

type SecurityTab = 'shield' | 'kernel' | 'actions' | 'correlation';
const TABS: ControlTab<SecurityTab>[] = [
  { id: 'shield', label: 'Endpoints & devices', icon: ShieldCheck },
  { id: 'kernel', label: 'Policy & guardians', icon: Network },
  { id: 'actions', label: 'Intent review', icon: GitCompare },
  { id: 'correlation', label: 'Correlation evidence', icon: GitMerge },
];

export default function SecurityControlPage({ initialTab = 'shield' }: { initialTab?: SecurityTab }) {
  const [tab, setTab] = useState<SecurityTab>(initialTab);
  return (
    <div className="control-page control-page-full">
      <ControlHeader eyebrow="Enforcement plane" title="Security & Policy" description="Monitor endpoint posture, configure policy boundaries, and review agent actions before and after execution." />
      <ControlTabs tabs={TABS} active={tab} onChange={setTab} label="Security control views" />
      <AgentRiskContext purpose="security" />
      <div className="control-hub-content">
        {tab === 'shield' && <ShieldPage />}
        {tab === 'kernel' && <KernelPage />}
        {tab === 'actions' && <KernelIntentPage />}
        {tab === 'correlation' && <CorrelationPage />}
      </div>
    </div>
  );
}
