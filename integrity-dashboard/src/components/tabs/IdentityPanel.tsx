import { useState } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { Panel } from '../shared/Panel';
import { Key, Users, ShieldCheck, Search, Link as LinkIcon, Settings } from 'lucide-react';
import { DIDExplorer } from '../ui/DIDExplorer';
import { RegisterAgentModal } from '../ui/RegisterAgentModal';
import { XNSSearchService } from '../ui/XNSSearchService';
import { ClaimAgentModal } from './ClaimAgentModal';

export function IdentityPanel() {
  const { selectedAgent, fetchData } = useDashboard();
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);
  const [mockMode, setMockMode] = useState(false);

  // Mock-mode is a legacy toggle (the client-side mock-agent filter was removed; the oracle
  // has no /v1/protocol/settings endpoint). Kept as a local UI toggle only — it no longer
  // persists to or fetches from a backend, rather than pretending to via a mock route.
  const toggleMockMode = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMockMode(e.target.checked);
    if (fetchData) fetchData();
  };

  return (
    <div className="flex-col gap-6">
      <Panel title="Decentralized Identifier (DID)" icon={<Key size={18} />}>
        {selectedAgent ? (
          <DIDExplorer agent={selectedAgent} />
        ) : (
          <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center' }}>
            Select an agent from the sidebar to view its Decentralized Identity Document.
          </div>
        )}
      </Panel>

      <Panel title="XNS Search Service" icon={<Search size={18} />}>
        <XNSSearchService />
      </Panel>

      <Panel title="Identity Management" icon={<Users size={18} />}>
        <div className="flex-col gap-4">
           <p className="text-muted" style={{ fontSize: '0.875rem' }}>
              Manage your autonomous agent identities. You can either deploy a new identity or claim ownership of an existing one.
           </p>
           <div className="flex gap-3">
             <button className="btn btn-primary" onClick={() => setIsRegisterModalOpen(true)} style={{ flex: 1 }}>
               <ShieldCheck size={16} style={{ marginRight: '8px' }} /> Register New
             </button>
             <button className="btn btn-outline" onClick={() => setIsClaimModalOpen(true)} style={{ flex: 1 }}>
               <LinkIcon size={16} style={{ marginRight: '8px' }} /> Claim Existing
             </button>
           </div>
        </div>
      </Panel>

      <Panel title="Dashboard Configurations" icon={<Settings size={18} />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
           <p className="text-muted" style={{ fontSize: '0.85rem', margin: 0 }}>
             Configure dashboard state and data mode options.
           </p>
           <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-3) 0', borderTop: '1px solid var(--glass-border)' }}>
             <div>
               <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Enable Mock Mode</div>
               <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Load seeded mock agents instead of only the local Xibalba agent.</div>
             </div>
             <input
               type="checkbox"
               checked={mockMode}
               onChange={toggleMockMode}
               style={{ width: '18px', height: '18px', cursor: 'pointer' }}
             />
           </div>
        </div>
      </Panel>
      
      {isRegisterModalOpen && (
         <RegisterAgentModal
           isOpen={isRegisterModalOpen}
           onClose={() => setIsRegisterModalOpen(false)}
           onSuccess={() => { setIsRegisterModalOpen(false); if (fetchData) fetchData(); }}
         />
      )}
      {isClaimModalOpen && (
         <ClaimAgentModal 
           isOpen={isClaimModalOpen} 
           defaultAddress={selectedAgent?.eth_address}
           onClose={() => setIsClaimModalOpen(false)} 
           onSuccess={() => { setIsClaimModalOpen(false); if (fetchData) fetchData(); }} 
         />
      )}
    </div>
  );
}
