import re

with open("src/pages/ProtocolDashboardPage.tsx", "r") as f:
    code = f.read()

# I will find the exact string to replace using regex, capturing from {(tab === 'overview' || tab === 'identity') && <section className="protocol-grid agent-focus-grid"> down to the end of that section.
match = re.search(r"\{\(tab === 'overview' \|\| tab === 'identity'\) && <section className=\"protocol-grid agent-focus-grid\".*?(?=\n\s*\{\(tab === 'overview' \|\| tab === 'identity'\) && <section className=\"protocol-grid\">)", code, flags=re.DOTALL)
if match:
    # Let's completely rewrite this block cleanly
    clean_block = """        {(tab === 'overview' || tab === 'identity') && (
          <section className="protocol-grid agent-focus-grid">
            <div className="protocol-panel selected-agent-panel">
              <div className="panel-heading">
                <div>
                  <span className="panel-label">Selected identity</span>
                  <h2>{selectedAgent?.alias || selectedAgent?.name || (selectedAgent ? short(selectedAgent.id, 15, 9) : 'No agent selected')}</h2>
                </div>
                <State ok={erc8004?.binding_status === 'verified'}>{erc8004?.binding_status === 'verified' ? 'Verified' : 'Not verified'}</State>
              </div>
              <div className="identity-lines">
                <EvidenceValue label="ERC-8004 / DID" value={selectedAgent?.id} />
                <EvidenceValue label="Sovereign agent" value={detail?.primitives?.sovereign_agent} />
                <EvidenceValue label="NFT owner" value={erc8004?.nft_owner_address} />
                <EvidenceValue label="Agent wallet" value={erc8004?.agent_wallet_address} />
                <div className="ais-score">
                  <span>Agent Integrity Score</span>
                  <strong>{ais?.ais == null ? '—' : ais.ais.toFixed(1)}</strong>
                  <small>/ 100 · Tier {detail?.verification_tier ?? selectedAgent?.verification_tier ?? '—'} · Oracle projection</small>
                </div>
              </div>
            </div>
            <div className="protocol-panel agent-list-panel">
              <div className="panel-heading">
                <div>
                  <span className="panel-label">{ALLOW_UNSCOPED_AGENT_DIRECTORY ? 'Operator / dev directory' : 'Authenticated scope'}</span>
                  <h2>Agents</h2>
                </div>
                <span className="panel-count">{agents.length}</span>
              </div>
              <div className="agent-list">
                {agents.length ? agents.map(agent => <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedAgent?.id} onSelect={() => setSelectedAgent(agent)} />) : <div className="empty-state">No permitted agents are available for this authenticated session.</div>}
              </div>
            </div>
          </section>
        )}"""
    code = code[:match.start()] + clean_block + code[match.end():]
    
# Clean up any trailing garbage at the end of the file caused by bad replacement
# Let's fix line 174: <section className="protocol-note"><ShieldCheck size={16} /><span>This console exposes protocol evidence and wallet controls. It never renders private keys or treats AIS as authorization by itself.</span></div></div></section>}
# which should be: <section className="protocol-note"><ShieldCheck size={16} /><span>This console exposes protocol evidence and wallet controls. It never renders private keys or treats AIS as authorization by itself.</span></section>
code = code.replace("</span></div></div></section>}", "</span></section>")

with open("src/pages/ProtocolDashboardPage.tsx", "w") as f:
    f.write(code)
print("Rewrote block cleanly")
