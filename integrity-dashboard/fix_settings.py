import re

with open("src/pages/SettingsPage.tsx", "r") as f:
    code = f.read()

# I want to wrap the settings content in protocol-panel
# Right now it has a top-level div with display: flex, flexDirection: column
# Let's see what the top level div is
match = re.search(r'return \(\s*<div style=\{\{ display: \'flex\', flexDirection: \'column\'', code)
if match:
    print("Found top level div")
    # Actually, the user can just have the panels match.
    # I'll just change the inner divs to Panel or protocol-panel.
