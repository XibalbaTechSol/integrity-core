import re

with open("src/pages/TreasuryControlPage.tsx", "r") as f:
    code = f.read()

# We need to replace the StatCard component definition and the way the top stats are rendered.
# We also need to change the root divs.

match_statcard = re.search(r'function StatCard.*?\}', code, flags=re.DOTALL)
if match_statcard:
    code = code[:match_statcard.start()] + code[match_statcard.end():]

# Find the return block
match_return = re.search(r'return \(\s*<div style=\{\{ display: \'flex\', flexDirection: \'column\', gap: \'var\(--space-4\)\' \}\}>.*?<AgentRiskContext purpose="funds" />', code, flags=re.DOTALL)
if match_return:
    replacement = """return (
    <div className="protocol-app-inner" style={{ display: 'contents' }}>
      <section className="protocol-health">
        <div><span>TVL</span><strong><DollarSign size={15} style={{ marginRight: 6 }}/> {tvl.toLocaleString()}</strong></div>
        <div><span>Total Loan Volume</span><strong><TrendingUp size={15} style={{ marginRight: 6 }}/> {totalLoans.toLocaleString()}</strong></div>
        <div><span>Staked ITK</span><strong><Lock size={15} style={{ marginRight: 6 }}/> {stakedItk.toLocaleString()}</strong></div>
        <div><span>Market Volume</span><strong><ShoppingCart size={15} style={{ marginRight: 6 }}/> {marketVol.toLocaleString()}</strong></div>
      </section>

      <div className="protocol-content">
        <AgentRiskContext purpose="funds" />"""
    
    code = code[:match_return.start()] + replacement + code[match_return.end():]

# Now remove the old 4-stat strip
code = re.sub(r'\{/\* ── 4-stat strip.*?</style>.*?</div>', '', code, flags=re.DOTALL) # wait there's no </style>
code = re.sub(r'\{/\* ── 4-stat strip.*?</div>', '', code, flags=re.DOTALL)

# Let's cleanly replace the middle section:
middle_replace_pattern = r'\{/\* ── 4-stat strip ─────────────────────────────────────────────────── \*/\}.*?</div>'
code = re.sub(middle_replace_pattern, '', code, flags=re.DOTALL)

# The Sub-navigation Tab Bar:
#       {/* ── Sub-navigation Tab Bar ───────────────────────────────────────── */}
#      <div style={{ marginBottom: '16px', marginTop: '16px' }}>
#        <SubTabs tabs={TABS as any} activeTab={activeTab} setActiveTab={setActiveTab as any} />
#      </div>
code = re.sub(r'<div style=\{\{ marginBottom: \'16px\', marginTop: \'16px\' \}\}>\s*<SubTabs tabs=\{TABS as any\} activeTab=\{activeTab\} setActiveTab=\{setActiveTab as any\} />\s*</div>', 
              r'<SubTabs tabs={TABS as any} activeTab={activeTab} setActiveTab={setActiveTab as any} />', code)

# Close the protocol-content and protocol-app-inner divs at the end
code = re.sub(r'</AnimatePresence>\s*</div>\s*</div>\s*\);\s*\}', r'</AnimatePresence>\s*</div>\s*</div>\s*</div>\s*);\s*}', code)

with open("src/pages/TreasuryControlPage.tsx", "w") as f:
    f.write(code)

