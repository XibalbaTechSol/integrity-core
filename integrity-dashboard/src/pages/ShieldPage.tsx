import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  Activity,
  FileText,
  Key,
  Users,
  Lock,
  Unlock,
  AlertTriangle,
  Gavel,
  RefreshCw,
  X,
  Search,
  ArrowRight,
  Database
} from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { StatusBadge } from '../components/shared/StatusBadge';
import { useDashboard } from '../context/useDashboard';

// ─── Interfaces ──────────────────────────────────────────────────────────────

interface BAA {
  id: string;
  coveredEntity: string;
  businessAssociate: string;
  status: 'active' | 'pending' | 'slashed';
  signedAt: string;
  stakedITK: number;
  documentHash: string;
}

interface ConsentContract {
  id: string;
  patientDid: string;
  requestingEntity: string;
  recordHash: string;
  status: 'Authorized' | 'Revoked' | 'Pending';
  lastUpdated: string;
}

interface InteractionLog {
  id: string;
  time: string;
  action: string;
  resourceHash: string;
  agent: string;
  baaId: string;
  status: 'PASSED' | 'BLOCKED';
}

interface ViolationRecord {
  id: string;
  time: string;
  agent: string;
  baaId: string;
  type: string;
  detail: string;
  status: 'pending' | 'slashed' | 'dismissed';
}

interface QuarantinedAgent {
  id: string;
  agentDid: string;
  violationReason: string;
  lockoutExpiry: string;
  status: 'LOCKED' | 'RESTORED';
}

// ─── Sub-Tabs ────────────────────────────────────────────────────────────────

type ShieldSubTab = 'Smart BAAs' | 'PHI Access Gates' | 'Audit & Compliance' | 'Quarantine Zone';

const SUB_TABS: { id: ShieldSubTab; icon: React.ReactNode }[] = [
  { id: 'Smart BAAs', icon: <FileText size={14} /> },
  { id: 'PHI Access Gates', icon: <Lock size={14} /> },
  { id: 'Audit & Compliance', icon: <Activity size={14} /> },
  { id: 'Quarantine Zone', icon: <AlertTriangle size={14} /> },
];

