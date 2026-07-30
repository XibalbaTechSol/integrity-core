import os
import re
from datetime import datetime

WIKI_DIR = 'docs/wiki'
INDEX_FILE = os.path.join(WIKI_DIR, 'WIKI_INDEX.md')

def check_wiki():
    print("--- WIKI LINT REPORT ---")
    
    if not os.path.exists(INDEX_FILE):
        print(f"Error: {INDEX_FILE} not found.")
        return

    with open(INDEX_FILE, 'r') as f:
        index_content = f.read()

    # 1. Orphan & Dead-link detection
    all_md_files = []
    for root, _, files in os.walk(WIKI_DIR):
        for file in files:
            if file.endswith('.md') and file != 'WIKI_INDEX.md' and file != 'WIKI_LOG.md' and file != 'WIKI_SCHEMA.md' and file != 'index.md':
                rel_path = os.path.relpath(os.path.join(root, file), WIKI_DIR)
                all_md_files.append(rel_path)

    linked_pages = re.findall(r'\]\(([^)]+\.md)\)', index_content)
    
    # Normalize paths
    linked_pages = [os.path.normpath(p) for p in linked_pages]
    
    orphans = [p for p in all_md_files if p not in linked_pages]
    dead_links = [p for p in linked_pages if p not in all_md_files and not p.startswith('../')]

    print(f"\nOrphans (in dir but not in index): {len(orphans)}")
    for o in orphans:
        print(f"  - {o}")

    print(f"\nDead links in index (in index but file missing): {len(dead_links)}")
    for d in dead_links:
        print(f"  - {d}")

    # 2. Staleness audit
    print("\nStaleness Audit (>14 days old):")
    stale_pages = []
    now = datetime.now()
    
    for md_file in all_md_files:
        path = os.path.join(WIKI_DIR, md_file)
        with open(path, 'r') as f:
            content = f.read()
            match = re.search(r'updated:\s*(\d{4}-\d{2}-\d{2})', content)
            if match:
                date_str = match.group(1)
                try:
                    updated_date = datetime.strptime(date_str, '%Y-%m-%d')
                    days_old = (now - updated_date).days
                    if days_old > 14:
                        stale_pages.append((md_file, days_old))
                except ValueError:
                    pass

    for p, days in stale_pages:
        print(f"  - {p} ({days} days old)")

    # 3. Drift check targets
    print("\nDrift Check Targets (Entities with source_files):")
    for md_file in all_md_files:
        if not md_file.startswith('entities/'):
            continue
        path = os.path.join(WIKI_DIR, md_file)
        with open(path, 'r') as f:
            content = f.read()
            # extract source_files from frontmatter
            if 'source_files:' in content:
                print(f"  - {md_file}:")
                lines = content.split('\n')
                in_source = False
                for line in lines:
                    if line.startswith('source_files:'):
                        in_source = True
                    elif in_source:
                        if line.startswith('  - '):
                            src = line.strip()[2:].strip()
                            exists = os.path.exists(src)
                            status = "EXISTS" if exists else "MISSING"
                            print(f"      {src} [{status}]")
                        elif not line.startswith(' '):
                            break

    # 4. Counter reconciliation
    total_pages = len(all_md_files)
    concepts = len([p for p in all_md_files if p.startswith('concepts/')])
    entities = len([p for p in all_md_files if p.startswith('entities/')])
    print(f"\nPage Counts: Total={total_pages}, Concepts={concepts}, Entities={entities}")
    print("Please verify the WIKI_INDEX.md counter matches this.")

if __name__ == '__main__':
    check_wiki()
