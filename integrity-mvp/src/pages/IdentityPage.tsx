import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { TopBar } from '../components/TopBar';
import { ShieldCheck, Key, Shield, Globe, Database, Copy, UserCheck, User, Cpu, History, FileText, ExternalLink, Rocket, Loader2 } from 'lucide-react';
import { NotionDatabase } from '../components/NotionDatabase';
import { ClaimAgentModal } from '../components/ClaimAgentModal';
import { RegisterAgentModal } from '../components/RegisterAgentModal';
import type { ColumnDef } from '@tanstack/react-table';
import { useAgent } from '../contexts/AgentContext';
import { oracle, type WalletResponse, type AisResponse } from '../services/oracle';
import { XNSSearchService } from '../components/XNSSearchService';
import { Panel } from '../shared/Panel';
import { SeededDataBadge } from '../shared/SeededDataBadge';
import { useAccount, useReadContract } from 'wagmi';
import { singleton } from '../chain/deployments';
import { abis } from '../chain/abis';
import { useSovereignAgentWrite } from '../hooks/useSovereignAgentWrite';
import { useToast } from '../contexts/ToastContext';
import { waitForTransactionReceipt } from '@wagmi/core';
import { wagmiConfig } from '../chain/wagmi';

// --- Mocks ---
const MOCK_CREDENTIALS = [
  { id: '1', type: 'HIPAA Compliance Badge', icon: 'shield', issuer: 'Xibalba Trust Registry', status: 'Valid', validUntil: '2028-01-01' },
  { id: '2', type: 'KYC Provider Clearance', icon: 'key', issuer: 'Chainalysis Oracles', status: 'Valid', validUntil: '2027-05-15' }
];

const CREDENTIAL_COLUMNS: ColumnDef<any>[] = [
  { 
    accessorKey: 'type', 
    header: 'Credential Type', 
    cell: info => (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 500 }}>
        {info.row.original.icon === 'shield' ? <ShieldCheck size={16} className="text-success" /> : <Key size={16} className="text-success" />} 
        {info.getValue() as string}
      </div>
    ) 
  },
  { accessorKey: 'issuer', header: 'Issuer', cell: info => <span style={{ color: 'var(--text-secondary)' }}>{info.getValue() as string}</span> },
  { accessorKey: 'status', header: 'Status', cell: info => <span className="badge badge-success">{info.getValue() as string}</span> },
  { accessorKey: 'validUntil', header: 'Valid Until', cell: info => <span style={{ color: 'var(--text-muted)' }}>{info.getValue() as string}</span> },
];

// --- Shared Micro-styles ---
const statCardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  padding: 'var(--space-3) var(--space-4)',
  background: 'rgba(255, 255, 255, 0.02)',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--border)',
  minWidth: 0,
};

const statLabelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  fontSize: '0.7rem',
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: '2px',
};

