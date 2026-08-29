import { useState } from 'react';
import { useDashboard } from '../../context/DashboardContext';
import { Panel } from '../shared/Panel';
import { Key, Users, ShieldCheck, Search, Link as LinkIcon, Settings, Globe } from 'lucide-react';
import { DIDExplorer } from '../ui/DIDExplorer';
import { RegisterAgentModal } from '../ui/RegisterAgentModal';
import { XNSSearchService } from '../ui/XNSSearchService';
import { XNSRegisterForm } from '../ui/XNSRegisterForm';
import { ClaimAgentModal } from '../ui/ClaimAgentModal';
import { VerificationPanel } from './VerificationPanel';

export function IdentityPanel() {
  const { selectedAgent } = useDashboard();
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);

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

      <VerificationPanel />

      <Panel title="XNS Search Service" icon={<Search size={18} />}>
        <XNSSearchService />
      </Panel>

      <Panel title="Register a Handle" icon={<Globe size={18} />}>
        {selectedAgent ? (
          <XNSRegisterForm />
        ) : (
          <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center' }}>
            Select an agent to register a handle for it.
          </div>
        )}
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


      
      {isRegisterModalOpen && (
         <RegisterAgentModal
           isOpen={isRegisterModalOpen}
           onClose={() => setIsRegisterModalOpen(false)}
           onSuccess={() => { setIsRegisterModalOpen(false); }}
         />
      )}
      {isClaimModalOpen && (
         <ClaimAgentModal 
           isOpen={isClaimModalOpen} 
           defaultAddress={selectedAgent?.eth_address}
           onClose={() => setIsClaimModalOpen(false)} 
           onSuccess={() => { setIsClaimModalOpen(false); }} 
         />
      )}
    </div>
  );
}
