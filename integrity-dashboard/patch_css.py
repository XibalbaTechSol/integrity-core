import re

with open("src/index.css", "r") as f:
    css = f.read()

new_root = """:root {
  --bg-color: #08111b;
  --surface-color: #0d1824;
  --border-color: #213246;
  --border: var(--border-color);
  --text-primary: #eef5fb;
  --text-secondary: #8ea1b4;
  --font-family: system-ui, -apple-system, sans-serif;
  --base-font-size: 16px;
  --accent-color: #36a7ff;
  --accent-hover: #1b8cd4;
  --glass-border: #213246;

  /* Dashboard Ported Variables */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --radius-sm: 4px;"""

css = re.sub(r":root\s*{[^}]*--radius-sm: 4px;", new_root, css, flags=re.DOTALL)

with open("src/index.css", "w") as f:
    f.write(css)

print("Patched index.css")
