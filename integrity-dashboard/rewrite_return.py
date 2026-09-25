import re

with open("src/pages/ProtocolDashboardPage.tsx", "r") as f:
    code = f.read()

# We will cut everything from "return <div className="protocol-app-inner"" to the end of the file
# and replace it with a clean formatted block.

match = re.search(r'return <div className="protocol-app-inner".*', code, flags=re.DOTALL)
if not match:
    print("Could not find return statement")
    exit(1)

clean_return = """return (
    <div className="protocol-app-inner" style={{ display: 'contents' }}>
      <section className="protocol-health">
        <div><span>Network health</span><strong><i />{detail ? 'Connected' : 'Awaiting Oracle'}</strong></div>
        <div><span>Identity binding</span><strong><i className={erc8004?.binding_status === 'verified' ? '' : 'muted-dot'} />{erc8004?.binding_status === 'verified' ? 'ERC-8004 verified' : 'Not confirmed'}</strong></div>
        <div><span>Cortex evidence</span><strong><i className={cortex?.integrity_check === 'ok' ? '' : 'muted-dot'} />{cortex ? `${cortex.memory_count.toLocaleString()} memories` : 'Unavailable'}</strong></div>
        <div><span>Live data</span><strong><i className={ais ? '' : 'muted-dot'} />{ais ? 'Oracle projection' : 'Read-only state'}</strong></div>
      </section>

      <div className="protocol-content">
        <SubTabs 
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'identity', label: 'Identity & Trust' },
            { id: 'contracts', label: 'Contracts' },
            { id: 'wallets', label: 'Wallets' },
            { id: 'evidence', label: 'Evidence' }
          ]} 
          activeTab={tab} 
          setActiveTab={(id) => setRouteTab(id)} 
        />

        {(tab === 'overview' || tab === 'identity') && (
          <>
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
                  {agents.length ? agents.map(agent => (
                    <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedAgent?.id} onSelect={() => setSelectedAgent(agent)} />
                  )) : (
                    <div className="empty-state">No permitted agents are available for this authenticated session.</div>
                  )}
                </div>
              </div>
            </section>

            <section className="protocol-grid xns-grid">
              <div className="protocol-panel">
                <div className="panel-heading">
                  <div>
                    <span className="panel-label">On-chain name resolution</span>
                    <h2>XNS Search Service</h2>
                  </div>
                </div>
                <div style={{ padding: '20px' }}>
                  <XNSSearchService />
                </div>
              </div>
              
              <div className="protocol-panel">
                <div className="panel-heading">
                  <div>
                    <span className="panel-label">Autonomous identities</span>
                    <h2>Identity Management</h2>
                  </div>
                </div>
                <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Manage your autonomous agent identities. You can either deploy a new identity or claim ownership of an existing one.
                  </p>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="primary-button" onClick={() => setIsRegisterModalOpen(true)} style={{ flex: 1 }}>Register New Identity</button>
                    <button className="secondary-button" onClick={() => setIsClaimModalOpen(true)} style={{ flex: 1 }}>Claim Existing Identity</button>
                  </div>
                </div>
              </div>
              
              <div className="protocol-panel">
                <div className="panel-heading">
                  <div>
                    <span className="panel-label">Register</span>
                    <h2>Register an XNS Handle</h2>
                  </div>
                </div>
                <div style={{ padding: '20px' }}>
                  {selectedAgent ? <XNSRegisterForm /> : <div className="empty-state">Select an agent to register a handle.</div>}
                </div>
              </div>
            </section>
          </>
        )}

        {(tab === 'overview' || tab === 'wallets') && (
          <section className="protocol-grid wallet-grid">
            <div className="protocol-panel wallet-panel">
              <div className="panel-heading">
                <div><span className="panel-label">Agent treasury</span><h2>Wallet custody</h2></div>
                <KeyRound size={19} />
              </div>
              <div className="wallet-lock">
                <LockKeyhole size={22} />
                <div>
                  <strong>Protected key boundary</strong>
                  <span>Private keys are never shown. This UI can read the resolved treasury and connect an external signer, but cannot export or custody agent keys.</span>
                </div>
              </div>
              <div className="wallet-address-row">
                <span>Agent wallet · on-chain resolved</span>
                <code>{short(detail?.primitives?.sovereign_agent, 12, 10)}</code>
                <small>Controller and signer relationship are shown only when independently verified by ERC-8004 data.</small>
              </div>
              <div className="balance-grid">
                <div><span>ITK balance · Oracle</span><strong>{formatItk(wallet?.itk_balance) ?? onChainBalance?.itk ?? '—'} <small>ITK</small></strong></div>
                <div><span>ETH balance · RPC</span><strong>{ethBalance ?? '—'} <small>ETH</small></strong></div>
              </div>
              <div className="wallet-actions">
                <button className="primary-button" onClick={() => void connectWallet()}><ArrowUpFromLine size={16} />Connect external signer</button>
                <button className="secondary-button" onClick={() => void copyText(detail?.primitives?.sovereign_agent)}><ArrowDownToLine size={16} />Copy receive address</button>
              </div>
              {onChainBalance && <div className="source-line">On-chain read · Base Sepolia · block {onChainBalance.blockNumber} · {onChainBalance.itkSymbol} {onChainBalance.itk}</div>}
            </div>
            
            <div className="protocol-panel transaction-panel">
              <div className="panel-heading">
                <div><span className="panel-label">Wallet activity</span><h2>Transactions</h2></div>
                <span className="panel-count">{wallet?.transaction_history?.length ?? 0}</span>
              </div>
              {wallet?.transaction_history?.length ? wallet.transaction_history.slice(0, 6).map(tx => (
                <div className="transaction-row" key={tx.id}>
                  <span className="tx-icon"><ArrowUpFromLine size={14} /></span>
                  <span><strong>{tx.type} · {tx.asset}</strong><small>{short(tx.id, 12, 8)} · {tx.status}</small></span>
                  <b>{tx.amount}</b>
                </div>
              )) : <div className="empty-state">Oracle transaction history is unavailable until event indexing is implemented.</div>}
            </div>
          </section>
        )}

        {(tab === 'overview' || tab === 'evidence') && (
          <section className="protocol-panel evidence-panel">
            <div className="panel-heading">
              <div><span className="panel-label">Proof surface</span><h2>Evidence chain</h2></div>
              <a href="#evidence">Inspect all <ChevronRight size={14} /></a>
            </div>
            <div className="evidence-chain">
              <div className="evidence-node"><span>01</span><strong>BCC intent</strong><small>{auditLog.length ? `${auditLog.length} audit records` : 'Unavailable'}</small></div>
              <div className="evidence-line" />
              <div className="evidence-node"><span>02</span><strong>Hash</strong><small>{provenance.length ? `${provenance.length} anchored leaves` : 'Unavailable'}</small></div>
              <div className="evidence-line" />
              <div className="evidence-node"><span>03</span><strong>Merkle root</strong><small>{short(provenance[0]?.root || merkle?.root_node_id, 10, 8)}</small></div>
              <div className="evidence-line" />
              <div className="evidence-node"><span>04</span><strong>ZK proof</strong><small>{ais?.zk_proof_verified === true ? 'Verified' : ais ? 'Not verified' : 'Unavailable'}</small></div>
              <div className="evidence-line" />
              <div className="evidence-node"><span>05</span><strong>Oracle receipt</strong><small>{ais ? 'AIS projection' : 'Unavailable'}</small></div>
            </div>
            <div className="evidence-detail-grid">
              <EvidenceValue label="Merkle root" value={provenance[0]?.root || merkle?.root_node_id} />
              <EvidenceValue label="Latest content leaf" value={provenance[0]?.leaf} />
              <EvidenceValue label="Verification state" value={ais ? (ais.zk_proof_verified ? 'zk_verified' : 'not_verified') : 'unavailable'} />
              <EvidenceValue label="Reporting period" value={ais ? `${ais.period_start} → ${ais.period_end}` : null} />
            </div>
          </section>
        )}

        {(tab === 'overview' || tab === 'contracts') && (
          <section className="protocol-panel contracts-panel">
            <div className="panel-heading">
              <div><span className="panel-label">Agent-controlled surface</span><h2>Deployed contracts</h2></div>
              <span className="panel-count">{contracts.length + primitiveRows.length}</span>
            </div>
            <div className="contracts-table-wrap">
              <table>
                <thead><tr><th>Address</th><th>Contract / primitive</th><th>Role</th><th>Authoritative controller</th><th>State</th></tr></thead>
                <tbody>
                  {primitiveRows.map(([name, address]) => (
                    <tr key={name}>
                      <td><code>{short(String(address), 11, 8)}</code></td>
                      <td><strong>{name.replace(/_/g, ' ')}</strong><small>Resolved by Oracle from agent registry</small></td>
                      <td>Protocol primitive</td>
                      <td>{erc8004 ? short(erc8004.nft_owner_address, 8, 6) : 'Unverified'}</td>
                      <td><State ok={Boolean(address && !/^0x0+$/i.test(String(address)))}>{address && !/^0x0+$/i.test(String(address)) ? 'Resolved' : 'Missing'}</State></td>
                    </tr>
                  ))}
                  {contracts.map(contract => (
                    <tr key={contract.address}>
                      <td><code>{short(contract.address, 11, 8)}</code></td>
                      <td><strong>IntegrityMarket</strong><small>{short(contract.question, 42, 0)}</small></td>
                      <td>Creator projection</td>
                      <td>{short(contract.creator, 8, 6)}</td>
                      <td><State ok={!contract.resolved}>{contract.resolved ? 'Resolved' : 'Active'}</State></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!primitiveRows.length && !contracts.length && <div className="empty-state">No owned or controlled contracts were verified for this identity.</div>}
            </div>
          </section>
        )}

        <section className="protocol-note">
          <ShieldCheck size={16} />
          <span>This console exposes protocol evidence and wallet controls. It never renders private keys or treats AIS as authorization by itself.</span>
        </section>
      </div>

      {isRegisterModalOpen && <RegisterAgentModal isOpen={isRegisterModalOpen} onClose={() => setIsRegisterModalOpen(false)} onSuccess={() => setIsRegisterModalOpen(false)} />}
      {isClaimModalOpen && <ClaimAgentModal isOpen={isClaimModalOpen} defaultAddress={selectedAgent?.eth_address} onClose={() => setIsClaimModalOpen(false)} onSuccess={() => setIsClaimModalOpen(false)} />}
    </div>
  );
}
"""

code = code[:match.start()] + clean_return
with open("src/pages/ProtocolDashboardPage.tsx", "w") as f:
    f.write(code)

print("Rewritten cleanly!")