export function ShieldPage() {
  const { selectedAgent, addToast, activeTab: globalActiveTab } = useDashboard() as any;
  const [activeTab, setActiveTab] = useState<ShieldSubTab>('PHI Access Gates');

  useEffect(() => {
    if (globalActiveTab === 'compliance') {
      setActiveTab('Audit & Compliance');
    } else if (globalActiveTab === 'shield') {
      setActiveTab('PHI Access Gates');
    } else if (globalActiveTab === 'governance') {
      setActiveTab('Smart BAAs');
    }
  }, [globalActiveTab]);

  // ─── State Arrays ──────────────────────────────────────────────────────────
  const [baas, setBaas] = useState<BAA[]>([]);
  const [consents, setConsents] = useState<ConsentContract[]>([]);
  const [logs, setLogs] = useState<InteractionLog[]>([]);
  const [violations, setViolations] = useState<ViolationRecord[]>([]);
  const [quarantinedAgents, setQuarantinedAgents] = useState<QuarantinedAgent[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal / Inputs
  const [isProposeOpen, setIsProposeOpen] = useState(false);
  const [selectedBAA, setSelectedBAA] = useState<BAA | null>(null);
  
  // New BAA Inputs
  const [newCE, setNewCE] = useState('');
  const [newDocHash, setNewDocHash] = useState('');
  const [newStake, setNewStake] = useState('5000');

  // New Consent Inputs
  const [newPatientDid, setNewPatientDid] = useState('did:xibalba:patient:0x981a...f281');
  const [newRequester, setNewRequester] = useState('0xHealth_Provider_Clinic_88a');
  const [newRecordHash, setNewRecordHash] = useState('0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');

  // ─── Seed initial realistic Mock HIPAA Database ──────────────────────────
  const loadDefaultData = () => {
    const agentAddr = selectedAgent?.eth_address || '0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556';
    const agentAlias = selectedAgent?.alias || 'Xibalba Master Agent';

    const defaultBaas: BAA[] = [
      { id: 'baa_contract_01', coveredEntity: '0xMayo_Clinic_Minnesota_39a', businessAssociate: agentAddr, status: 'active', signedAt: '2026-06-18 10:30', stakedITK: 10000, documentHash: '0x7e8b9...f201d' },
      { id: 'baa_contract_02', coveredEntity: '0xUW_Health_Madison_f29c', businessAssociate: agentAddr, status: 'pending', signedAt: '-', stakedITK: 5000, documentHash: '0x3c91d...002aa' }
    ];

    const defaultConsents: ConsentContract[] = [
      { id: 'con_gate_101', patientDid: 'did:xibalba:patient:0x71c7...281b', requestingEntity: '0xMayo_Clinic_Minnesota_39a', recordHash: '0x8f1a32...f2910', status: 'Authorized', lastUpdated: '2026-06-24 16:45' },
      { id: 'con_gate_102', patientDid: 'did:xibalba:patient:0xaa12...009f', requestingEntity: agentAddr, recordHash: '0xc5d246...e500b', status: 'Pending', lastUpdated: '2026-06-25 01:10' }
    ];

    const defaultLogs: InteractionLog[] = [
      { id: 'log_01', time: '2026-06-25 01:50:23', action: 'DECRYPT_EHR', resourceHash: '0x8f1a32...f2910', agent: agentAlias, baaId: 'baa_contract_01', status: 'PASSED' },
      { id: 'log_02', time: '2026-06-25 02:02:11', action: 'QUERY_PATIENT_PHI', resourceHash: '0xc5d246...e500b', agent: agentAlias, baaId: 'baa_contract_02', status: 'BLOCKED' }
    ];

    const defaultViolations: ViolationRecord[] = [
      { id: 'viol_01', time: '2026-06-25 02:02:11', agent: agentAlias, baaId: 'baa_contract_02', type: 'unauthorized_phi_query', detail: 'Attempted to query out-of-bounds EHR record without active BAA consent approval signature.', status: 'pending' }
    ];

    const defaultQuarantined: QuarantinedAgent[] = [
      { id: 'q_01', agentDid: 'did:intg:agent-007', violationReason: 'PHI Exfiltration Attempt (SSN Match)', lockoutExpiry: new Date(Date.now() + 15*60*1000).toISOString(), status: 'LOCKED' }
    ];

    setBaas(defaultBaas);
    setConsents(defaultConsents);
    setLogs(defaultLogs);
    setViolations(defaultViolations);
    setQuarantinedAgents(defaultQuarantined);
    setLoading(false);
  };

  useEffect(() => {
    loadDefaultData();
  }, [selectedAgent]);

  // ─── Handlers ──────────────────────────────────────────────────────────────

  const handleProposeBAA = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) return;
    const newB: BAA = {
      id: 'baa_contract_' + Math.floor(Math.random() * 1000),
      coveredEntity: newCE || '0xGeneric_Clinic_Address',
      businessAssociate: selectedAgent.eth_address,
      status: 'pending',
      signedAt: '-',
      stakedITK: parseFloat(newStake) || 5000,
      documentHash: newDocHash || '0xe3b0c442...9852b855'
    };
    setBaas(prev => [newB, ...prev]);
    addToast('success', 'Smart BAA contract proposed successfully.');
    setIsProposeOpen(false);
    setNewCE('');
    setNewDocHash('');
  };

  const handleSignBAA = (id: string) => {
    setBaas(prev => prev.map(b => b.id === id ? { ...b, status: 'active', signedAt: new Date().toISOString().replace('T', ' ').substring(0, 16) } : b));
    addToast('success', 'Smart BAA Contract Signed & Enforced.');
  };

  const handleCreateConsent = (e: React.FormEvent) => {
    e.preventDefault();
    const newC: ConsentContract = {
      id: 'con_gate_' + Math.floor(Math.random() * 1000),
      patientDid: newPatientDid,
      requestingEntity: newRequester,
      recordHash: newRecordHash,
      status: 'Pending',
      lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16)
    };
    setConsents(prev => [newC, ...prev]);
    addToast('success', 'Consent Contract gating record proposed.');
  };

  const handleToggleConsent = async (id: string, action: 'Authorized' | 'Revoked') => {
    try {
      addToast('info', 'Awaiting Biometric Passkey signature...');
      
      const challenge = new Uint8Array(32);
      window.crypto.getRandomValues(challenge);
      
      const publicKeyCredentialCreationOptions = {
          challenge: challenge,
          rp: {
              name: "Xibalba Shield (EHR Gate)"
          },
          user: {
              id: new Uint8Array(16),
              name: "patient-" + id,
              displayName: "Patient Sovereign Identity"
          },
          pubKeyCredParams: [{alg: -7, type: "public-key"}],
          authenticatorSelection: {
              authenticatorAttachment: "platform", // Forces Touch ID / Windows Hello
              userVerification: "required"
          },
          timeout: 60000,
          attestation: "none"
      } as any;

      const credential = await navigator.credentials.create({
          publicKey: publicKeyCredentialCreationOptions
      });

      if (credential) {
        setConsents(prev => prev.map(c => c.id === id ? { ...c, status: action, lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16) } : c));
        addToast('success', `EHR Gate successfully updated to: ${action} via Passkey Signature.`);
      }
    } catch (error) {
      console.error(error);
      addToast('error', 'Passkey authentication cancelled or unsupported on this device.');
    }
  };

  const handleSlashViolation = (violationId: string, baaId: string) => {
    setViolations(prev => prev.map(v => v.id === violationId ? { ...v, status: 'slashed' } : v));
    setBaas(prev => prev.map(b => b.id === baaId ? { ...b, status: 'slashed' } : b));
    addToast('error', 'HIPAA Violation confirmed: Locked ITK Stake Slashed.');
  };

  const handleDismissViolation = (id: string) => {
    setViolations(prev => prev.map(v => v.id === id ? { ...v, status: 'dismissed' } : v));
    addToast('info', 'Violation alert dismissed.');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      
      {/* ─── Hero HIPAA Gateway Bar ─── */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(201, 168, 76, 0.05) 0%, rgba(5, 13, 24, 0.95) 100%)',
          border: '1px solid var(--gold-muted)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6) var(--space-8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-6)',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-1)' }}>
            <Shield size={24} color="var(--gold)" />
            <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800, color: 'white', letterSpacing: '-0.02em' }}>
              Xibalba Shield
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Decentralized HIPAA Compliance, Automated Smart BAAs &amp; Patient-Controlled PHI Access Gating
          </p>
        </div>

        {/* ─── HIPAA Stats Strip ─── */}
        <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-5)', textAlign: 'center', minWidth: '120px' }}>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--gold)', lineHeight: 1 }}>
              {baas.filter(b => b.status === 'active').length}
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginTop: '4px' }}>
              Active BAAs
            </div>
          </div>

          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-5)', textAlign: 'center', minWidth: '120px' }}>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--success)', lineHeight: 1 }}>
              100%
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginTop: '4px' }}>
              Enclave Integrity
            </div>
          </div>
        </div>
      </div>

      {/* ─── Sub-Nav Toggles ─── */}
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        {SUB_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: 'var(--space-2) var(--space-4)',
                borderRadius: '999px',
                border: isActive ? '1px solid var(--gold)' : '1px solid var(--glass-border)',
                background: isActive ? 'var(--gold-muted)' : 'var(--bg-card)',
                color: isActive ? 'var(--gold)' : 'var(--text-muted)',
                fontWeight: isActive ? 700 : 500,
                fontSize: '0.85rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.icon}
              {tab.id}
            </button>
          );
        })}
      </div>

      {/* ─── Render Tab Contents ─── */}
      <AnimatePresence mode="wait">
        
        {/* TAB 1: Smart BAAs */}
        {activeTab === 'Smart BAAs' && (
          <motion.div
            key="baas"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex-col gap-6"
          >
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
              
              {/* Active BAAs */}
              <Panel 
                title="Smart BAA Registry" 
                icon={<FileText size={18} color="var(--gold)" />}
                action={
                  <button className="btn btn-primary btn-sm" onClick={() => setIsProposeOpen(true)}>
                    + Propose BAA Contract
                  </button>
                }
              >
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Business Associate Agreements (BAAs) deployed as auto-enforcing smart contracts. Locked ITK tokens act as parametric collateral slashed automatically upon enclave leakage verification.
                  </p>
                  
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Covered Entity</th>
                          <th>Status</th>
                          <th>Staked Collateral</th>
                          <th>Doc Hash</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {baas.map(b => (
                          <tr key={b.id}>
                            <td className="mono" title={b.coveredEntity}>{b.coveredEntity.substring(0, 15)}...</td>
                            <td><StatusBadge status={b.status} /></td>
                            <td className="mono" style={{ color: 'var(--gold)' }}>{b.stakedITK.toLocaleString()} ITK</td>
                            <td className="mono">{b.documentHash.substring(0, 8)}...</td>
                            <td>
                              <div style={{ display: 'flex', gap: '4px' }}>
                                {b.status === 'pending' && (
                                  <button className="btn btn-success btn-xs" onClick={() => handleSignBAA(b.id)}>Sign</button>
                                )}
                                <button className="btn btn-outline btn-xs" onClick={() => setSelectedBAA(b)}>Explore</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>

              {/* Legal / Enclave Info */}
              <Panel title="HIPAA Gateway Concept & Safeguards" icon={<ShieldCheck size={18} color="var(--gold)" />}>
                <div className="flex-col gap-4" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
                  <div style={{ padding: '16px', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-md)' }}>
                    <strong>Parametric Enforcement:</strong> BAA contracts are no longer passive paper. Under Xibalba Shield, the contract acts as a cryptographic custodian of performance. If a validator enclave leaks PHI, the contract executes the slash automatically.
                  </div>
                  
                  {[
                    { title: 'TEE Hardware Isolation', desc: 'Medical records are queried inside Secure Enclaves (Intel SGX) with zero memory visibility to host operators.' },
                    { title: 'Edge-Blinding', desc: 'No unblinded PHI is committed to the blockchain ledger. We store cryptographic SHA-256 hashes of record histories.' },
                    { title: 'Intent Verification', desc: 'BCC boundary controls audit queries in real-time, blocking outbound transmission of patient datasets.' }
                  ].map((x, i) => (
                    <div key={i} style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)' }}>
                      <strong style={{ display: 'block', color: 'white', marginBottom: '2px' }}>{x.title}</strong>
                      <span className="text-muted" style={{ fontSize: '0.8rem' }}>{x.desc}</span>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          </motion.div>
        )}

        {/* TAB 2: PHI Access Gates */}
        {activeTab === 'PHI Access Gates' && (
          <motion.div
            key="gates"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex-col gap-6"
          >
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
              
              {/* Record Gate Consent Contracts */}
              <Panel title="Patient Consent Contracts (EHR Gates)" icon={<Lock size={18} color="var(--gold)" />}>
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Access gating contracts governing record releases. The patient maintains complete digital sovereignty; only the record hashes are validated on-chain to authorize queries.
                  </p>
                  
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Patient DID</th>
                          <th>Requester</th>
                          <th>Record Hash</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {consents.map(c => (
                          <tr key={c.id}>
                            <td className="mono" title={c.patientDid} style={{ whiteSpace: 'nowrap' }}>{c.patientDid.substring(0, 15)}...</td>
                            <td className="mono" title={c.requestingEntity} style={{ whiteSpace: 'nowrap' }}>{c.requestingEntity.substring(0, 12)}...</td>
                            <td className="mono" style={{ whiteSpace: 'nowrap' }}>{c.recordHash.substring(0, 10)}...</td>
                            <td style={{ whiteSpace: 'nowrap' }}><StatusBadge status={c.status.toLowerCase()} /></td>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <div style={{ display: 'flex', gap: '4px' }}>
                                {c.status !== 'Authorized' && (
                                  <button className="btn btn-success btn-sm" onClick={() => handleToggleConsent(c.id, 'Authorized')}>AUTHORIZE</button>
                                )}
                                {c.status !== 'Revoked' && (
                                  <button className="btn btn-danger btn-sm" onClick={() => handleToggleConsent(c.id, 'Revoked')}>REVOKE</button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>

              {/* Propose Consent Request */}
              <Panel title="Request / Register Consent Gate" icon={<Key size={18} />}>
                <form className="flex-col gap-4" onSubmit={handleCreateConsent}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="patient-did">Patient DID</label>
                    <input 
                      id="patient-did"
                      className="input" 
                      value={newPatientDid} 
                      onChange={e => setNewPatientDid(e.target.value)} 
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="requester-entity">Requesting Entity Address</label>
                    <input 
                      id="requester-entity"
                      className="input" 
                      value={newRequester} 
                      onChange={e => setNewRequester(e.target.value)} 
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="ehr-record-hash">Medical Record Hash (SHA-256)</label>
                    <input 
                      id="ehr-record-hash"
                      className="input" 
                      value={newRecordHash} 
                      onChange={e => setNewRecordHash(e.target.value)} 
                    />
                  </div>
                  <button type="submit" className="btn btn-primary">
                    Deploy Consent Gate Contract
                  </button>
                </form>
              </Panel>
            </div>
          </motion.div>
        )}

        {/* TAB 3: Audit & Compliance */}
        {activeTab === 'Audit & Compliance' && (
          <motion.div
            key="audit"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex-col gap-6"
          >
            {/* Interaction Logs + Violations */}
            <div className="grid-cols-3" style={{ gap: 'var(--space-6)' }}>
              
              {/* Interaction Logs */}
              <div className="col-span-2">
                <Panel title="Medical Record Interaction Logs" icon={<Activity size={18} color="var(--gold)" />}>
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Action</th>
                          <th>Resource Hash</th>
                          <th>Agent</th>
                          <th>Result</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logs.map(l => (
                          <tr key={l.id}>
                            <td className="mono text-muted">{l.time}</td>
                            <td style={{ fontWeight: 600 }}>{l.action}</td>
                            <td className="mono">{l.resourceHash}</td>
                            <td>{l.agent}</td>
                            <td>
                              <span style={{
                                fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                                background: l.status === 'PASSED' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                                color: l.status === 'PASSED' ? 'var(--success)' : 'var(--danger)',
                                border: `1px solid ${l.status === 'PASSED' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)'}`,
                                fontWeight: 700
                              }}>
                                {l.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>

              {/* Violations Review Queue */}
              <div className="col-span-1">
                <Panel title="Compliance Review Queue" icon={<AlertTriangle size={18} color="var(--danger)" />}>
                  <div className="flex-col gap-4">
                    {violations.filter(v => v.status === 'pending').length === 0 ? (
                      <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                        <ShieldCheck size={32} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
                        No violations flagged for review.
                      </div>
                    ) : (
                      violations.filter(v => v.status === 'pending').map(v => (
                        <div
                          key={v.id}
                          style={{
                            background: 'rgba(244, 63, 94, 0.05)',
                            border: '1px solid rgba(244, 63, 94, 0.2)',
                            borderRadius: 'var(--radius-md)',
                            padding: 'var(--space-4)',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--danger)' }}>
                              {v.type.toUpperCase()}
                            </span>
                            <ShieldAlert size={16} color="var(--danger)" />
                          </div>
                          <p style={{ fontSize: '0.75rem', color: 'var(--text-primary)', marginBottom: '12px', lineHeight: 1.4 }}>
                            {v.detail}
                          </p>
                          <div className="flex gap-2">
                            <button className="btn btn-danger btn-xs" style={{ flex: 1 }} onClick={() => handleSlashViolation(v.id, v.baaId)}>
                              Slash Stake
                            </button>
                            <button className="btn btn-ghost btn-xs" style={{ flex: 1, border: '1px solid var(--border)' }} onClick={() => handleDismissViolation(v.id)}>
                              Dismiss
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </Panel>
              </div>
            </div>
          </motion.div>
        )}

        {/* TAB 4: Quarantine Zone */}
        {activeTab === 'Quarantine Zone' && (
          <motion.div
            key="quarantine"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex-col gap-6"
          >
            <div className="grid-cols-1" style={{ gap: 'var(--space-6)' }}>
              <Panel title="Agent Circuit Breakers (Quarantine Zone)" icon={<AlertTriangle size={18} color="var(--danger)" />}>
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Agents that have violated the OPA HIPAA intent policies or lacked active BAA smart contracts are locked out at the pre-execution middleware layer. Their network access is severed until the lockout expires.
                  </p>
                  
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Agent DID</th>
                          <th>Violation Reason</th>
                          <th>Lockout Expiry</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {quarantinedAgents.map(qa => (
                          <tr key={qa.id}>
                            <td className="mono" title={qa.agentDid}>{qa.agentDid}</td>
                            <td style={{ color: 'var(--danger)', fontWeight: 600 }}>{qa.violationReason}</td>
                            <td className="mono">{new Date(qa.lockoutExpiry).toLocaleTimeString()}</td>
                            <td>
                              <span style={{
                                fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                                background: qa.status === 'LOCKED' ? 'rgba(244, 63, 94, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                                color: qa.status === 'LOCKED' ? 'var(--danger)' : 'var(--success)',
                                border: `1px solid ${qa.status === 'LOCKED' ? 'rgba(244, 63, 94, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
                                fontWeight: 700
                              }}>
                                {qa.status}
                              </span>
                            </td>
                            <td>
                              {qa.status === 'LOCKED' && (
                                <button className="btn btn-outline btn-xs" onClick={() => {
                                  setQuarantinedAgents(prev => prev.map(q => q.id === qa.id ? { ...q, status: 'RESTORED' } : q));
                                  addToast('success', 'Manual override: Agent restored from quarantine.');
                                }}>
                                  Force Restore
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── Modals ─── */}

      {/* Propose BAA Modal */}
      {isProposeOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div onClick={() => setIsProposeOpen(false)} style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} />
          <form 
            onSubmit={handleProposeBAA}
            style={{ 
              position: 'relative', width: '100%', maxWidth: '450px', background: 'var(--bg-card)', 
              border: '1px solid var(--gold)', borderRadius: 'var(--radius-lg)', padding: '24px', 
              display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
            }}
          >
            <h3 style={{ margin: 0, color: 'white', fontSize: '1.1rem', fontWeight: 700 }}>Propose Smart BAA</h3>
            
            <div className="form-group">
              <label className="form-label">Covered Entity Clinic/Hospital</label>
              <input 
                type="text" className="input" placeholder="e.g. 0xMayo_Clinic_Minnesota_39a" 
                value={newCE} onChange={e => setNewCE(e.target.value)} required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Document Hash (BAA PDF Hash)</label>
              <input 
                type="text" className="input" placeholder="e.g. 0xe3b0c442..." 
                value={newDocHash} onChange={e => setNewDocHash(e.target.value)} required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Staked ITK Collateral Amount</label>
              <input 
                type="number" className="input" value={newStake} 
                onChange={e => setNewStake(e.target.value)} required
              />
            </div>
            <button type="submit" className="btn btn-primary">Deploy Smart BAA</button>
          </form>
        </div>
      )}

      {/* Explore BAA Modal */}
      {selectedBAA && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div onClick={() => setSelectedBAA(null)} style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} />
          <div 
            style={{ 
              position: 'relative', width: '100%', maxWidth: '600px', background: 'var(--bg-card)', 
              border: '1px solid var(--gold)', borderRadius: 'var(--radius-lg)', padding: '24px', 
              display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: '0 20px 50px rgba(0,0,0,0.6)',
              maxHeight: '90vh', overflowY: 'auto'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', paddingBottom: '12px' }}>
              <h3 style={{ margin: 0, color: 'white', fontSize: '1.1rem', fontWeight: 700 }}>Explore HIPAA Smart BAA</h3>
              <button onClick={() => setSelectedBAA(null)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={20} /></button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: 'var(--radius-md)' }}>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Covered Entity</span>
                <div style={{ fontSize: '0.8rem' }} className="mono">{selectedBAA.coveredEntity}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Status</span>
                <div><StatusBadge status={selectedBAA.status} /></div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Collateral Committed</span>
                <div style={{ fontSize: '0.8rem', color: 'var(--gold)' }} className="mono">{selectedBAA.stakedITK.toLocaleString()} ITK</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Doc Hash</span>
                <div style={{ fontSize: '0.8rem' }} className="mono">{selectedBAA.documentHash}</div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '12px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Agreement Document View</span>
              <div style={{ background: '#fff', color: '#333', padding: '16px', borderRadius: '4px', fontFamily: 'serif', fontSize: '0.8rem', lineHeight: 1.4, maxHeight: '200px', overflowY: 'auto', marginTop: '6px' }}>
                <h4 style={{ textAlign: 'center', margin: '0 0 12px 0' }}>HIPAA Business Associate Agreement</h4>
                <p>This Business Associate Agreement is cryptographically executed and automatically enforced by and between the Covered Entity and the autonomous Business Associate Agent.</p>
                <p><strong>1. PHI Access &amp; Confidentiality:</strong> The Business Associate shall only use and disclose PHI inside secure hardware isolation enclaves (TEEs) to prevent data containment violations.</p>
                <p><strong>2. Parametric Liability:</strong> The Business Associate commits {selectedBAA.stakedITK.toLocaleString()} ITK collateral to this contract. Verification of a PHI leak by the Oracle Registry triggers automatic stake slashing.</p>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
