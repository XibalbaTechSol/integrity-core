import re

with open("src/pages/SecurityControlPage.tsx", "r") as f:
    content = f.read()

# Remove ShieldPage import
content = re.sub(r"import ShieldPage from '\./ShieldPage';\n", "", content)

# Remove the 'shield' tab from TABS
content = re.sub(r"\s*{\s*id:\s*'shield',\s*label:\s*'Endpoints & devices',\s*icon:\s*ShieldCheck\s*},", "", content)

# Change initialTab from 'shield' to 'kernel'
content = content.replace("initialTab = 'shield'", "initialTab = 'kernel'")
content = content.replace("initialTab?: SecurityTab }", "initialTab?: SecurityTab }") # no change needed for type
content = content.replace("type SecurityTab = 'shield' | 'kernel' | 'actions';", "type SecurityTab = 'kernel' | 'actions';")

# Remove the shield tab rendering
content = re.sub(r"\s*{tab === 'shield' && <ShieldPage />}\n", "\n", content)

with open("src/pages/SecurityControlPage.tsx", "w") as f:
    f.write(content)

print("Patched SecurityControlPage.tsx")
