import re

with open('src/App.tsx', 'r') as f:
    app = f.read()

app = re.sub(r'<Route path="/agents".*?/>\n?\s*', '', app)
app = re.sub(r'<Route path="/evidence".*?/>\n?\s*', '', app)
app = re.sub(r'<Route path="/memory".*?/>\n?\s*', '', app)
app = re.sub(r'\} />\s*\{/\* Cross-platform.*?\*/\}\s*', '', app)

with open('src/App.tsx', 'w') as f:
    f.write(app)
print("Fixed App.tsx redirects")
