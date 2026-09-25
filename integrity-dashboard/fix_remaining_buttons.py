import os
import re

button_mapping = {
    r'\bbtn btn-secondary\b': 'secondary-button',
    r'\bbtn btn-danger\b': 'secondary-button', # Maybe make danger ones secondary since we only have two main styles, or keep danger if they want a red button. User said "w/ blue buttons" so secondary-button is fine.
    r'\bbtn btn-sm btn-primary\b': 'primary-button',
    r'\bbtn btn-sm btn-danger\b': 'secondary-button',
    r'\bbtn btn-xs btn-danger\b': 'secondary-button',
    r'className="btn"': 'className="secondary-button"',
    r'\bbtn btn-danger btn-xs\b': 'secondary-button',
    r'\bbtn btn-danger btn-sm\b': 'secondary-button',
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

