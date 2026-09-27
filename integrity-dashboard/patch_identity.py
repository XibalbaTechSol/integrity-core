import re

with open("src/pages/ProtocolDashboardPage.tsx", "r") as f:
    code = f.read()

# Add imports
imports = """
import { XNSSearchService } from '../components/ui/XNSSearchService';
import { XNSRegisterForm } from '../components/ui/XNSRegisterForm';
import { RegisterAgentModal } from '../components/ui/RegisterAgentModal';
import { ClaimAgentModal } from '../components/ui/ClaimAgentModal';
"""
code = code.replace("import { SubTabs }", imports + "\import { SubTabs }")

# Add state hooks
state_hooks = """
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);
"""
code = code.replace("const [loading, setLoading] = useState(false);", "const [loading, setLoading] = useState(false);\n" + state_hooks)

# Insert the XNS and Management UI right after the agent list panel in the identity tab
xns_ui = """</div></section>

        {(tab === 'overview' || tab === 'identity') && <section className="protocol-grid"><div className="protocol-panel"><div className="panel-heading"><div><span className="panel-label">On-chain name resolution</span><h2>XNS Search Service</h2></div></div><div style={{ padding: '20px' }}><XNSSearchService /></div></div><div className="protocol-panel"><div className="panel-heading"><div><span className="panel-label">Autonomous identities</span><h2>Identity Management</h2></div></div><div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}><p className="text-muted" style={{ fontSize: '0.85rem' }}>Manage your autonomous agent identities. You can either deploy a new identity or claim ownership of an existing one.</p><div style={{ display: 'flex', gap: '10px' }}><button className="primary-button" onClick={() => setIsRegisterModalOpen(true)} style={{ flex: 1 }}>Register New Identity</button><button className="secondary-button" onClick={() => setIsClaimModalOpen(true)} style={{ flex: 1 }}>Claim Existing Identity</button></div></div></div></section>}
        {(tab === 'overview' || tab === 'identity') && <section className="protocol-grid"><div className="protocol-panel"><div className="panel-heading"><div><span className="panel-label">Register</span><h2>Register an XNS Handle</h2></div></div><div style={{ padding: '20px' }}>{selectedAgent ? <XNSRegisterForm /> : <div className="empty-state">Select an agent to register a handle.</div>}</div></div></section>}
        
        {isRegisterModalOpen && <RegisterAgentModal isOpen={isRegisterModalOpen} onClose={() => setIsRegisterModalOpen(false)} onSuccess={() => setIsRegisterModalOpen(false)} />}
        {isClaimModalOpen && <ClaimAgentModal isOpen={isClaimModalOpen} defaultAddress={selectedAgent?.eth_address} onClose={() => setIsClaimModalOpen(false)} onSuccess={() => setIsClaimModalOpen(false)} />}
"""

code = code.replace('</div></div></section>}', xns_ui)

with open("src/pages/ProtocolDashboardPage.tsx", "w") as f:
    f.write(code)
print("Patched ProtocolDashboardPage with XNS/Register/Claim")
