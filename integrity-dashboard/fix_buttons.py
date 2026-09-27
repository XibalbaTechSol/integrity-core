import os
import re

button_mapping = {
    r'\bbtn btn-primary\b': 'primary-button',
    r'\bbtn btn-success\b': 'primary-button',
    r'\bbtn btn-outline\b': 'secondary-button',
    r'\bbtn btn-ghost\b': 'secondary-button',
    r'\bbutton primary\b': 'primary-button',
    # "button" by itself in AuthPage.tsx:
    r'className="button"': 'className="secondary-button"',
    r'\bbtn btn-icon\b': 'secondary-button', # maybe? Or keep icon button?
}

def replace_in_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    for pattern, repl in button_mapping.items():
        content = re.sub(pattern, repl, content)
        
    if original != content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('src'):
    for file in files:
        if file.endswith('.tsx'):
            replace_in_file(os.path.join(root, file))

