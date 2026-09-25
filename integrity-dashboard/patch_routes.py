import re

with open('src/App.tsx', 'r') as f:
    content = f.read()

content = content.replace("import KnowledgeControlPage from './pages/KnowledgeControlPage';", "import IntelligenceControlPage from './pages/IntelligenceControlPage';")
content = content.replace("import { IntelligencePage } from './pages/IntelligencePage';", "")
content = content.replace("import CorrelationPage from './pages/CorrelationPage';", "")

content = re.sub(r'<Route path="/knowledge" element=\{<KnowledgeControlPage />\} />\s*', '', content)
content = re.sub(r'<Route path="/correlation" element=\{<CorrelationPage />\} />\s*', '', content)
content = re.sub(r'<Route path="/intelligence" element=\{<IntelligencePage />\} />\s*', '<Route path="/intelligence" element={<IntelligenceControlPage />} />\n            ', content)
content = content.replace('<KnowledgeControlPage />', '<IntelligenceControlPage />')

with open('src/App.tsx', 'w') as f:
    f.write(content)

with open('src/navigation.tsx', 'r') as f:
    nav = f.read()

# In navigation.tsx, remove /knowledge and /correlation.
# We have: 
#   { section: 'Intelligence', items: [
#     { to: '/intelligence', label: 'Intelligence', icon: BrainCircuit },
#     { to: '/correlation', label: 'Correlation', icon: Network },
#     { to: '/prediction-markets', label: 'Prediction Markets', icon: BadgeCheck },
#   ] },
#   { section: 'System', items: [
#     { to: '/health', label: 'Health', icon: Activity },
#     { to: '/kernel', label: 'Kernel', icon: ShieldCheck },
#     { to: '/knowledge', label: 'Knowledge', icon: Database },
#     { to: '/licence', label: 'Licence', icon: FileKey2 },
#     ...

nav = re.sub(r"\s*\{\s*to:\s*'/knowledge',\s*label:\s*'Knowledge',\s*icon:\s*Database\s*\},", "", nav)
nav = re.sub(r"\s*\{\s*to:\s*'/correlation',\s*label:\s*'Correlation',\s*icon:\s*Network\s*\},", "", nav)

with open('src/navigation.tsx', 'w') as f:
    f.write(nav)

print("Patched App.tsx and navigation.tsx")
