import re

with open("src/pages/FinancialsPage.tsx", "r") as f:
    content = f.read()

# Add import for AgentRiskContext
if "AgentRiskContext" not in content:
    content = content.replace("import { SubTabs } from '../components/ui/SubTabs';", "import { SubTabs } from '../components/ui/SubTabs';\nimport { AgentRiskContext } from '../components/control/AgentRiskContext';")

# Remove the h1 tag
content = re.sub(r'<h1[^>]*>.*?</h1>', '', content)

# Inject AgentRiskContext right before the 4-stat strip
content = content.replace("{/* ── 4-stat strip", "<AgentRiskContext purpose=\"funds\" />\n\n      {/* ── 4-stat strip")

# Replace FinancialsPage with TreasuryControlPage
content = content.replace("export default function FinancialsPage() {", "export default function TreasuryControlPage() {")

with open("src/pages/TreasuryControlPage.tsx", "w") as f:
    f.write(content)

with open('src/App.tsx', 'r') as f:
    app = f.read()

app = app.replace("import FinancialsPage from './pages/FinancialsPage';\n", "")
app = re.sub(r'<Route path="/financials" element=\{<FinancialsPage />\} />\s*', '', app)

with open('src/App.tsx', 'w') as f:
    f.write(app)

with open('src/navigation.tsx', 'r') as f:
    nav = f.read()

nav = re.sub(r"\s*\{\s*to:\s*'/financials',\s*label:\s*'Financials',\s*icon:\s*WalletCards\s*\},", "", nav)

with open('src/navigation.tsx', 'w') as f:
    f.write(nav)

print("Merged FinancialsPage into TreasuryControlPage and updated routing")
