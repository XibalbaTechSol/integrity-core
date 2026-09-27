with open("src/components/AppHeader.tsx", "r") as f:
    header = f.read()

header = header.replace("'dashboard': 'Protocol overview',", "'dashboard': 'Protocol Core',")
header = header.replace("'intelligence': 'Intelligence & Knowledge',", "'intelligence': 'Intelligence',\n    'system': 'System Administration',")

with open("src/components/AppHeader.tsx", "w") as f:
    f.write(header)
print("Updated AppHeader")
