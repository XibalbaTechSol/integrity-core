import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ethers } from 'ethers';
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
  Database,
  Loader2,
  Info,
  Trash2
} from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { StatusBadge } from '../components/shared/StatusBadge';
import { useDashboard } from '../context/DashboardContext';
import { SubTabs } from '../components/ui/SubTabs';
import { bccMiddleware } from '../services/bccMiddleware';
import { oracle, type BaaDto, type AuditLogEntryDto } from '../services/oracle';
import { SMART_BAA_FACTORY_ADDRESS, COVERED_ENTITY_REGISTRY_ADDRESS, ITK_TOKEN_ADDRESS, ARBITRATOR_ADDRESS, EHR_GATE_ADDRESS, RPC_URL } from '../constants';
import { SMART_BAA_FACTORY_ABI, SMART_BAA_ABI, COVERED_ENTITY_REGISTRY_ABI, ENTITY_TYPE_COVERED_ENTITY, EHR_GATE_ABI } from '../chain/shield';
import { ERC20_ABI, executeAsAgent } from '../chain/markets';

// EHRGate has no on-chain enumeration of gates (accessGates is keyed by a specific
// (patient, recordHash, agent) triplet, no "list all" getter) -- this browser-local
// watchlist of triplets to re-check is a bookmark list, not a source of truth. Each
// entry's actual status is always re-read live from the contract, never cached here.
const CONSENT_WATCHLIST_KEY = 'integrity_mvp_consent_watchlist';
interface WatchedGate { patient: string; recordHash: string; agent: string; }
function loadWatchlist(): WatchedGate[] {
  try { return JSON.parse(localStorage.getItem(CONSENT_WATCHLIST_KEY) || '[]'); } catch { return []; }
}
function saveWatchlist(list: WatchedGate[]) {
  localStorage.setItem(CONSENT_WATCHLIST_KEY, JSON.stringify(list));
}

// ─── Interfaces ──────────────────────────────────────────────────────────────
// BAA/Interaction/Violation are now derived directly from real oracle DTOs
// (BaaDto, AuditLogEntryDto) rather than a hand-rolled mock shape — see
// fetchHealthData below, which mirrors integrity-dashboard's HealthPanel.tsx
// (the validated reference implementation for this exact flow).

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
  address: string; // the disputed SmartBAA's own contract address (its "id" on-chain)
  agent: string;
  coveredEntity: string;
  detail: string;
}

// Real EHRGate.accessGates(patient, recordHash, agent) read — no "status" concept
// beyond isUnlocked; coveredEntity/grantedAt come straight from the contract.
interface ConsentGate {
  patient: string;
  recordHash: string;
  agent: string;
  coveredEntity: string;
  isUnlocked: boolean;
  grantedAt: number;
}

// Real quarantine semantics, mirroring bcc_middleware/app/quarantine.py exactly:
// an agent is quarantined iff Slasher.lockedStakeOf(agent) > 0 — i.e. StakeDto's
// locked_stake, which the oracle already exposes per-agent. No separate contract or
// endpoint needed; quarantine clears itself the moment governance resolves the
// dispute (bcc_middleware never builds a manual "restore" step, so this UI doesn't
// fake one either — see Slasher.sol's resolveDispute).
interface QuarantinedAgent {
  agentId: string;
  agentDid: string;
  lockedStake: string;
  openDisputes: number;
}



