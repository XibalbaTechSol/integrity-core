import re

with open("src/pages/ProtocolDashboardPage.tsx", "r") as f:
    protocol = f.read()

if "import { SubTabs }" not in protocol:
    protocol = protocol.replace("import { useDashboard }", "import { SubTabs } from '../components/ui/SubTabs';\nimport { useDashboard }")

# Replace routeTab logic with local state
route_logic = """const [routeTab, setRouteTab] = useState('overview');
  const tab = routeTab === 'identity' ? 'identity' : ['records', 'proofs', 'activity'].includes(routeTab) ? 'evidence' : ['transactions', 'security'].includes(routeTab) ? 'wallets' : routeTab as 'overview' | 'wallets' | 'contracts';
"""
protocol = re.sub(r"const routeTab: Tab = location.pathname.*?;(\r?\n)?\s*// Reuse.*?explicit and discoverable.(\r?\n)?\s*const tab: .*? 'contracts';", route_logic, protocol, flags=re.DOTALL)

# Insert SubTabs just inside .protocol-content
tabs_component = """
      <div className="protocol-content">
        <SubTabs 
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'identity', label: 'Identity & Trust' },
            { id: 'contracts', label: 'Contracts' },
            { id: 'wallets', label: 'Wallets' },
            { id: 'evidence', label: 'Evidence' }
          ]} 
          activeTab={tab} 
          setActiveTab={(id) => setRouteTab(id)} 
        />
"""
protocol = protocol.replace('<div className="protocol-content">', tabs_component)

with open("src/pages/ProtocolDashboardPage.tsx", "w") as f:
    f.write(protocol)
print("Patched ProtocolDashboardPage")