export const IdentityPage = () => {
  const { addToast } = useToast();
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isClaimOpen, setIsClaimOpen] = useState(false);
  const [newXnsHandle, setNewXnsHandle] = useState('');
  const [isXnsSubmitting, setIsXnsSubmitting] = useState(false);
  
  const { selectedAgent } = useAgent();
  const { address: connectedAddress, isConnected } = useAccount();
  const { executeViaAgent } = useSovereignAgentWrite();

  const [agentDetails, setAgentDetails] = useState<any>(null);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [ais, setAisData] = useState<AisResponse | null>(null);
  const [auditLog, setAuditLog] = useState<any[]>([]);

  // Fetch Agent Details and Primitives
  useEffect(() => {
    if (!selectedAgent) return;
    let cancelled = false;
    oracle.getAgent(selectedAgent.id)
      .then(details => { if (!cancelled) setAgentDetails(details); })
      .catch(e => console.error("Failed to load agent primitives details:", e));
    return () => { cancelled = true; };
  }, [selectedAgent]);

  // Fetch wallet
  useEffect(() => {
    if (!selectedAgent) return;
    let cancelled = false;
    setWallet(null);
    setWalletError(null);
    oracle.getWallet(selectedAgent.id)
      .then(w => { if (!cancelled) setWallet(w); })
      .catch(e => { if (!cancelled) setWalletError(e instanceof Error ? e.message : 'Failed to reach the oracle'); });
    return () => { cancelled = true; };
  }, [selectedAgent]);

  // Fetch AIS
  useEffect(() => {
    if (!selectedAgent) { setAisData(null); return; }
    let cancelled = false;
    oracle.getAis(selectedAgent.id)
      .then(res => { if (!cancelled) setAisData(res); })
      .catch(() => { if (!cancelled) setAisData(null); });
    return () => { cancelled = true; };
  }, [selectedAgent]);

  // Fetch Audit History
  useEffect(() => {
    if (!selectedAgent) return;
    oracle.getAuditLog(selectedAgent.id)
      .then(logs => setAuditLog(logs))
      .catch(e => console.error("Failed to fetch audit log:", e));
  }, [selectedAgent]);

  const sovereignAgentAddress = agentDetails?.primitives?.sovereign_agent;

  // On-chain primary XNS handle read
  const { data: primaryHandle, refetch: refetchPrimaryHandle } = useReadContract({
    address: singleton('XibalbaNameService'),
    abi: abis.XibalbaNameService,
    functionName: 'primaryHandle',
    args: sovereignAgentAddress ? [sovereignAgentAddress as `0x${string}`] : undefined,
    query: {
      enabled: !!sovereignAgentAddress
    }
  });

  const handleRegisterXns = async () => {
    if (!isConnected || !connectedAddress) {
      addToast('error', 'Connect your wallet first');
      return;
    }
    if (!sovereignAgentAddress) {
      addToast('error', 'Select an agent with registered primitives');
      return;
    }
    if (!newXnsHandle.trim()) {
      addToast('error', 'Enter a valid handle');
      return;
    }

    setIsXnsSubmitting(true);
    try {
      addToast('info', `Submitting handle registration for ${newXnsHandle.trim()}...`);
      
      const xnsAddress = singleton('XibalbaNameService');
      const hash = await executeViaAgent({
        sovereignAgent: sovereignAgentAddress as `0x${string}`,
        target: xnsAddress,
        abi: abis.XibalbaNameService,
        functionName: 'register',
        args: [newXnsHandle.trim()],
      });

      await waitForTransactionReceipt(wagmiConfig, { hash });
      addToast('success', `Handle ${newXnsHandle.trim()} successfully registered on-chain!`);
      setNewXnsHandle('');
      refetchPrimaryHandle();
    } catch (err) {
      console.error(err);
      addToast('error', err instanceof Error ? err.message : 'Transaction failed.');
    } finally {
      setIsXnsSubmitting(false);
    }
  };

  function stabilityTier(score: number): { label: string; color: string } {
    if (score >= 900) return { label: 'AAA', color: 'var(--success)' };
    if (score >= 700) return { label: 'A', color: 'var(--success)' };
    if (score >= 500) return { label: 'B', color: 'var(--warning)' };
    return { label: 'C', color: 'var(--danger)' };
  }

  const did = selectedAgent?.did ?? null;
  const shortDID = did ? (did.length > 36 ? `${did.slice(0, 18)}\u2026${did.slice(-14)}` : did) : null;
  const tier = ais ? stabilityTier(ais.ais) : null;
  const tierColor = tier?.color ?? 'var(--text-muted)';

  return (
    <div className="main-content" style={{ position: 'relative' }}>
      <TopBar title="Identity" />

      <div className="page-content custom-scrollbar" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', minHeight: 0, padding: '24px', width: '100%', maxWidth: '100%' }}>
        
        {/* --- Hero Bar --- */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          style={{
            padding: 'var(--space-5) var(--space-6)',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-4)',
          }}
        >
          <span style={{ color: 'var(--primary)' }}>
            <User size={28} />
          </span>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, letterSpacing: '-0.01em' }}>Identity & primitives</h1>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Decentralized identifiers, on-chain primitive contracts, handles & history
            </p>
          </div>
        </motion.div>

        {selectedAgent ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {/* --- Agent Identity Card Strip --- */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 }}>
              <Panel title="" icon={undefined}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)', padding: 'var(--space-2) 0' }}>
                  
                  {/* DID */}
                  <div style={statCardStyle}>
                    <div style={statLabelStyle}><Key size={12} style={{ marginRight: 4 }} /> Decentralized ID</div>
                    <div className="mono" title={did ?? '\u2014'} style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                      {shortDID ?? <span style={{ color: 'var(--text-muted)' }}>Not Registered</span>}
                    </div>
                  </div>

                  {/* AIS Score */}
                  <div style={statCardStyle}>
                    <div style={statLabelStyle}>AIS Score</div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--primary)', lineHeight: 1 }}>
                      {ais !== null ? `${ais.ais.toFixed(1)} / 1000` : '\u2014'}
                    </div>
                  </div>

                  {/* Verification Tier */}
                  <div style={statCardStyle}>
                    <div style={statLabelStyle}>Verification Tier</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                      {tier ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', padding: '3px 10px', borderRadius: '999px', fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.04em', background: `${tierColor}22`, color: tierColor, border: `1px solid ${tierColor}55` }}>
                          {tier.label}
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{'\u2014'}</span>
                      )}
                    </div>
                  </div>

                  {/* XNS Handle */}
                  <div style={statCardStyle}>
                    <div style={statLabelStyle}><Globe size={12} style={{ marginRight: 4 }} /> XNS Handle</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--gold)' }}>
                      {primaryHandle ? `${primaryHandle}` : <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>None</span>}
                    </div>
                  </div>

                </div>
              </Panel>
            </motion.div>

            {/* Identity Actions Panel */}
            <Panel title="Identity & Onboarding Actions" icon={<Shield size={18} />}>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <button className="btn btn-secondary glass-panel-hover" onClick={() => setIsClaimOpen(true)}>
                  <Shield size={16} /> Claim / Verify Control
                </button>
                <button className="btn btn-primary" onClick={() => setIsRegisterOpen(true)}>
                  <Rocket size={16} /> Register New Agent
                </button>
              </div>
            </Panel>

            {/* Sovereign Identity DID */}
            <Panel title="Sovereign Identity DID" icon={<Key size={18} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  This is the agent's unique self-sovereign Decentralized Identifier (DID). It represents the identity document anchored on-chain.
                </p>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', wordBreak: 'break-all', padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  {selectedAgent?.did ?? 'No agent selected'}
                  {selectedAgent && (
                    <button className="btn btn-secondary" style={{ padding: '6px', background: 'transparent' }} onClick={() => { navigator.clipboard.writeText(selectedAgent.did); addToast('success', 'DID copied to clipboard'); }}><Copy size={16} /></button>
                  )}
                </div>
              </div>
            </Panel>

            {/* --- 7 Primitive Contracts Table Panel --- */}
            <Panel title="On-chain Primitive Contracts" icon={<Cpu size={18} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowX: 'auto' }}>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  The 7 agent-specific primitives registered in the <code style={{ color: 'var(--primary)' }}>XibalbaAgentRegistry</code>.
                </p>

                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left', minWidth: '600px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '12px 8px', fontWeight: 600 }}>Contract Primitive</th>
                      <th style={{ padding: '12px 8px', fontWeight: 600 }}>On-chain Address</th>
                      <th style={{ padding: '12px 8px', fontWeight: 600, width: '100px' }}>Status</th>
                      <th style={{ padding: '12px 8px', fontWeight: 600 }}>Architectural Role</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { key: 'sovereign_agent', label: 'Sovereign Agent', desc: 'Canonical DID anchor, manages EOA controller permissions, and routes execution.' },
                      { key: 'state_anchor', label: 'State Root Anchor', desc: 'Maintains tamper-evident cryptographic Merkle anchors representing agent metrics.' },
                      { key: 'reputation_registry', label: 'Reputation Registry', desc: 'AIS tracking storage containing oracle scores and ZK proving boosts.' },
                      { key: 'slasher', label: 'Slasher', desc: 'ITK token collateral escrow for intent-policy enforcement.' },
                      { key: 'verifier_registry', label: 'Verifier Registry', desc: 'Reference pointers to system-approved ZK Proof Verifier contracts.' },
                      { key: 'compliance_gate', label: 'Compliance Gate', desc: 'Industry compliance vertical validation gates (e.g. HIPAA checks).' },
                      { key: 'agent_profile', label: 'Agent Profile', desc: 'Domain-membership indices and pointers to off-chain IPFS metadata.' }
                    ].map(prim => {
                      const address = agentDetails?.primitives?.[prim.key];
                      const isActive = address && address !== '0x0000000000000000000000000000000000000000';
                      return (
                        <tr key={prim.key} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                          <td style={{ padding: '12px 8px', fontWeight: 700, color: 'var(--text-primary)' }}>{prim.label}</td>
                          <td style={{ padding: '12px 8px' }}>
                            {isActive ? (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontFamily: 'var(--font-mono)' }}>
                                <span style={{ color: 'var(--text-secondary)' }}>{address.slice(0, 8)}...{address.slice(-8)}</span>
                                <button className="btn btn-icon btn-sm" style={{ padding: '3px', background: 'transparent' }} onClick={() => { navigator.clipboard.writeText(address); addToast('success', 'Address copied'); }}><Copy size={12} /></button>
                                <a href={`https://sepolia.basescan.org/address/${address}`} target="_blank" rel="noreferrer" className="btn btn-icon btn-sm" style={{ padding: '3px', background: 'transparent' }}><ExternalLink size={12} /></a>
                              </div>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>Not Deployed</span>
                            )}
                          </td>
                          <td style={{ padding: '12px 8px' }}>
                            {isActive ? (
                              <span className="badge badge-success" style={{ padding: '3px 8px', fontSize: '0.65rem' }}>Active</span>
                            ) : (
                              <span className="badge badge-warning" style={{ padding: '3px 8px', fontSize: '0.65rem' }}>Inactive</span>
                            )}
                          </td>
                          <td style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>{prim.desc}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>

            {/* XNS Handles */}
            <Panel title="XNS Handles & Registry" icon={<Globe size={18} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  XNS registers user-friendly handles mapping directly to agent addresses on-chain.
                </p>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: 'rgba(255,255,255,0.02)', padding: '16px 24px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '4px' }}>
                      Primary Handle
                    </div>
                    <span style={{ fontSize: '1.5rem', fontWeight: '900', fontFamily: 'var(--font-mono)', background: 'linear-gradient(90deg, #fff, #60a5fa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                      {primaryHandle ? `${primaryHandle}` : 'No handle registered'}
                    </span>
                  </div>
                </div>

                {sovereignAgentAddress ? (
                  <div style={{ padding: '20px', background: 'rgba(0,0,0,0.1)', borderRadius: '12px', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>Register Additional Handle</label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input 
                        type="text" 
                        className="input" 
                        placeholder="e.g. auditor-prime.integrity"
                        value={newXnsHandle} 
                        onChange={e => setNewXnsHandle(e.target.value)}
                        disabled={isXnsSubmitting}
                        style={{ flex: 1 }}
                      />
                      <button className="btn btn-primary" onClick={handleRegisterXns} disabled={isXnsSubmitting || !newXnsHandle.trim()}>
                        {isXnsSubmitting ? <Loader2 className="spin" size={16} /> : 'Register'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Sovereign agent address not resolved on-chain. Create primitives first.
                  </div>
                )}
              </div>
            </Panel>

            {/* Lookup Handles */}
            <Panel title="Lookup Handles" icon={<Globe size={18} />}>
              <XNSSearchService />
            </Panel>

            {/* TEE Measurements */}
            <Panel
              title="TEE Measurements"
              icon={<Shield size={18} />}
              action={<SeededDataBadge label="No real attestation document exists yet" />}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Execution Enclave</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>AWS Nitro Enclaves</div>
                </div>
                <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>PCR0 (Image Hash)</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: 'var(--gold)', wordBreak: 'break-all' }}>e3b0c44298fc1c149afbf4c8996fb924...</div>
                </div>
                <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>PCR1 (Kernel Hash)</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: '#60a5fa', wordBreak: 'break-all' }}>8d743a129d20c5411df83e5c92842b10...</div>
                </div>
              </div>
            </Panel>

            {/* Economic Capacity */}
            <Panel title="Economic Capacity" icon={<Database size={18} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {walletError && <div style={{ padding: '12px', background: 'rgba(244,63,94,0.1)', color: '#f43f5e', borderRadius: '8px', fontSize: '0.9rem' }}>Oracle error: {walletError}</div>}
                
                <div style={{ padding: '24px', background: 'rgba(0,0,0,0.2)', borderRadius: '16px', border: '1px solid var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>ITK Token Balance</div>
                    <div style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>
                      {wallet ? Number(wallet.itk_balance).toLocaleString() : '—'}
                    </div>
                  </div>
                  <div style={{ width: '48px', height: '48px', borderRadius: '24px', background: 'rgba(59, 130, 246, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Database size={24} style={{ color: '#60a5fa' }} />
                  </div>
                </div>

                <div style={{ padding: '20px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', fontWeight: 500 }}>Open Market Positions</span>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--warning)' }}>{wallet ? wallet.open_positions.length : '—'}</span>
                </div>
              </div>
            </Panel>

            {/* Verifiable Credentials Wallet */}
            <Panel title="Verifiable Credentials Wallet" icon={<UserCheck size={18} />}>
              <div style={{ marginBottom: '16px' }}>
                <SeededDataBadge label="No credentials system built" />
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '12px', overflow: 'hidden', height: '350px' }}>
                <NotionDatabase data={MOCK_CREDENTIALS} columns={CREDENTIAL_COLUMNS} title="Credentials" readOnly />
              </div>
            </Panel>

            {/* History & Timeline */}
            <Panel title="Durable Agent History & Logs" icon={<History size={18} />}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Reconstructed sequence of events and decisions logged by the off-chain oracle and OPA gateways for this agent.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', position: 'relative', paddingLeft: '24px', borderLeft: '2px solid rgba(255,255,255,0.05)' }}>
                  {auditLog.length > 0 ? (
                    auditLog.map(item => (
                      <div key={item.id} style={{ position: 'relative', marginBottom: '8px' }}>
                        {/* Bullet */}
                        <div style={{ position: 'absolute', left: '-31px', top: '2px', width: '12px', height: '12px', borderRadius: '6px', background: item.decision === 'ALLOW' ? 'var(--success)' : item.decision === 'DENY' ? 'var(--danger)' : 'var(--primary)', border: '2px solid var(--bg-secondary)' }} />
                        
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
                          <span style={{ fontWeight: 700, fontSize: '0.85rem', color: 'white' }}>{item.event_type}</span>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{new Date(item.created_at).toLocaleString()}</span>
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          Decision: <span style={{ fontWeight: 600, color: item.decision === 'ALLOW' ? 'var(--success)' : 'var(--text-primary)' }}>{item.decision}</span> · Source: {item.source}
                        </div>
                        {item.detail && (
                          <pre style={{ margin: '8px 0 0', padding: '8px', background: 'rgba(0,0,0,0.15)', borderRadius: '6px', fontSize: '0.7rem', overflow: 'auto', color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.03)' }}>
                            {item.detail}
                          </pre>
                        )}
                      </div>
                    ))
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', padding: '16px 0' }}>No historical events recorded yet.</div>
                  )}
                </div>
              </div>
            </Panel>

            {/* Raw DID Document payload */}
            {agentDetails?.did_document && (
              <Panel title="DID Document Payload" icon={<FileText size={18} />}>
                <pre style={{ margin: 0, padding: '16px', background: 'rgba(0,0,0,0.3)', borderRadius: '12px', overflow: 'auto', fontSize: '0.8rem', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                  {JSON.stringify(agentDetails.did_document, null, 2)}
                </pre>
              </Panel>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: 0.05 }} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-4)', padding: 'var(--space-10) var(--space-6)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-lg)', border: '1px dashed var(--border)', textAlign: 'center' }}>
              <User size={48} color="var(--text-muted)" strokeWidth={1.5} />
              <div>
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>No Agent Selected</h3>
                <p style={{ margin: '8px 0 0', color: 'var(--text-muted)', fontSize: '0.85rem', maxWidth: '450px', lineHeight: 1.5 }}>
                  Select an autonomous agent from the sidebar list to inspect its details, or execute one of the management actions below.
                </p>
              </div>
            </motion.div>

            {/* Quick Actions Panel */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
              <Panel title="Claim & Verify Control" icon={<Shield size={18} />}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', justifyContent: 'space-between' }}>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Link an existing on-chain Sovereign Agent contract to your dashboard user profile. Generates a cryptographic verification signature challenge.
                  </p>
                  <button className="btn btn-secondary" style={{ width: '100%', justifyContent: 'center', marginTop: '16px' }} onClick={() => setIsClaimOpen(true)}>
                    <Shield size={16} /> Claim / Verify Control
                  </button>
                </div>
              </Panel>

              <Panel title="On-chain Registration" icon={<Rocket size={18} />}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', justifyContent: 'space-between' }}>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Deploys a new SovereignAgent and StateAnchor identity to the blockchain, clones the remaining 5 primitives, and registers domain membership.
                  </p>
                  <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: '16px' }} onClick={() => setIsRegisterOpen(true)}>
                    <Rocket size={16} /> Register New Agent
                  </button>
                </div>
              </Panel>
            </div>
          </div>
        )}

      </div>

      {/* Claim/Verify Agent Modal */}
      <ClaimAgentModal 
        isOpen={isClaimOpen} 
        onClose={() => setIsClaimOpen(false)} 
        onSuccess={() => setIsClaimOpen(false)} 
      />

      {/* Register Agent Modal */}
      <RegisterAgentModal
        isOpen={isRegisterOpen}
        onClose={() => setIsRegisterOpen(false)}
        onSuccess={() => setIsRegisterOpen(false)}
      />
    </div>
  );
};
