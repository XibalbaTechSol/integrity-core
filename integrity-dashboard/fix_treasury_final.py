import re

with open("src/pages/TreasuryControlPage.tsx", "r") as f:
    code = f.read()

# Remove the StatCard definition
# It starts at `function StatCard` and ends right before `const sectionVariants =`
code = re.sub(r'interface StatCardProps \{.*?\}\s*function StatCard.*?\}\s*(?=// ─── Animation config)', '', code, flags=re.DOTALL)

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
middle_replace_pattern = r'\{\/\* ── 4-stat strip ─────────────────────────────────────────────────── \*\/\}.*?</div>'
code = re.sub(middle_replace_pattern, '', code, flags=re.DOTALL)

# The Sub-navigation Tab Bar:
code = re.sub(r'<div style=\{\{ marginBottom: \'16px\', marginTop: \'16px\' \}\}>\s*<SubTabs tabs=\{TABS as any\} activeTab=\{activeTab\} setActiveTab=\{setActiveTab as any\} />\s*</div>', 
              r'<SubTabs tabs={TABS as any} activeTab={activeTab} setActiveTab={setActiveTab as any} />', code)

# Close the protocol-content and protocol-app-inner divs at the end
code = code.replace("</AnimatePresence>\n      </div>\n    </div>", "</AnimatePresence>\n      </div>\n      </div>\n    </div>")

with open("src/pages/TreasuryControlPage.tsx", "w") as f:
    f.write(code)

