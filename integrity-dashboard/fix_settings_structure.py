import re

with open("src/pages/SettingsPage.tsx", "r") as f:
    code = f.read()

# I want to change:
# <div className="protocol-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
#   <div className="panel-heading"><h2 style={{ margin: 0, fontSize: "17px" }}>Title</h2></div>
#   ...
# </div>
#
# To:
# <div className="protocol-panel">
#   <div className="panel-heading"><h2 style={{ margin: 0, fontSize: "17px" }}>Title</h2></div>
#   <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
#   ...
#   </div>
# </div>

pattern = re.compile(
    r'<div className="protocol-panel" style=\{\{ padding: \'20px\', display: \'flex\', flexDirection: \'column\', gap: \'20px\' \}\}>\s*<div className="panel-heading"><h2 style=\{\{ margin: 0, fontSize: "17px" \}\}>(.*?)</h2></div>',
    re.DOTALL
)

def replacer(match):
    title = match.group(1)
    return f'<div className="protocol-panel">\n            <div className="panel-heading"><h2 style={{{{ margin: 0, fontSize: "17px" }}}}>{title}</h2></div>\n            <div style={{{{ padding: \'20px\', display: \'flex\', flexDirection: \'column\', gap: \'20px\' }}}}>'

code = pattern.sub(replacer, code)

# We also need to add a closing </div> at the end of each tab before the closing )}
code = re.sub(r'(\s*</div>\s*)\)}', r'\n            </div>\1)}', code)

with open("src/pages/SettingsPage.tsx", "w") as f:
    f.write(code)

