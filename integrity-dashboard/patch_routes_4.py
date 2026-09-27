import re

with open('src/App.tsx', 'r') as f:
    app = f.read()

imports_to_add = "import SystemControlPage from './pages/SystemControlPage';\n"
app = app.replace("import HealthPage from './pages/HealthPage';", imports_to_add)
app = re.sub(r"import KernelPage from './pages/KernelPage';\n?", "", app)
app = re.sub(r"import LicencePage from './pages/LicencePage';\n?", "", app)
app = re.sub(r"import WikiPage from './pages/WikiPage';\n?", "", app)
app = re.sub(r"import SettingsPage from './pages/SettingsPage';\n?", "", app)

# Remove all 5 system routes
app = re.sub(r'<Route path="/health" element=\{<HealthPage />\} />\n?', '', app)
app = re.sub(r'<Route path="/kernel" element=\{<KernelPage />\} />\n?', '', app)
app = re.sub(r'<Route path="/licence" element=\{<LicencePage />\} />\n?', '', app)
app = re.sub(r'<Route path="/wiki" element=\{<WikiPage />\} />\n?', '', app)
app = re.sub(r'<Route path="/settings" element=\{<SettingsPage />\} />\n?', '', app)

# Insert the single /system route
app = app.replace('<Route path="/intelligence"', '<Route path="/system" element={<SystemControlPage />} />\n            <Route path="/intelligence"')

# Remove leftover protocol routes since ProtocolDashboardPage handles them internally now
# The ones left are: /identity, /records, /proofs, /wallets, /transactions, /contracts, /evidence, /security, /activity
protocol_routes = ['/identity', '/records', '/proofs', '/wallets', '/transactions', '/contracts', '/evidence', '/security', '/activity']
for r in protocol_routes:
    app = re.sub(r'<Route path="' + r + r'" element=\{<ProtocolDashboardPage />\} />\n?\s*', '', app)

# Make sure prediction-markets is gone too just in case
app = re.sub(r'<Route path="/prediction-markets".*?/>\n?\s*', '', app)

with open('src/App.tsx', 'w') as f:
    f.write(app)

# Rewrite navigation.tsx to ONLY have the 4 pillars!
nav_content = """import {
  Activity,
  BrainCircuit,
  Landmark,
  LayoutDashboard,
} from 'lucide-react';

export const NAVIGATION_ITEMS = [
  { to: '/dashboard', label: 'Protocol Core', icon: LayoutDashboard },
  { to: '/treasury', label: 'Treasury Control', icon: Landmark },
  { to: '/intelligence', label: 'Intelligence', icon: BrainCircuit },
  { to: '/system', label: 'System', icon: Activity },
];
"""
with open('src/navigation.tsx', 'w') as f:
    f.write(nav_content)

print("Updated routes and navigation to 4 pillars")
