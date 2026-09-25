import os
import re

# 1. Update App.tsx
with open("src/App.tsx", "r") as f:
    app_tsx = f.read()

# Remove imports for ShieldPage and QuantPage
app_tsx = re.sub(r"import ShieldPage.*?\n", "", app_tsx)
app_tsx = re.sub(r"import QuantPage.*?\n", "", app_tsx)

# Remove routes
app_tsx = re.sub(r"\s*<Route path=\"/shield\".*?/>\n", "\n", app_tsx)
app_tsx = re.sub(r"\s*<Route path=\"/fleet\".*?/>\n", "\n", app_tsx)
app_tsx = re.sub(r"\s*<Route path=\"/quant\".*?/>\n", "\n", app_tsx)

with open("src/App.tsx", "w") as f:
    f.write(app_tsx)

# 2. Update navigation.tsx
with open("src/navigation.tsx", "r") as f:
    nav_tsx = f.read()

new_nav = """export const NAVIGATION_GROUPS: NavigationGroup[] = [
  { section: 'Protocol', items: [
    { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
    { to: '/identity', label: 'Identity & Trust', icon: Fingerprint },
    { to: '/contracts', label: 'Contracts', icon: FileKey2 },
  ] },
  { section: 'Treasury', items: [
    { to: '/treasury', label: 'Treasury Control', icon: Landmark },
    { to: '/financials', label: 'Financials', icon: WalletCards },
  ] },
  { section: 'Intelligence', items: [
    { to: '/intelligence', label: 'Intelligence', icon: BrainCircuit },
    { to: '/correlation', label: 'Correlation', icon: Network },
    { to: '/prediction-markets', label: 'Prediction Markets', icon: BadgeCheck },
  ] },
  { section: 'System', items: [
    { to: '/health', label: 'Health', icon: Activity },
    { to: '/kernel', label: 'Kernel', icon: ShieldCheck },
    { to: '/knowledge', label: 'Knowledge', icon: Database },
    { to: '/licence', label: 'Licence', icon: FileKey2 },
    { to: '/wiki', label: 'Wiki', icon: BookOpen },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
];"""

nav_tsx = re.sub(r"export const NAVIGATION_GROUPS: NavigationGroup\[\] = \[\s*.*?\s*\];", new_nav, nav_tsx, flags=re.DOTALL)

with open("src/navigation.tsx", "w") as f:
    f.write(nav_tsx)

print("Patched files successfully.")
