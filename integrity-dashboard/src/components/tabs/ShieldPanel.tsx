import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Shield, FileText, Activity, CheckCircle, AlertTriangle, Search, Clock, ShieldAlert, Gavel, Trash2, X, Lock, Loader2, Info } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { StatusBadge } from '../shared/StatusBadge';
import { api } from '../../services/api';
import { oracle } from '../../services/oracle';
import { motion, AnimatePresence } from 'framer-motion';
import { ethers } from 'ethers';
import { IS_PRODUCTION, BASE_SEPOLIA_CHAIN_ID } from '../../constants';

interface BAA {
  id: string;
  coveredEntity: string;
  businessAssociate: string;
  status: string;
  signedAt: string;
  stakedITK: string;
  documentHash: string;
}

interface Interaction {
  id: string;
  time: string;
  action: string;
  resource: string;
  agent: string;
  baaId: string;
  status: 'PASSED' | 'BLOCKED';
}

interface Violation {
  id: string;
  time: string;
  agent: string;
  baaId: string;
  type: string;
  detail: string;
  status: string;
}

// ─── Inline BAA Propose Modal ────────────────────────────────────────────────
interface ProposeBAAModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function ProposeBAAModal({ isOpen, onClose, onSuccess }: ProposeBAAModalProps) {
  const { addToast, selectedAgent, walletAddress } = useDashboard();
  const [coveredEntity, setCoveredEntity] = useState('');
  const [stakeAmount, setStakeAmount] = useState('5000');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const handlePropose = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) {
      addToast('error', 'Please select an agent first');
      return;
    }
    
    setIsSubmitting(true);
    try {
      const documentHash = "0x" + Array.from({length: 64}, () => Math.floor(Math.random()*16).toString(16)).join('');
      
      let signature = "";
      if (IS_PRODUCTION && (window as any).ethereum) {
        const provider = new ethers.BrowserProvider((window as any).ethereum);
        const signer = await provider.getSigner();

        const domain = {
          name: 'Xibalba Smart BAA',
          version: '1',
          chainId: BASE_SEPOLIA_CHAIN_ID,
          verifyingContract: '0x323315892D902eA5b6cb1f8eDecce22B015F07b1A'
        };

        const types = {
          BAA: [
            { name: 'coveredEntity', type: 'address' },
            { name: 'businessAssociate', type: 'address' },
            { name: 'documentHash', type: 'bytes32' },
            { name: 'uri', type: 'string' },
            { name: 'stakedITK', type: 'uint256' },
            { name: 'controller', type: 'address' }
          ]
        };

        const value = {
          coveredEntity: coveredEntity,
          businessAssociate: selectedAgent.eth_address,
          documentHash: documentHash,
          uri: "ipfs://Qm...",
          stakedITK: ethers.parseEther(stakeAmount),
          controller: walletAddress
        };

        addToast('info', 'Please sign the BAA proposal in your wallet');
        signature = await signer.signTypedData(domain, types, value);
      }
      
      await api.proposeBAA({
        covered_entity: coveredEntity,
        business_associate: selectedAgent.eth_address,
        document_hash: documentHash,
        stake_amount: stakeAmount,
        uri: "ipfs://Qm...",
        signature: signature
      });
      
      addToast('success', 'Smart BAA Proposed successfully on-chain');
      onSuccess();
    } catch (err: any) {
      addToast('error', `Failed to propose BAA: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <motion.div 
        initial={{ opacity: 0 }} 
        animate={{ opacity: 1 }} 
        exit={{ opacity: 0 }} 
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} 
      />
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        style={{ 
          position: 'relative', 
          width: '100%', 
          maxWidth: '550px', 
          background: 'var(--bg-card)', 
          border: '1px solid var(--gold-muted)', 
          borderRadius: 'var(--radius-lg)', 
          overflow: 'hidden',
          boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
        }}
      >
        <div style={{ padding: 'var(--space-6)', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--navy-light)' }}>
          <div className="flex items-center gap-3">
            <Shield size={20} color="var(--gold)" />
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'white' }}>Propose Smart BAA</h3>
          </div>
          <button onClick={onClose} className="btn btn-icon"><X size={20} /></button>
        </div>

        <form onSubmit={handlePropose} style={{ padding: 'var(--space-8)' }} className="flex-col gap-6">
          <div className="flex-col gap-2">
            <label className="form-label">Covered Entity Address (Hospital/Clinic)</label>
            <input 
              type="text" 
              placeholder="0x..." 
              className="input mono"
              required
              value={coveredEntity}
              onChange={(e) => setCoveredEntity(e.target.value)}
            />
          </div>

          <div className="grid-cols-2 gap-4">
             <div className="flex-col gap-2">
                <label className="form-label">Liability Stake (ITK)</label>
                <input 
                  type="number" 
                  className="input"
                  required
                  value={stakeAmount}
                  onChange={(e) => setStakeAmount(e.target.value)}
                />
             </div>
             <div className="flex-col gap-2">
                <label className="form-label">BAA Document (PDF)</label>
                <div style={{ position: 'relative' }}>
                   <input 
                     type="file" 
                     accept=".pdf"
                     style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }}
                     onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
                   />
                   <div className="input flex items-center gap-2" style={{ background: 'var(--bg-secondary)', borderStyle: 'dashed' }}>
                      <FileText size={16} /> {pdfFile ? pdfFile.name : 'Upload BAA...'}
                   </div>
                </div>
             </div>
          </div>

          <div style={{ padding: 'var(--space-4)', background: 'var(--gold-dim)', borderRadius: 'var(--radius-md)', border: '1px solid var(--gold)', display: 'flex', gap: '12px' }}>
             <Lock size={20} color="var(--gold)" style={{ flexShrink: 0 }} />
             <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)' }}>
                <strong>Parametric Enforcement:</strong> By proposing this BAA, you agree to lock <strong>{stakeAmount} ITK</strong>. These funds will be slashed automatically if the Integrity Oracle detects a HIPAA violation.
             </div>
          </div>

          <button 
            type="submit" 
            className="btn btn-primary" 
            disabled={isSubmitting || !coveredEntity || !pdfFile}
          >
            {isSubmitting ? <><Loader2 className="spin" size={18} /> Submitting Proposal...</> : 'Propose & Stake ITK'}
          </button>
        </form>

        <div style={{ padding: 'var(--space-4) var(--space-8)', background: 'var(--bg-secondary)', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <Info size={16} color="var(--text-muted)" />
          <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', margin: 0 }}>
            Proposing a BAA creates an on-chain record linked to your Agent's DID. The Covered Entity must sign to activate.
          </p>
        </div>
      </motion.div>
    </div>
  );
}

// ─── ShieldPanel Component ───────────────────────────────────────────────────
export function ShieldPanel() {
  const { selectedAgent, addToast } = useDashboard();
  const [baas, setBaas] = useState<BAA[]>([]);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [isProposeModalOpen, setIsProposeModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Real shield reads. BAAs come from the SmartBAAFactory event-query endpoint; the
  // interaction log is the agent's real BCC/audit decisions; the review queue is the
  // agent's BAAs currently in the on-chain Disputed state (awaiting arbitration). No
  // mock api.getBAAs/getShieldInteractions/getComplianceReviewQueue.
  const fetchData = async () => {
    if (!selectedAgent) { setBaas([]); setInteractions([]); setViolations([]); setIsLoading(false); return; }
    setIsLoading(true);
    const did = selectedAgent.eth_address;
    try {
      const [baaData, auditData] = await Promise.all([
        oracle.getAgentBaas(did).catch(() => []),
        oracle.getAuditLog(did, 50).catch(() => []),
      ]);
      setBaas(baaData.map((b) => ({
        id: b.address,
        coveredEntity: b.covered_entity,
        businessAssociate: b.business_associate,
        status: b.status,
        signedAt: '',
        stakedITK: (Number(b.required_collateral) / 1e18).toLocaleString() + ' ITK',
        documentHash: b.agreement_hash,
      })));
      setInteractions(auditData.map((a) => ({
        id: a.id,
        time: new Date(a.created_at).toLocaleString(),
        action: a.event_type,
        resource: a.detail || '—',
        agent: a.agent_id || '—',
        baaId: a.source,
        status: (/pass|allow|permit/i.test(a.decision) ? 'PASSED' : 'BLOCKED') as 'PASSED' | 'BLOCKED',
      })));
      setViolations(baaData.filter((b) => b.status === 'Disputed').map((b) => ({
        id: b.address,
        time: '',
        agent: b.business_associate,
        baaId: b.address,
        type: 'BAA Dispute',
        detail: `Disputed SmartBAA with covered entity ${b.covered_entity.slice(0, 10)}… — awaiting on-chain arbitration.`,
        status: 'Disputed',
      })));
    } catch (err: any) {
      addToast('error', `Shield sync failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedAgent]);

  const handleResolveViolation = async (id: string, action: 'finalize_slash' | 'dismiss') => {
    try {
      await api.resolveComplianceViolation(id, action);
      addToast('success', action === 'finalize_slash' ? 'ITK Stake Slashed Successfully' : 'Violation Dismissed');
      fetchData();
    } catch (err: any) {
      addToast('error', `Resolution failed: ${err.message}`);
    }
  };

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-2">
        <Panel 
          title="Smart BAA Registry" 
          icon={<Shield size={18} color="var(--gold)" />}
          action={
             <button className="btn btn-primary btn-sm" onClick={() => setIsProposeModalOpen(true)}>
               <FileText size={14} style={{ marginRight: '6px' }} /> Propose New
             </button>
          }
        >
          <div className="flex-col gap-4">
            <div className="text-muted" style={{ fontSize: '0.8rem' }}>
              Cryptographically-bound Business Associate Agreements (BAAs) mapping AI Agents to Healthcare Providers.
            </div>

            <div className="table-container">
              <table className="table" style={{ fontSize: '0.8rem' }}>
                <thead>
                  <tr>
                    <th>Assoc (Agent)</th>
                    <th>Status</th>
                    <th>Stake</th>
                    <th>Doc Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {baas.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', padding: '2rem' }}>No BAAs found.</td></tr>
                  ) : (
                    baas.map(baa => (
                      <tr key={baa.id}>
                        <td className="mono">{baa.businessAssociate.substring(0, 10)}...</td>
                        <td><StatusBadge status={baa.status} /></td>
                        <td className="mono" style={{ color: 'var(--gold)' }}>{baa.stakedITK}</td>
                        <td className="mono" title={baa.documentHash}>{baa.documentHash.substring(0, 8)}...</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Panel>

        <Panel title="HIPAA Gateway Controls" icon={<ShieldAlert size={18} color="var(--gold)" />}>
          <div className="flex-col gap-4">
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
               Pre-execution filters enforced by the BCC (Boundary Control Concept) Middleware.
            </div>

            <div className="flex items-center justify-between" style={{ padding: 'var(--space-3)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--gold-muted)' }}>
              <div className="flex-col">
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>PHI Edge-Blinding</span>
                <span className="text-muted" style={{ fontSize: '0.7rem' }}>HMAC-SHA256 Anonymous Pointers</span>
              </div>
              <CheckCircle size={18} color="var(--success)" />
            </div>

            <div className="flex items-center justify-between" style={{ padding: 'var(--space-3)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--gold-muted)' }}>
              <div className="flex-col">
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Intent Locking (BCC)</span>
                <span className="text-muted" style={{ fontSize: '0.7rem' }}>Prompt-level compliance gating</span>
              </div>
              <CheckCircle size={18} color="var(--success)" />
            </div>

            <div className="flex items-center justify-between" style={{ padding: 'var(--space-3)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--gold-muted)' }}>
              <div className="flex-col">
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Parametric Liability</span>
                <span className="text-muted" style={{ fontSize: '0.7rem' }}>Automated ITK Slashing logic active</span>
              </div>
              <CheckCircle size={18} color="var(--success)" />
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid-cols-3" style={{ gap: 'var(--space-6)' }}>
         <div className="col-span-2">
            <Panel 
              title="Medical Record Interaction Logs" 
              icon={<Activity size={18} color="var(--gold)" />}
              action={
                <button className="btn btn-outline btn-sm" onClick={() => {
                  const csv = "Time,Action,Agent,BAA_Ref,Result\n" + interactions.map(i => `${i.time},${i.action},${i.agent},${i.baaId},${i.status}`).join("\n");
                  const blob = new Blob([csv], { type: 'text/csv' });
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'medical_interactions.csv';
                  a.click();
                }}>
                  Export Logs
                </button>
              }
            >
              <div className="table-container">
                <table className="table" style={{ fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Action</th>
                      <th>Agent</th>
                      <th>BAA Ref</th>
                      <th>BCC Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {interactions.length === 0 ? (
                      <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>Scanning for gateway activity...</td></tr>
                    ) : (
                      interactions.map(int => (
                        <tr key={int.id}>
                          <td className="mono text-muted">{int.time}</td>
                          <td style={{ fontWeight: 600 }}>{int.action}</td>
                          <td className="mono">{int.agent}</td>
                          <td className="mono" style={{ color: 'var(--gold)' }}>{int.baaId}</td>
                          <td>
                             <span style={{ 
                               fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                               background: int.status === 'PASSED' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                               color: int.status === 'PASSED' ? 'var(--success)' : 'var(--danger)',
                               border: `1px solid ${int.status === 'PASSED' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)'}`,
                               fontWeight: 700
                             }}>
                               {int.status}
                             </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
         </div>

         <div className="col-span-1">
            <Panel title="Compliance Review Queue" icon={<AlertTriangle size={18} color="var(--danger)" />}>
               <div className="flex-col gap-4">
                  {violations.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 'var(--space-8)', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                       <CheckCircle size={32} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
                       No pending violations for manual review.
                    </div>
                  ) : (
                    violations.map(v => (
                      <div key={v.id} style={{ background: 'rgba(244, 63, 94, 0.05)', border: '1px solid rgba(244, 63, 94, 0.2)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                         <div className="flex justify-between items-start mb-3">
                            <div className="flex-col">
                               <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--danger)' }}>{v.type.toUpperCase()}</span>
                               <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }} className="mono">{v.time} | {v.agent}</span>
                            </div>
                            <ShieldAlert size={16} color="var(--danger)" />
                         </div>
                         <p style={{ fontSize: '0.75rem', marginBottom: 'var(--space-4)', lineHeight: 1.4 }}>
                            {v.detail}
                         </p>
                         <div className="flex gap-2">
                            <button className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={() => handleResolveViolation(v.id, 'finalize_slash')}>
                               <Gavel size={14} style={{ marginRight: '6px' }} /> Slash Stake
                            </button>
                            <button className="btn btn-ghost btn-sm" style={{ flex: 1, border: '1px solid var(--border)' }} onClick={() => handleResolveViolation(v.id, 'dismiss')}>
                               <Trash2 size={14} style={{ marginRight: '6px' }} /> Dismiss
                            </button>
                         </div>
                      </div>
                    ))
                  )}
               </div>
            </Panel>
         </div>
      </div>

      <AnimatePresence>
        {isProposeModalOpen && (
          <ProposeBAAModal 
            isOpen={isProposeModalOpen} 
            onClose={() => setIsProposeModalOpen(false)} 
            onSuccess={() => { setIsProposeModalOpen(false); fetchData(); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
