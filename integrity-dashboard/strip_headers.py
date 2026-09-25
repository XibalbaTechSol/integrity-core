import re
import os

pages = [
    'src/pages/HealthPage.tsx',
    'src/pages/KernelPage.tsx',
    'src/pages/LicencePage.tsx',
    'src/pages/SettingsPage.tsx',
    'src/pages/WikiPage.tsx'
]

for page in pages:
    if not os.path.exists(page): continue
    with open(page, 'r') as f:
        content = f.read()

    # Strip ControlHeader
    content = re.sub(r'<ControlHeader[^>]*/>', '', content)
    # Strip inline <h1> headers just in case
    content = re.sub(r'<h1[^>]*>.*?</h1>', '', content)
    # Convert <div className="control-page"> to just <div style={{ display: 'flex', flexDirection: 'column' }}> or similar
    content = re.sub(r'<div className="control-page[^"]*">', '<div>', content)
    content = content.replace('<div className="control-page-body">', '<div>')

    with open(page, 'w') as f:
        f.write(content)
print("Stripped headers")
