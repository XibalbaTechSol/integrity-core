import re

with open("src/pages/IntelligenceControlPage.tsx", "r") as f:
    intel = f.read()

# Replace ControlTabs with SubTabs
intel = intel.replace("import { ControlTabs, type ControlTab } from '../components/control/ControlTabs';", "import { SubTabs } from '../components/ui/SubTabs';")
intel = intel.replace("import { ControlHeader } from '../components/control/ControlHeader';", "")

# Update the TABS definition
intel = re.sub(r"const TABS: ControlTab<KnowledgeTab>\[\] = \[.*?\];", """const TABS = [
  { id: 'overview', label: 'AIS & knowledge', icon: <Sparkles size={14} /> },
  { id: 'intelligence', label: 'Agent intelligence', icon: <Activity size={14} /> },
  { id: 'evidence', label: 'Evidence correlation', icon: <GitMerge size={14} /> },
];""", intel, flags=re.DOTALL)

# Update rendering logic
render_logic = """export default function IntelligenceControlPage() {
  const [tab, setTab] = useState('overview');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <SubTabs tabs={TABS} activeTab={tab} setActiveTab={setTab} />
      <div style={{ marginTop: 'var(--space-2)' }}>
        {tab === 'overview' && <KnowledgeOverview />}
        {tab === 'intelligence' && <IntelligencePage />}
        {tab === 'evidence' && <CorrelationPage />}
      </div>
    </div>
  );
}"""
intel = re.sub(r'export default function IntelligenceControlPage\(\) \{.*', render_logic, intel, flags=re.DOTALL)

with open("src/pages/IntelligenceControlPage.tsx", "w") as f:
    f.write(intel)
print("Patched IntelligenceControlPage")
