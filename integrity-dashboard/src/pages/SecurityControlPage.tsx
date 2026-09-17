import { useState } from 'react';
import { GitCompare, Network, ShieldCheck } from 'lucide-react';
import { ControlHeader } from '../components/control/ControlHeader';
import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';
import KernelPage from './KernelPage';
import KernelIntentPage from './KernelIntentPage';
import { AgentRiskContext } from '../components/control/AgentRiskContext';

// Cross-system correlation (oracle intents + Shield decisions + Cortex invocations) lives
// in exactly one place now: Knowledge & Evidence's "evidence" tab (CorrelationPage). This
// page used to embed a second copy of it; removed rather than duplicated.
type SecurityTab = 'kernel' | 'actions';
const TABS: ControlTab<SecurityTab>[] = [
  { id: 'kernel', label: 'Policy & guardians', icon: Network },
  { id: 'actions', label: 'Intent review', icon: GitCompare },
];

export default function SecurityControlPage({ initialTab = 'kernel' }: { initialTab?: SecurityTab }) {
  const [tab, setTab] = useState<SecurityTab>(initialTab);
  return (
    <div className="control-page control-page-full">
      <ControlHeader eyebrow="Enforcement plane" title="Security & Policy" description="Monitor endpoint posture, configure policy boundaries, and review agent actions before and after execution." />
      <ControlTabs tabs={TABS} active={tab} onChange={setTab} label="Security control views" />
      <AgentRiskContext purpose="security" />
      <div className="control-hub-content">
        {tab === 'kernel' && <KernelPage />}
        {tab === 'actions' && <KernelIntentPage />}
      </div>
    </div>
  );
}
