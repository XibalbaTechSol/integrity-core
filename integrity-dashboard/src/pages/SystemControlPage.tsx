import { useState } from 'react';
import { Activity, ShieldCheck, FileKey2, BookOpen, Settings } from 'lucide-react';
import { SubTabs } from '../components/ui/SubTabs';
import HealthPage from './HealthPage';
import KernelPage from './KernelPage';
import LicencePage from './LicencePage';
import WikiPage from './WikiPage';
import SettingsPage from './SettingsPage';

const TABS = [
  { id: 'health', label: 'Health', icon: <Activity size={14} /> },
  { id: 'kernel', label: 'Kernel', icon: <ShieldCheck size={14} /> },
  { id: 'licence', label: 'Licence', icon: <FileKey2 size={14} /> },
  { id: 'wiki', label: 'Wiki', icon: <BookOpen size={14} /> },
  { id: 'settings', label: 'Settings', icon: <Settings size={14} /> },
];

export default function SystemControlPage() {
  const [tab, setTab] = useState('health');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <SubTabs tabs={TABS} activeTab={tab} setActiveTab={setTab} />
      <div style={{ marginTop: 'var(--space-2)' }}>
        {tab === 'health' && <HealthPage />}
        {tab === 'kernel' && <KernelPage />}
        {tab === 'licence' && <LicencePage />}
        {tab === 'wiki' && <WikiPage />}
        {tab === 'settings' && <SettingsPage />}
      </div>
    </div>
  );
}
