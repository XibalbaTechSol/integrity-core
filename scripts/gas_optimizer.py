import json
import os
from collections import defaultdict
from datetime import datetime

LOG_FILE = "integrity-sdk/gas_usage.jsonl"
REPORT_FILE = "docs/wiki/queries/gas-tracking.md"

def analyze_gas():
    if not os.path.exists(LOG_FILE):
        print("No gas usage data found.")
        return

    data_by_action = defaultdict(list)
    total_cost_wei = 0

    with open(LOG_FILE, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                action = entry.get("action", "unknown")
                gas_used = entry.get("gas_used", 0)
                cost_wei = entry.get("cost_wei", 0)
                
                data_by_action[action].append((gas_used, cost_wei, entry.get("timestamp")))
                total_cost_wei += cost_wei
            except Exception:
                pass

    if not data_by_action:
        print("No valid entries to analyze.")
        return

    report_lines = [
        "---",
        "title: Gas Tracking & Optimization Data",
        "type: query",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "confidence: high",
        "---",
        "# Gas Tracking Data",
        f"> Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This document automatically tracks gas usage from the agent SDK transactions.",
        f"**Total Agent Spend:** {total_cost_wei} wei",
        "",
        "## Averages by Action",
        "| Action | Count | Avg Gas Used | Avg Cost (wei) |",
        "|---|---|---|---|"
    ]

    for action, entries in data_by_action.items():
        count = len(entries)
        avg_gas = sum(e[0] for e in entries) / count
        avg_cost = sum(e[1] for e in entries) / count
        report_lines.append(f"| {action} | {count} | {avg_gas:,.2f} | {avg_cost:,.2f} |")

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, 'w') as f:
        f.write("\n".join(report_lines))
    
    print(f"Gas report updated at {REPORT_FILE}")
    
    # Check if we need to add this to WIKI_INDEX.md
    index_path = "docs/wiki/WIKI_INDEX.md"
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            index_content = f.read()
            
        if "gas-tracking.md" not in index_content:
            with open(index_path, 'a') as f:
                f.write("\n- [Gas Tracking](queries/gas-tracking.md) — Automated SDK gas optimization loop\n")
            print("Added gas-tracking.md to WIKI_INDEX.md")

if __name__ == '__main__':
    analyze_gas()
