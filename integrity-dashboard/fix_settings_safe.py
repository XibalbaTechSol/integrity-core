import re

with open("src/pages/SettingsPage.tsx", "r") as f:
    code = f.read()

# Replace <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}> with <div className="protocol-panel"><div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
code = code.replace(
    "<div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>",
    '<div className="protocol-panel"><div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "2rem" }}>'
)

# Since we added an opening <div className="protocol-panel">, we must add a closing </div> right before the end of the JSX expression for each tab.
# Each tab block looks like:
# {activeTab === 'general' && (
#   <div className="protocol-panel"><div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "2rem" }}>
#     ...
#   </div>
# )}
# Wait, replacing the open div means there's now one unclosed div.
# Instead, let's just use Panel component!
# We can just change <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}> to <Panel>
code = code.replace(
    "<div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>",
    '<Panel style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>'
)

# And then we change the closing </div> for those specific divs to </Panel>
# Since the closing </div> is right before )}, we can just replace </div>\n        )} with </Panel>\n        )}
code = re.sub(r'</div>\s*\)}', r'</Panel>\n        )}', code)

# Let's ensure Panel is imported
if 'import { Panel }' not in code:
    code = code.replace("import { useState, useEffect } from 'react';", "import { useState, useEffect } from 'react';\nimport { Panel } from '../components/shared/Panel';")

# Change h3 to panel-heading
code = re.sub(
    r'<h3 style=\{\{ borderBottom: \'1px solid var\(--border-color\)\', paddingBottom: \'1rem\' \}\}>(.*?)</h3>',
    r'<div className="panel-heading"><h2 style={{ margin: 0, fontSize: "17px" }}>\1</h2></div>',
    code
)

with open("src/pages/SettingsPage.tsx", "w") as f:
    f.write(code)

