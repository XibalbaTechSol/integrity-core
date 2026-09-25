import re

with open("src/pages/SettingsPage.tsx", "r") as f:
    code = f.read()

# Replace <h3 style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>Title</h3>
# with <div className="panel-heading"><h2>Title</h2></div>
code = re.sub(
    r'<h3 style=\{\{ borderBottom: \'1px solid var\(--border-color\)\', paddingBottom: \'1rem\' \}\}>(.*?)</h3>',
    r'<div className="panel-heading"><h2 style={{ margin: 0, fontSize: "17px" }}>\1</h2></div>',
    code
)

with open("src/pages/SettingsPage.tsx", "w") as f:
    f.write(code)