export default function HealthPage() {
  const { selectedAgent, addToast } = useDashboard() as any;

  const TABS = [
    { id: 'governance', label: 'Smart BAAs', icon: <FileText size={14} /> },
    { id: 'shield', label: 'EHR Gates', icon: <Lock size={14} /> },
    { id: 'compliance', label: 'Audit & Compliance', icon: <ShieldCheck size={14} /> },
    { id: 'quarantine', label: 'Quarantine', icon: <AlertTriangle size={14} /> },
  ];
  const { walletAddress, agentsLoading, agents } = useDashboard() as any;
  const [baas, setBaas] = useState<BaaDto[]>([]);
  const [saAddr, setSaAddr] = useState<string | null>(null);
  const [consents, setConsents] = useState<ConsentGate[]>([]);
  const [consentsLoading, setConsentsLoading] = useState(true);
  const [busyGate, setBusyGate] = useState<string | null>(null);
  const [logs, setLogs] = useState<InteractionLog[]>([]);
  const [violations, setViolations] = useState<ViolationRecord[]>([]);
  const [arbitratorQueue, setArbitratorQueue] = useState<ViolationRecord[]>([]);
  const [arbitratorQueueLoading, setArbitratorQueueLoading] = useState(false);
  const [quarantinedAgents, setQuarantinedAgents] = useState<QuarantinedAgent[]>([]);
  const [quarantineLoading, setQuarantineLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busyBaa, setBusyBaa] = useState<string | null>(null);

  // Modal / Inputs
  const [isProposeOpen, setIsProposeOpen] = useState(false);
  const [selectedBAA, setSelectedBAA] = useState<BaaDto | null>(null);

  // New BAA Inputs — a real content commitment (keccak256 of the uploaded PDF's
  // bytes), not a random/typed-in hash, mirroring integrity-dashboard's HealthPanel.
  // The covered entity is the connected wallet itself, not a typed-in address.
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [newStake, setNewStake] = useState('5000');

  // New Consent Inputs — real EHRGate.grantAccess args. Patient defaults to the
  // connected wallet since grantAccess is patient-wallet-signed (msg.sender).
  const [newRequester, setNewRequester] = useState('');
  const [newCoveredEntity, setNewCoveredEntity] = useState('');
  const [newRecordHash, setNewRecordHash] = useState('0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');

  // Allowlist
  const [allowlist, setAllowlist] = useState<string[]>([]);
  const [allowlistLoading, setAllowlistLoading] = useState(true);
  const [newAllowlistAgent, setNewAllowlistAgent] = useState('');
  const [allowlistBusy, setAllowlistBusy] = useState(false);
  const [allowlistError, setAllowlistError] = useState<string | null>(null);

  useEffect(() => { 
    setAllowlistLoading(true); 
    bccMiddleware.getClinicalAllowlist().then((result) => setAllowlist(result.agents)).catch(() => setAllowlist([])).finally(() => setAllowlistLoading(false)); 
  }, []);
  const addToAllowlist = async () => { const did = newAllowlistAgent.trim(); if (!did || allowlist.includes(did)) return; setAllowlistBusy(true); setAllowlistError(null); try { const next = [...allowlist, did]; await bccMiddleware.setClinicalAllowlist(next); setAllowlist(next); setNewAllowlistAgent(''); } catch (error) { setAllowlistError(String(error)); } finally { setAllowlistBusy(false); } };
  const removeFromAllowlist = async (did: string) => { setAllowlistBusy(true); setAllowlistError(null); try { const next = allowlist.filter((item) => item !== did); await bccMiddleware.setClinicalAllowlist(next); setAllowlist(next); } catch (error) { setAllowlistError(String(error)); } finally { setAllowlistBusy(false); } };

  // ─── Real Smart BAA registry + audit log (mirrors integrity-dashboard's
  // HealthPanel.fetchData exactly — no mock api.getBAAs/getHealthInteractions). ───
  const fetchHealthData = useCallback(async () => {
    if (!selectedAgent) { setBaas([]); setLogs([]); setViolations([]); setLoading(false); return; }
    setLoading(true);
    const did = selectedAgent.eth_address;
    try {
      const [baaData, auditData] = await Promise.all([
        oracle.getAgentBaas(did).catch(() => [] as BaaDto[]),
        oracle.getAuditLog(did, 50).catch(() => [] as AuditLogEntryDto[]),
      ]);
      setBaas(baaData);
      setLogs(auditData.map((a) => ({
        id: a.id,
        time: new Date(a.created_at).toLocaleString(),
        action: a.event_type,
        resourceHash: a.detail || '—',
        agent: a.agent_id || '—',
        baaId: a.source,
        status: (/pass|allow|permit/i.test(a.decision) ? 'PASSED' : 'BLOCKED') as 'PASSED' | 'BLOCKED',
      })));
      // A BAA in the on-chain Disputed state IS the real violation/review queue —
      // no separate fake "violations" table.
      setViolations(baaData.filter((b) => b.status === 'Disputed').map((b) => ({
        id: b.address,
        address: b.address,
        agent: b.business_associate,
        coveredEntity: b.covered_entity,
        detail: `Disputed SmartBAA with covered entity ${b.covered_entity.slice(0, 10)}… — awaiting on-chain arbitration.`,
      })));
    } catch (err: any) {
      addToast('error', `Health data sync failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [selectedAgent]);

  useEffect(() => {
    const did = selectedAgent?.eth_address;
    if (!did) { setSaAddr(null); return; }
    let active = true;
    oracle.resolveSovereignAgent(did).then(a => { if (active) setSaAddr(a); }).catch(() => { if (active) setSaAddr(null); });
    return () => { active = false; };
  }, [selectedAgent]);

  useEffect(() => {
    fetchHealthData();
  }, [fetchHealthData]);

  // Real quarantine scan: fan out oracle.getStake() across the whole registered fleet
  // (same O(N) client-side pattern DashboardContext already uses for protocol-wide
  // stake aggregation) and flag any agent with locked_stake > 0 — the exact
  // `Slasher.lockedStakeOf(agent) > 0` check bcc_middleware's quarantine.py already
  // enforces at the request-gating layer. This just surfaces that same real state.
  const refreshQuarantine = useCallback(async () => {
    if (agentsLoading) return;
    setQuarantineLoading(true);
    try {
      const results = await Promise.all(
        (agents as any[]).map(async (a) => {
          try {
            const stake = await oracle.getStake(a.eth_address);
            return { a, stake };
          } catch {
            return null;
          }
        })
      );
      const quarantined = results
        .filter((r): r is { a: any; stake: any } => !!r && Number(r.stake.locked_stake) > 0)
        .map(({ a, stake }) => ({
          agentId: a.id,
          agentDid: a.eth_address,
          lockedStake: stake.locked_stake,
          openDisputes: stake.open_disputes,
        }));
      setQuarantinedAgents(quarantined);
    } finally {
      setQuarantineLoading(false);
    }
  }, [agents, agentsLoading]);

  useEffect(() => { refreshQuarantine(); }, [refreshQuarantine]);

  // The arbitrator wallet is the ONLY wallet that can actually resolve a dispute
  // (SmartBAA.arbitrate is onlyArbitrator — see handleArbitrate below), but the
  // per-agent `violations` above only ever shows the currently-selected agent's
  // disputes. A real arbitrator monitoring the whole network needs every disputed
  // BAA across every agent, not one at a time — this fans out oracle.getAgentBaas()
  // across the fleet (same bounded client-side pattern as refreshQuarantine above)
  // only when the connected wallet IS the arbitrator, so it's not wasted work for
  // every other visitor.
  const refreshArbitratorQueue = useCallback(async () => {
    if (!walletAddress || walletAddress.toLowerCase() !== ARBITRATOR_ADDRESS.toLowerCase() || agentsLoading) {
      setArbitratorQueue([]);
      return;
    }
    setArbitratorQueueLoading(true);
    try {
      const perAgent = await Promise.all(
        (agents as any[]).map((a) => oracle.getAgentBaas(a.eth_address).catch(() => [] as BaaDto[]))
      );
      const disputed = perAgent
        .flat()
        .filter((b) => b.status === 'Disputed')
        .map((b) => ({
          id: b.address,
          address: b.address,
          agent: b.business_associate,
          coveredEntity: b.covered_entity,
          detail: `Disputed SmartBAA with covered entity ${b.covered_entity.slice(0, 10)}… — awaiting on-chain arbitration.`,
        }));
      setArbitratorQueue(disputed);
    } finally {
      setArbitratorQueueLoading(false);
    }
  }, [agents, agentsLoading, walletAddress]);

  useEffect(() => { refreshArbitratorQueue(); }, [refreshArbitratorQueue]);

  const getSigner = async () => new ethers.BrowserProvider((window as any).ethereum).getSigner();

  // Real EHRGate.accessGates reads for every (patient, recordHash, agent) triplet this
  // browser has previously interacted with — see CONSENT_WATCHLIST_KEY's comment for
  // why a local watchlist is the correct pattern here (no on-chain enumeration exists).
  const refreshConsents = useCallback(async () => {
    if (!EHR_GATE_ADDRESS) { setConsents([]); setConsentsLoading(false); return; }
    const watched = loadWatchlist();
    if (watched.length === 0) { setConsents([]); setConsentsLoading(false); return; }
    setConsentsLoading(true);
    try {
      const provider = new ethers.JsonRpcProvider(RPC_URL);
      const gate = new ethers.Contract(EHR_GATE_ADDRESS, EHR_GATE_ABI, provider);
      const results = await Promise.all(watched.map(async (w) => {
        try {
          const [coveredEntity, isUnlocked, grantedAt] = await gate.accessGates(w.patient, w.recordHash, w.agent);
          return { ...w, coveredEntity, isUnlocked, grantedAt: Number(grantedAt) } as ConsentGate;
        } catch {
          return { ...w, coveredEntity: '0x0', isUnlocked: false, grantedAt: 0 } as ConsentGate;
        }
      }));
      setConsents(results);
    } finally {
      setConsentsLoading(false);
    }
  }, []);

  useEffect(() => { refreshConsents(); }, [refreshConsents]);

  // ─── Handlers ──────────────────────────────────────────────────────────────

  // Real SmartBAAFactory.createBAA. The caller is the covered entity (the connected
  // wallet), which must be an active Covered Entity in CoveredEntityRegistry —
  // registration is REGISTRAR_ROLE-gated, not self-service, so if the wallet isn't
  // registered we say so plainly, and only self-register if it actually holds
  // REGISTRAR_ROLE (mirrors integrity-dashboard's HealthPanel.ProposeBAAModal).
  const handleProposeBAA = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) { addToast('error', 'Select an agent first.'); return; }
    if (!walletAddress) { addToast('error', 'Connect the covered-entity wallet first.'); return; }
    if (!pdfFile) { addToast('error', 'Attach the BAA document.'); return; }

    setBusyBaa('propose');
    try {
      const businessAssociate = await oracle.resolveSovereignAgent(selectedAgent.eth_address);
      const signer = await getSigner();

      const registry = new ethers.Contract(COVERED_ENTITY_REGISTRY_ADDRESS, COVERED_ENTITY_REGISTRY_ABI, signer);
      const isActive: boolean = await registry.isActiveCoveredEntity(walletAddress);
      if (!isActive) {
        const registrarRole: string = await registry.REGISTRAR_ROLE();
        const canRegister: boolean = await registry.hasRole(registrarRole, walletAddress);
        if (!canRegister) {
          throw new Error('Your wallet is not a registered Covered Entity. Registration requires the protocol registrar (REGISTRAR_ROLE).');
        }
        addToast('info', 'Registering your wallet as a Covered Entity…');
        await (await registry.registerEntity(walletAddress, ENTITY_TYPE_COVERED_ENTITY, 'ipfs://covered-entity')).wait();
      }

      const bytes = new Uint8Array(await pdfFile.arrayBuffer());
      const agreementHash = ethers.keccak256(bytes);
      const requiredCollateral = ethers.parseEther(newStake || '0');

      const factory = new ethers.Contract(SMART_BAA_FACTORY_ADDRESS, SMART_BAA_FACTORY_ABI, signer);
      addToast('info', 'Creating the SmartBAA on-chain…');
      await (await factory.createBAA(businessAssociate, agreementHash, requiredCollateral)).wait();

      addToast('success', 'Smart BAA created. The agent must sign to activate it.');
      setIsProposeOpen(false);
      setPdfFile(null);
      fetchHealthData();
    } catch (err: any) {
      addToast('error', `Failed to create BAA: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyBaa(null);
    }
  };

  // The agent (business associate) activates a Proposed BAA by posting its required
  // collateral — pulled from its SovereignAgent, so we top the SA up + approve, then
  // sign, all routed through SovereignAgent.execute (mirrors StakingPanel's pattern).
  const handleSignBAA = async (baaAddr: string) => {
    if (!saAddr) { addToast('error', 'Agent SovereignAgent not resolved.'); return; }
    if (!walletAddress) { addToast('error', 'Connect the agent controller wallet.'); return; }
    setBusyBaa(baaAddr);
    try {
      const signer = await getSigner();
      const baa = new ethers.Contract(baaAddr, SMART_BAA_ABI, signer);
      const collateral: bigint = await baa.requiredCollateral();
      const itk = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, signer);
      const bal: bigint = await itk.balanceOf(saAddr);
      if (bal < collateral) {
        addToast('info', 'Funding your agent with the BAA collateral…');
        await (await itk.transfer(saAddr, collateral - bal)).wait();
      }
      const allowance: bigint = await itk.allowance(saAddr, baaAddr);
      if (allowance < collateral) {
        const approveData = new ethers.Interface(ERC20_ABI as any).encodeFunctionData('approve', [baaAddr, collateral]);
        await executeAsAgent(signer, saAddr, ITK_TOKEN_ADDRESS, approveData);
      }
      const signData = new ethers.Interface(SMART_BAA_ABI as any).encodeFunctionData('sign', []);
      addToast('info', 'Signing the BAA…');
      await executeAsAgent(signer, saAddr, baaAddr, signData);
      addToast('success', 'BAA signed and activated.');
      fetchHealthData();
    } catch (err: any) {
      addToast('error', `Sign failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyBaa(null);
    }
  };

  // Real SmartBAA.raiseDispute — covered-entity-only (dashboard's HealthPanel never
  // built this; it's new here). We can't route through executeAsAgent since the
  // caller is the CE's own wallet, not the agent.
  const handleRaiseDispute = async (baaAddr: string, coveredEntity: string) => {
    if (!walletAddress || walletAddress.toLowerCase() !== coveredEntity.toLowerCase()) {
      addToast('error', 'Only the covered entity on this BAA can raise a dispute.');
      return;
    }
    setBusyBaa(baaAddr);
    try {
      const signer = await getSigner();
      const baa = new ethers.Contract(baaAddr, SMART_BAA_ABI, signer);
      await (await baa.raiseDispute()).wait();
      addToast('success', 'Dispute raised — awaiting arbitration.');
      fetchHealthData();
      refreshArbitratorQueue();
    } catch (err: any) {
      addToast('error', `Raising dispute failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyBaa(null);
    }
  };

  // Real SmartBAA.revoke — either party, blocked on-chain while Disputed.
  const handleRevokeBAA = async (baaAddr: string) => {
    setBusyBaa(baaAddr);
    try {
      const signer = await getSigner();
      const baa = new ethers.Contract(baaAddr, SMART_BAA_ABI, signer);
      await (await baa.revoke()).wait();
      addToast('success', 'BAA revoked.');
      fetchHealthData();
    } catch (err: any) {
      addToast('error', `Revoke failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyBaa(null);
    }
  };

  // Runs a real WebAuthn passkey ceremony as a local biometric pre-authorization gate
  // before prompting the actual wallet signature. The passkey itself has no
  // cryptographic link to the on-chain transaction — it's a UX gate, not the
  // authorization; the wallet signature below is what actually authorizes.
  const runPasskeyGate = async (label: string): Promise<boolean> => {
    try {
      const challenge = new Uint8Array(32);
      window.crypto.getRandomValues(challenge);
      const credential = await navigator.credentials.create({
        publicKey: {
          challenge,
          rp: { name: 'Integrity Health (EHR Gate)' },
          user: { id: new Uint8Array(16), name: label, displayName: 'Patient Sovereign Identity' },
          pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
          authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required' },
          timeout: 60000,
          attestation: 'none',
        } as any,
      });
      return !!credential;
    } catch {
      addToast('error', 'Passkey authentication cancelled or unsupported — proceeding to wallet signature only.');
      return true; // the passkey is a UX nicety, not a hard requirement — never block the real tx on it
    }
  };

  // Real EHRGate.grantAccess — patient-wallet-signed. The connected wallet IS the
  // patient (msg.sender), so there's no separate "patient address" field to fill in.
  const handleCreateConsent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!EHR_GATE_ADDRESS) { addToast('error', 'EHRGate is not deployed on this network yet.'); return; }
    if (!walletAddress) { addToast('error', 'Connect your wallet (as the patient) first.'); return; }
    if (!ethers.isAddress(newRequester) || !ethers.isAddress(newCoveredEntity)) {
      addToast('error', 'Requesting agent and covered entity must be valid addresses.'); return;
    }
    setBusyGate('create');
    try {
      await runPasskeyGate(`patient-${walletAddress}`);
      const signer = await getSigner();
      const gate = new ethers.Contract(EHR_GATE_ADDRESS, EHR_GATE_ABI, signer);
      addToast('info', 'Granting EHR Gate access…');
      await (await gate.grantAccess(newRecordHash, newRequester, newCoveredEntity)).wait();
      const watched = loadWatchlist();
      const entry = { patient: walletAddress, recordHash: newRecordHash, agent: newRequester };
      if (!watched.some(w => w.patient === entry.patient && w.recordHash === entry.recordHash && w.agent === entry.agent)) {
        saveWatchlist([entry, ...watched]);
      }
      addToast('success', 'EHR Gate access granted.');
      setNewRequester('');
      setNewCoveredEntity('');
      refreshConsents();
    } catch (err: any) {
      addToast('error', `Grant failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyGate(null);
    }
  };

  // Real EHRGate.revokeAccess — patient-wallet-signed.
  const handleRevokeConsent = async (gate: ConsentGate) => {
    if (!walletAddress || walletAddress.toLowerCase() !== gate.patient.toLowerCase()) {
      addToast('error', 'Only the patient who granted this access can revoke it.');
      return;
    }
    const key = `${gate.patient}-${gate.recordHash}-${gate.agent}`;
    setBusyGate(key);
    try {
      await runPasskeyGate(`patient-${gate.patient}`);
      const signer = await getSigner();
      const contract = new ethers.Contract(EHR_GATE_ADDRESS!, EHR_GATE_ABI, signer);
      addToast('info', 'Revoking EHR Gate access…');
      await (await contract.revokeAccess(gate.recordHash, gate.agent)).wait();
      addToast('success', 'EHR Gate access revoked.');
      refreshConsents();
    } catch (err: any) {
      addToast('error', `Revoke failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyGate(null);
    }
  };

  // Real SmartBAA.arbitrate — onlyArbitrator (a fixed neutral address set at factory
  // deploy time, never the CE or the agent). Gated on the connected wallet, exactly
  // like integrity-dashboard's handleResolveViolation — anyone else is told plainly
  // rather than the UI pretending to resolve it.
  const handleArbitrate = async (baaAddr: string, slash: boolean) => {
    if (!walletAddress || walletAddress.toLowerCase() !== ARBITRATOR_ADDRESS.toLowerCase()) {
      addToast('error', 'Only the protocol arbitrator can resolve BAA disputes.');
      return;
    }
    setBusyBaa(baaAddr);
    try {
      const signer = await getSigner();
      const baa = new ethers.Contract(baaAddr, SMART_BAA_ABI, signer);
      await (await baa.arbitrate(slash)).wait();
      addToast('success', slash ? 'Collateral slashed to the covered entity.' : 'Dispute dismissed; BAA restored to Active.');
      fetchHealthData();
      refreshArbitratorQueue();
      refreshQuarantine();
    } catch (err: any) {
      addToast('error', `Arbitration failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusyBaa(null);
    }
  };


  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      
      {/* ─── Hero HIPAA Gateway Bar ─── */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(201, 168, 76, 0.05) 0%, rgba(5, 13, 24, 0.95) 100%)',
          border: '1px solid var(--theme-accent-muted)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6) var(--space-8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-6)',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--theme-accent)' }}>Health Protocol</div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Smart BAA registry, EHR Gates, and Quarantine are all real (Base Sepolia).</span>
        </div>

        {/* ─── HIPAA Stats Strip ─── */}
        <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-5)', textAlign: 'center', minWidth: '120px' }}>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--theme-accent)', lineHeight: 1 }}>
              {loading ? '—' : baas.filter(b => b.status === 'Active').length}
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginTop: '4px' }}>
              Active BAAs
            </div>
          </div>

          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-5)', textAlign: 'center', minWidth: '120px' }}>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--danger)', lineHeight: 1 }}>
              {loading ? '—' : baas.filter(b => b.status === 'Disputed').length}
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginTop: '4px' }}>
              Disputed BAAs
            </div>
          </div>
        </div>
      </div>



      

      {/* ─── Render Tab Contents ─── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-8)", marginTop: "24px" }}>
        
        {/* TAB 1: Smart BAAs */}
        
          <div className="flex-col gap-6" style={{ background: "rgba(0,0,0,0.2)", padding: "24px", borderRadius: "12px", border: "1px solid var(--glass-border)" }}>
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
              
              {/* Active BAAs */}
              <Panel 
                title="Smart BAA Registry" 
                icon={<FileText size={18} color="var(--theme-accent)" />}
                action={
                  <button className="btn btn-primary btn-sm" onClick={() => setIsProposeOpen(true)}>
                    + Propose BAA Contract
                  </button>
                }
              >
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Real, on-chain Business Associate Agreements via <code>SmartBAAFactory</code>/<code>SmartBAA</code>. Locked ITK collateral is slashed only by the protocol arbitrator, on a raised dispute.
                  </p>

                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Covered Entity</th>
                          <th>Status</th>
                          <th>Required Collateral</th>
                          <th>Agreement Hash</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {loading ? (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>Loading…</td></tr>
                        ) : baas.length === 0 ? (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>No BAAs found for this agent.</td></tr>
                        ) : (
                          baas.map(b => {
                            const canSign = b.status === 'Proposed' && !!saAddr && b.business_associate.toLowerCase() === saAddr.toLowerCase();
                            const canDispute = b.status === 'Active' && !!walletAddress && b.covered_entity.toLowerCase() === walletAddress.toLowerCase();
                            const canRevoke = b.status === 'Active' && !!walletAddress &&
                              (b.covered_entity.toLowerCase() === walletAddress.toLowerCase() || (!!saAddr && b.business_associate.toLowerCase() === saAddr.toLowerCase()));
                            return (
                            <tr key={b.address}>
                              <td className="mono" title={b.covered_entity}>{b.covered_entity.substring(0, 15)}...</td>
                              <td><StatusBadge status={b.status} /></td>
                              <td className="mono" style={{ color: 'var(--theme-accent)' }}>{(Number(b.required_collateral) / 1e18).toLocaleString()} ITK</td>
                              <td className="mono" title={b.agreement_hash}>{b.agreement_hash.substring(0, 10)}...</td>
                              <td>
                                <div style={{ display: 'flex', gap: '4px' }}>
                                  {canSign && (
                                    <button className="btn btn-success btn-xs" disabled={busyBaa === b.address} onClick={() => handleSignBAA(b.address)}>
                                      {busyBaa === b.address ? '…' : 'Sign'}
                                    </button>
                                  )}
                                  {canDispute && (
                                    <button className="btn btn-danger btn-xs" disabled={busyBaa === b.address} onClick={() => handleRaiseDispute(b.address, b.covered_entity)}>
                                      Dispute
                                    </button>
                                  )}
                                  {canRevoke && (
                                    <button className="btn btn-outline btn-xs" disabled={busyBaa === b.address} onClick={() => handleRevokeBAA(b.address)}>
                                      Revoke
                                    </button>
                                  )}
                                  <button className="btn btn-outline btn-xs" onClick={() => setSelectedBAA(b)}>Explore</button>
                                </div>
                              </td>
                            </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>

              {/* Legal / Enclave Info */}
              <Panel title="HIPAA Gateway Concept & Safeguards" icon={<ShieldCheck size={18} color="var(--theme-accent)" />}>
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

              {/* Clinical Allowlist */}
              <Panel title="Clinical Allowlist (BCC Runtime Policy)" icon={<Shield size={18} color="var(--theme-accent)" />}>
                <div className="flex-col gap-4">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="text-muted" style={{ fontSize: '0.85rem' }}>Agents permitted at runtime.</span>
                    <span style={{ fontSize: '0.75rem', background: 'var(--bg-secondary)', padding: '2px 8px', borderRadius: '12px' }}>{allowlist.length} agents</span>
                  </div>
                  {allowlistLoading ? <p className="text-muted" style={{ fontSize: '0.85rem' }}>Loading allowlist...</p> : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {allowlist.map((did) => (
                        <div key={did} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
                          <code style={{ fontSize: '0.8rem' }}>{did}</code>
                          <button className="btn btn-ghost btn-xs text-danger" disabled={allowlistBusy} onClick={() => void removeFromAllowlist(did)} title="Remove from allowlist"><Trash2 size={14} /></button>
                        </div>
                      ))}
                      {allowlist.length === 0 && <p className="text-muted" style={{ fontSize: '0.85rem' }}>No agents on the runtime allowlist.</p>}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <input className="input" style={{ flex: 1 }} value={newAllowlistAgent} onChange={(event) => setNewAllowlistAgent(event.target.value)} placeholder="did:integrity:..." />
                    <button className="btn btn-primary btn-sm" disabled={allowlistBusy || !newAllowlistAgent.trim()} onClick={() => void addToAllowlist()} type="button">Add</button>
                  </div>
                  {allowlistError && <p style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{allowlistError}</p>}
                </div>
              </Panel>

              {/* NHI Access Governance */}
              <Panel title="NHI Access Governance (Current MVP Identity View)" icon={<Users size={18} color="var(--theme-accent)" />}>
                <div className="flex-col gap-4">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="text-muted" style={{ fontSize: '0.85rem' }}>Registered Oracle Agents.</span>
                    <span style={{ fontSize: '0.75rem', background: 'var(--bg-secondary)', padding: '2px 8px', borderRadius: '12px' }}>{agents.length} agents</span>
                  </div>
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Agent</th>
                          <th>DID</th>
                          <th>Tier</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agents.length === 0 ? (
                          <tr><td colSpan={4} style={{ textAlign: 'center', padding: '2rem' }} className="text-muted">No agents registered on this network.</td></tr>
                        ) : (
                          agents.map((agent: any) => (
                            <tr key={agent.id}>
                              <td><strong style={{ color: agent.id === selectedAgent?.id ? 'var(--theme-accent)' : 'inherit' }}>{agent.alias || agent.name || agent.id}</strong></td>
                              <td><code style={{ fontSize: '0.75rem' }}>{agent.id.slice(0, 24)}...</code></td>
                              <td>{agent.verification_tier}</td>
                              <td><StatusBadge status="active" /></td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>
            </div>
          </div>

        {/* TAB 2: PHI Access Gates */}
        
          <div className="flex-col gap-6" style={{ background: "rgba(0,0,0,0.2)", padding: "24px", borderRadius: "12px", border: "1px solid var(--glass-border)" }}>
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
              
              {/* Record Gate Consent Contracts */}
              <Panel title="Patient Consent Contracts (EHR Gates)" icon={<Lock size={18} color="var(--theme-accent)" />}>
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Real on-chain consent via <code>EHRGate</code> (Base Sepolia). EHRGate has no on-chain enumeration, so this list is a local bookmark of gates this browser has interacted with — each row's status is always re-read live from the contract, never cached.
                  </p>

                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Patient</th>
                          <th>Requesting Agent</th>
                          <th>Record Hash</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {consentsLoading ? (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>Loading…</td></tr>
                        ) : consents.length === 0 ? (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>No known gates for this browser yet — grant one below.</td></tr>
                        ) : (
                          consents.map(c => {
                            const key = `${c.patient}-${c.recordHash}-${c.agent}`;
                            const canRevoke = c.isUnlocked && !!walletAddress && walletAddress.toLowerCase() === c.patient.toLowerCase();
                            return (
                            <tr key={key}>
                              <td className="mono" title={c.patient} style={{ whiteSpace: 'nowrap' }}>{c.patient.substring(0, 12)}...</td>
                              <td className="mono" title={c.agent} style={{ whiteSpace: 'nowrap' }}>{c.agent.substring(0, 12)}...</td>
                              <td className="mono" title={c.recordHash} style={{ whiteSpace: 'nowrap' }}>{c.recordHash.substring(0, 10)}...</td>
                              <td style={{ whiteSpace: 'nowrap' }}><StatusBadge status={c.isUnlocked ? 'active' : 'pending'} /></td>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                {canRevoke && (
                                  <button className="btn btn-danger btn-sm" disabled={busyGate === key} onClick={() => handleRevokeConsent(c)}>
                                    {busyGate === key ? '…' : 'REVOKE'}
                                  </button>
                                )}
                              </td>
                            </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>

              {/* Grant Consent */}
              <Panel title="Grant EHR Gate Access" icon={<Key size={18} />}>
                <form className="flex-col gap-4" onSubmit={handleCreateConsent}>
                  <div className="form-group">
                    <label className="form-label">Patient (your connected wallet)</label>
                    {walletAddress ? (
                      <div className="input mono" style={{ opacity: 0.8 }}>{walletAddress}</div>
                    ) : (
                      <div style={{ fontSize: '0.75rem', color: 'var(--danger)' }}>Connect a wallet first.</div>
                    )}
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>grantAccess is patient-wallet-signed — you grant access as yourself, not on behalf of another patient.</div>
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="requester-entity">Requesting Agent Address</label>
                    <input
                      id="requester-entity"
                      className="input"
                      placeholder="0x… (the agent's SovereignAgent address)"
                      value={newRequester}
                      onChange={e => setNewRequester(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="covered-entity">Covered Entity Address</label>
                    <input
                      id="covered-entity"
                      className="input"
                      placeholder="0x… (must have an active SmartBAA with the agent)"
                      value={newCoveredEntity}
                      onChange={e => setNewCoveredEntity(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="ehr-record-hash">Medical Record Hash (bytes32)</label>
                    <input
                      id="ehr-record-hash"
                      className="input"
                      value={newRecordHash}
                      onChange={e => setNewRecordHash(e.target.value)}
                      required
                    />
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={busyGate === 'create' || !walletAddress}>
                    {busyGate === 'create' ? 'Granting…' : 'Grant Access'}
                  </button>
                </form>
              </Panel>
            </div>
          </div>

        {/* TAB 3: Audit & Compliance */}
        
          <div className="flex-col gap-6" style={{ background: "rgba(0,0,0,0.2)", padding: "24px", borderRadius: "12px", border: "1px solid var(--glass-border)" }}>
            {/* Interaction Logs + Violations */}
            <div className="grid-cols-3" style={{ gap: 'var(--space-6)' }}>
              
              {/* Interaction Logs */}
              <div className="col-span-2">
                <Panel title="Medical Record Interaction Logs" icon={<Activity size={18} color="var(--theme-accent)" />}>
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
                {(() => {
                  const isArbitrator = !!walletAddress && walletAddress.toLowerCase() === ARBITRATOR_ADDRESS.toLowerCase();
                  const queue = isArbitrator ? arbitratorQueue : violations;
                  const queueLoading = isArbitrator && arbitratorQueueLoading;
                  return (
                    <Panel title={isArbitrator ? 'Arbitration Queue (Network-Wide)' : 'Compliance Review Queue'} icon={<AlertTriangle size={18} color="var(--danger)" />}>
                      <div className="flex-col gap-4">
                        <p className="text-muted" style={{ fontSize: '0.7rem', margin: 0 }}>
                          {isArbitrator
                            ? 'You are connected as the protocol arbitrator — this scans every registered agent\'s disputed SmartBAAs, not just the selected agent.'
                            : 'Real disputed SmartBAAs for the selected agent. Resolving requires connecting the protocol arbitrator\'s wallet.'}
                        </p>
                        {queueLoading ? (
                          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>Scanning fleet for disputes…</div>
                        ) : queue.length === 0 ? (
                          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                            <ShieldCheck size={32} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
                            No violations flagged for review.
                          </div>
                        ) : (
                          queue.map(v => (
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
                                  BAA DISPUTE
                                </span>
                                <ShieldAlert size={16} color="var(--danger)" />
                              </div>
                              <p style={{ fontSize: '0.75rem', color: 'var(--text-primary)', marginBottom: '12px', lineHeight: 1.4 }}>
                                {v.detail}
                              </p>
                              <div className="flex gap-2">
                                <button className="btn btn-danger btn-xs" style={{ flex: 1 }} disabled={busyBaa === v.address} onClick={() => handleArbitrate(v.address, true)}>
                                  Slash Stake
                                </button>
                                <button className="btn btn-ghost btn-xs" style={{ flex: 1, border: '1px solid var(--border)' }} disabled={busyBaa === v.address} onClick={() => handleArbitrate(v.address, false)}>
                                  Dismiss
                                </button>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </Panel>
                  );
                })()}
              </div>
            </div>
          </div>

        {/* TAB 4: Quarantine Zone */}
        
          <div className="flex-col gap-6" style={{ background: "rgba(0,0,0,0.2)", padding: "24px", borderRadius: "12px", border: "1px solid var(--glass-border)" }}>
            <div className="grid-cols-1" style={{ gap: 'var(--space-6)' }}>
              <Panel title="Agent Circuit Breakers (Quarantine Zone)" icon={<AlertTriangle size={18} color="var(--danger)" />}>
                <div className="flex-col gap-4">
                  <p className="text-muted" style={{ fontSize: '0.85rem' }}>
                    Real quarantine state: an agent is quarantined the moment its Slasher clone shows locked stake (an unresolved dispute), the exact same <code>lockedStakeOf(agent) &gt; 0</code> check <code>bcc_middleware</code>'s pre-execution gate enforces on every request. There's no separate "restore" action to build — quarantine clears itself the instant the arbitrator resolves the dispute via <code>SmartBAA.arbitrate</code> (Smart BAAs tab) or the dispute is otherwise released on-chain.
                  </p>

                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Agent</th>
                          <th>Locked Stake</th>
                          <th>Open Disputes</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {quarantineLoading ? (
                          <tr><td colSpan={4} style={{ textAlign: 'center', padding: '2rem' }}>Scanning fleet stake state…</td></tr>
                        ) : quarantinedAgents.length === 0 ? (
                          <tr><td colSpan={4} style={{ textAlign: 'center', padding: '2rem', color: 'var(--success)' }}>No agents currently quarantined.</td></tr>
                        ) : (
                          quarantinedAgents.map(qa => (
                            <tr key={qa.agentId}>
                              <td className="mono" title={qa.agentDid}>{qa.agentDid.substring(0, 24)}...</td>
                              <td className="mono" style={{ color: 'var(--danger)' }}>{(Number(qa.lockedStake) / 1e18).toLocaleString()} ITK</td>
                              <td>{qa.openDisputes}</td>
                              <td>
                                <span style={{
                                  fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                                  background: 'rgba(244, 63, 94, 0.1)', color: 'var(--danger)',
                                  border: '1px solid rgba(244, 63, 94, 0.2)', fontWeight: 700
                                }}>
                                  QUARANTINED
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </Panel>
            </div>
          </div>
      </div>

      {/* ─── Modals ─── */}

      {/* Propose BAA Modal */}
      {isProposeOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div onClick={() => setIsProposeOpen(false)} style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} />
          <form 
            onSubmit={handleProposeBAA}
            style={{ 
              position: 'relative', width: '100%', maxWidth: '450px', background: 'var(--bg-card)', 
              border: '1px solid var(--theme-accent)', borderRadius: 'var(--radius-lg)', padding: '24px', 
              display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
            }}
          >
            <h3 style={{ margin: 0, color: 'white', fontSize: '1.1rem', fontWeight: 700 }}>Propose Smart BAA</h3>

            <div className="form-group">
              <label className="form-label">Covered Entity (your connected wallet)</label>
              {walletAddress ? (
                <div className="input mono" style={{ opacity: 0.8 }}>{walletAddress}</div>
              ) : (
                <div style={{ fontSize: '0.75rem', color: 'var(--danger)' }}>Connect a wallet first.</div>
              )}
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                You create the BAA as the covered entity; <span className="mono">{selectedAgent?.alias || 'the selected agent'}</span> is the business associate.
              </div>
            </div>
            <div className="form-group">
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
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Hashed client-side (keccak256) as the on-chain agreement commitment — the file itself is never uploaded anywhere.</div>
            </div>
            <div className="form-group">
              <label className="form-label">Staked ITK Collateral Amount</label>
              <input
                type="number" className="input" value={newStake}
                onChange={e => setNewStake(e.target.value)} required
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={busyBaa === 'propose' || !walletAddress || !pdfFile}>
              {busyBaa === 'propose' ? 'Creating BAA…' : 'Deploy Smart BAA'}
            </button>
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
              border: '1px solid var(--theme-accent)', borderRadius: 'var(--radius-lg)', padding: '24px', 
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
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Contract Address</span>
                <div style={{ fontSize: '0.8rem' }} className="mono">{selectedBAA.address}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Status</span>
                <div><StatusBadge status={selectedBAA.status} /></div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Covered Entity</span>
                <div style={{ fontSize: '0.8rem' }} className="mono">{selectedBAA.covered_entity}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Business Associate</span>
                <div style={{ fontSize: '0.8rem' }} className="mono">{selectedBAA.business_associate}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Required Collateral</span>
                <div style={{ fontSize: '0.8rem', color: 'var(--theme-accent)' }} className="mono">{(Number(selectedBAA.required_collateral) / 1e18).toLocaleString()} ITK</div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Agreement Hash</span>
                <div style={{ fontSize: '0.8rem', wordBreak: 'break-all' }} className="mono">{selectedBAA.agreement_hash}</div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '12px', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
              <Info size={16} style={{ flexShrink: 0, marginTop: '2px', color: 'var(--text-muted)' }} />
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
                The agreement PDF itself is never uploaded to this app or stored on-chain — only its keccak256 content commitment is. Verifying the document matches this hash requires the original PDF file.
              </p>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
