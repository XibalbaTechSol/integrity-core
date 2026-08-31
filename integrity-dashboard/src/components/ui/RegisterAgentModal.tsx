import React from 'react';
import { ethers } from 'ethers';
import { X, Loader2, Check, ExternalLink } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';
import {
  AGENT_PRIMITIVES_FACTORY_ADDRESS,
  ORACLE_SIGNER_ADDRESS,
  DOMAINS,
  DOMAIN_REGISTRY_ADDRESS,
  XIBALBA_AGENT_REGISTRY_ADDRESS,
  RPC_URL,
  EXPLORER_URL,
} from '../../constants';
import {
  SOVEREIGN_AGENT_ABI, SOVEREIGN_AGENT_BYTECODE,
  STATE_ANCHOR_ABI, STATE_ANCHOR_BYTECODE,
} from '../../chain/bytecode';

// Real on-chain agent registration (Class C), the ethers port of integrity-dashboard's
// RegisterAgentModal. Runs the exact sequence integrity-sdk's registration.py does:
//   1. Deploy the agent's own SovereignAgent (account contract, DID baked in).
//   2. Deploy its own StateAnchor (admin = the SovereignAgent).
//   3. Route SovereignAgent.execute -> StateAnchor.grantRole(ANCHOR_ROLE, oracleSigner)
//      so the oracle can anchor this agent's Merkle roots. ANCHOR_ROLE is read LIVE
//      from the deployed clone — NOT a hardcoded constant (the dashboard used a garbage hash).
//   4. AgentPrimitivesFactory.registerPrimitives clones the remaining 5 primitives and
//      atomically registers all 7 into XibalbaAgentRegistry.
//   5. Record the agent in the oracle DB (which independently re-verifies the 7
//      addresses against the registry on-chain before accepting).
// Four wallet-confirmed txs; each step's result is held in state so a mid-sequence
// revert resumes from the failed step rather than redeploying from scratch.

// Minimal factory ABI: just the write + the event we parse the clone addresses out of.
const FACTORY_ABI = [
  'function registerPrimitives(address sovereignAgent, address stateAnchor, string did, bytes32 domainId, uint8 vertical, string profileURI) returns (address reputationRegistry, address slasher, address verifierRegistry, address complianceGate, address agentProfile)',
  'event PrimitivesRegistered(bytes32 indexed didHash, address indexed sovereignAgent, address indexed controller, address stateAnchor, address reputationRegistry, address slasher, address verifierRegistry, address complianceGate, address agentProfile, bytes32 domainId)',
] as const;

// Read-only preflight ABI: the exact two checks AgentPrimitivesFactory.registerPrimitives
// makes before deploying anything (REGISTRAR_ROLE on the registry, canJoin on the domain).
// See this modal's preflight check below -- run BEFORE step 1, not discovered at step 4
// after three real wallet-signed transactions already succeeded.
const DOMAIN_REGISTRY_ABI = ['function canJoin(bytes32 id, address caller) view returns (bool)'] as const;
const AGENT_REGISTRY_ROLE_ABI = ['function hasRole(bytes32 role, address account) view returns (bool)'] as const;
const REGISTRAR_ROLE = ethers.id('REGISTRAR_ROLE');

type StepState = 'idle' | 'busy' | 'done';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (did: string) => void;
}

export function RegisterAgentModal({ onClose, onSuccess }: Props) {
  const { addToast, walletAddress, connectWallet } = useDashboard();

  const [alias, setAlias] = React.useState('');
  const [vertical, setVertical] = React.useState<0 | 1>(0);
  const [profileURI, setProfileURI] = React.useState('');
  const [did] = React.useState(() => `did:integrity:${ethers.id(`agent-${Date.now()}`).slice(2, 34)}`);

  const [sovereignAgent, setSovereignAgent] = React.useState<string | null>(null);
  const [stateAnchor, setStateAnchor] = React.useState<string | null>(null);
  const [anchorGranted, setAnchorGranted] = React.useState(false);
  const [primitives, setPrimitives] = React.useState<Record<string, string> | null>(null);
  const [oracleDone, setOracleDone] = React.useState(false);
  const [lastTx, setLastTx] = React.useState<string | null>(null);

  const [busyStep, setBusyStep] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Preflight: the two on-chain preconditions AgentPrimitivesFactory.registerPrimitives
  // depends on, checked read-only (no wallet signature) before step 1 is enabled --
  // a registration that would fail at step 4 (DomainJoinNotApproved / missing
  // REGISTRAR_ROLE) previously only surfaced that after 3 real wallet-signed
  // transactions already succeeded. See integrity-sdk's registration.py
  // preflight_register_agent() for the same checks on the SDK/CLI side.
  const [preflight, setPreflight] = React.useState<'checking' | 'ok' | { error: string } | null>(null);
  const domainId = vertical === 1 ? DOMAINS['healthcare.integrity'] : DOMAINS['general.integrity'];

  React.useEffect(() => {
    if (!walletAddress) {
      setPreflight(null);
      return;
    }
    let cancelled = false;
    setPreflight('checking');
    (async () => {
      try {
        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const registry = new ethers.Contract(XIBALBA_AGENT_REGISTRY_ADDRESS, AGENT_REGISTRY_ROLE_ABI, provider);
        const hasRole: boolean = await registry.hasRole(REGISTRAR_ROLE, AGENT_PRIMITIVES_FACTORY_ADDRESS);
        if (!hasRole) {
          if (!cancelled) setPreflight({
            error: 'AgentPrimitivesFactory does not hold REGISTRAR_ROLE on XibalbaAgentRegistry -- ' +
              'registration would revert at the final step. This is a protocol-level configuration ' +
              'issue, not something fixable here.',
          });
          return;
        }
        if (!domainId) {
          if (!cancelled) setPreflight({ error: `No domain configured for this vertical.` });
          return;
        }
        const domainRegistry = new ethers.Contract(DOMAIN_REGISTRY_ADDRESS, DOMAIN_REGISTRY_ABI, provider);
        const canJoin: boolean = await domainRegistry.canJoin(domainId, walletAddress);
        if (!cancelled) setPreflight(
          canJoin ? 'ok' : { error: `Your wallet cannot join the ${vertical === 1 ? "healthcare.integrity" : "general.integrity"} domain right now -- registration would revert at the final step (DomainJoinNotApproved).` }
        );
      } catch (err: any) {
        if (!cancelled) setPreflight({ error: `Could not verify registration preconditions: ${err?.message || err}` });
      }
    })();
    return () => { cancelled = true; };
  }, [walletAddress, vertical, domainId]);

  const stepState = (n: number): StepState => {
    if (busyStep === n) return 'busy';
    if (n === 1 && sovereignAgent) return 'done';
    if (n === 2 && stateAnchor) return 'done';
    if (n === 3 && anchorGranted) return 'done';
    if (n === 4 && primitives) return 'done';
    if (n === 5 && oracleDone) return 'done';
    return 'idle';
  };

  const getSigner = async () => {
    const eth = (window as any).ethereum;
    if (!eth) throw new Error('No Web3 wallet detected.');
    const provider = new ethers.BrowserProvider(eth);
    return provider.getSigner();
  };

  const run = async (step: number, fn: () => Promise<void>) => {
    setBusyStep(step);
    setError(null);
    try {
      await fn();
    } catch (err: any) {
      setError(err?.shortMessage || err?.message || 'Transaction failed.');
      addToast('error', `Step ${step} failed: ${err?.shortMessage || err?.message || 'error'}`);
    } finally {
      setBusyStep(null);
    }
  };

  const deploySovereignAgent = () => run(1, async () => {
    const signer = await getSigner();
    addToast('info', 'Deploying SovereignAgent…');
    const factory = new ethers.ContractFactory(SOVEREIGN_AGENT_ABI, SOVEREIGN_AGENT_BYTECODE, signer);
    // constructor(did, controller, oracle, factory)
    const contract = await factory.deploy(did, walletAddress, ORACLE_SIGNER_ADDRESS, AGENT_PRIMITIVES_FACTORY_ADDRESS);
    await contract.waitForDeployment();
    const addr = await contract.getAddress();
    setSovereignAgent(addr);
    setLastTx(contract.deploymentTransaction()?.hash || null);
    addToast('success', `SovereignAgent deployed at ${addr.slice(0, 10)}…`);
  });

  const deployStateAnchor = () => run(2, async () => {
    if (!sovereignAgent) throw new Error('Deploy the SovereignAgent first.');
    const signer = await getSigner();
    addToast('info', 'Deploying StateAnchor…');
    const factory = new ethers.ContractFactory(STATE_ANCHOR_ABI, STATE_ANCHOR_BYTECODE, signer);
    const contract = await factory.deploy(sovereignAgent); // admin = SovereignAgent
    await contract.waitForDeployment();
    const addr = await contract.getAddress();
    setStateAnchor(addr);
    setLastTx(contract.deploymentTransaction()?.hash || null);
    addToast('success', `StateAnchor deployed at ${addr.slice(0, 10)}…`);
  });

  const grantAnchorRole = () => run(3, async () => {
    if (!sovereignAgent || !stateAnchor) throw new Error('Deploy both contracts first.');
    const signer = await getSigner();
    // Read the REAL ANCHOR_ROLE from the deployed clone (never a constant).
    const anchor = new ethers.Contract(stateAnchor, STATE_ANCHOR_ABI, signer);
    const anchorRole: string = await anchor.ANCHOR_ROLE();
    const grantData = anchor.interface.encodeFunctionData('grantRole', [anchorRole, ORACLE_SIGNER_ADDRESS]);
    // The SovereignAgent (StateAnchor's admin) must be the caller, so route through execute.
    const sa = new ethers.Contract(sovereignAgent, SOVEREIGN_AGENT_ABI, signer);
    addToast('info', 'Granting ANCHOR_ROLE to the oracle signer…');
    const tx = await sa.execute(stateAnchor, 0n, grantData);
    await tx.wait();
    setAnchorGranted(true);
    setLastTx(tx.hash);
    addToast('success', 'ANCHOR_ROLE granted.');
  });

  const registerPrimitives = () => run(4, async () => {
    if (!sovereignAgent || !stateAnchor) throw new Error('Prerequisites missing.');
    const signer = await getSigner();
    const factory = new ethers.Contract(AGENT_PRIMITIVES_FACTORY_ADDRESS, FACTORY_ABI, signer);
    const domainId = vertical === 1 ? DOMAINS['healthcare.integrity'] : DOMAINS['general.integrity'];
    addToast('info', 'Cloning + registering the 7-primitive set…');
    const tx = await factory.registerPrimitives(sovereignAgent, stateAnchor, did, domainId, vertical, profileURI.trim() || 'ipfs://placeholder');
    const receipt = await tx.wait();
    // Parse the real clone addresses out of the PrimitivesRegistered event.
    let parsed: Record<string, string> | null = null;
    for (const log of receipt.logs) {
      try {
        const ev = factory.interface.parseLog(log);
        if (ev?.name === 'PrimitivesRegistered') {
          parsed = {
            sovereign_agent: sovereignAgent,
            state_anchor: stateAnchor,
            reputation_registry: ev.args.reputationRegistry,
            slasher: ev.args.slasher,
            verifier_registry: ev.args.verifierRegistry,
            compliance_gate: ev.args.complianceGate,
            agent_profile: ev.args.agentProfile,
          };
          break;
        }
      } catch { /* not our event */ }
    }
    if (!parsed) throw new Error('registerPrimitives succeeded but PrimitivesRegistered was not found in the receipt.');
    setPrimitives(parsed);
    setLastTx(tx.hash);
    addToast('success', 'All 7 primitives registered on-chain.');
  });

  const registerWithOracle = () => run(5, async () => {
    if (!primitives) throw new Error('Register the primitives on-chain first.');
    addToast('info', 'Recording the agent in the oracle…');
    // The oracle re-verifies these 7 addresses against XibalbaAgentRegistry before accepting.
    await oracle.register({
      did,
      did_document: { id: did, controller: walletAddress },
      primitives: primitives as any,
      eth_address_hex: walletAddress || undefined,
    });
    setOracleDone(true);
    addToast('success', 'Agent registered. Welcome to the network.');
    onSuccess(did);
  });

  const STEPS = [
    { n: 1, label: 'Deploy SovereignAgent', action: deploySovereignAgent, ready: preflight === 'ok' },
    { n: 2, label: 'Deploy StateAnchor', action: deployStateAnchor, ready: !!sovereignAgent },
    { n: 3, label: 'Grant ANCHOR_ROLE to oracle', action: grantAnchorRole, ready: !!stateAnchor },
    { n: 4, label: 'Register 7 primitives (factory)', action: registerPrimitives, ready: anchorGranted },
    { n: 5, label: 'Record in oracle', action: registerWithOracle, ready: !!primitives },
  ];

  return (
    <div role="dialog" aria-modal="true" aria-label="Register agent on-chain" onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 'var(--space-4)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-6)', width: 'min(560px, 96vw)', maxHeight: '92vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>Register agent on-chain</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex' }}>
            <X size={18} />
          </button>
        </div>

        <div className="text-muted" style={{ fontSize: '0.8rem' }}>
          Deploys this agent's own contracts and registers its full 7-primitive set on Base Sepolia — four wallet-signed transactions. DID: <code style={{ color: 'var(--theme-accent)' }}>{did}</code>
        </div>

        {!walletAddress ? (
          <button className="btn btn-primary" onClick={connectWallet}>Connect a Base Sepolia wallet</button>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
              <div className="form-group" style={{ flex: 1, minWidth: 180 }}>
                <label className="form-label" htmlFor="ra-alias">Alias (display only)</label>
                <input id="ra-alias" className="input" value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="Sentinel-01" />
              </div>
              <div className="form-group" style={{ minWidth: 160 }}>
                <label className="form-label" htmlFor="ra-vertical">Vertical</label>
                <select id="ra-vertical" className="input" value={vertical} onChange={(e) => setVertical(Number(e.target.value) as 0 | 1)}>
                  <option value={0}>General</option>
                  <option value={1}>Healthcare (Shield)</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="ra-uri">Profile URI (optional)</label>
              <input id="ra-uri" className="input" value={profileURI} onChange={(e) => setProfileURI(e.target.value)} placeholder="ipfs://…" />
            </div>

            {preflight === 'checking' && (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Loader2 size={13} className="animate-spin" /> Verifying registration preconditions…
              </div>
            )}
            {preflight && typeof preflight === 'object' && (
              <div role="alert" style={{ fontSize: '0.75rem', color: 'var(--danger)', background: 'var(--danger-dim)', padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
                {preflight.error}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {STEPS.map((s) => {
                const st = stepState(s.n);
                return (
                  <div key={s.n} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--glass-border)' }}>
                    <span style={{ width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none', background: st === 'done' ? 'var(--success)' : 'rgba(255,255,255,0.08)', color: st === 'done' ? '#001b0e' : 'var(--text-muted)', fontSize: '0.7rem', fontWeight: 700 }}>
                      {st === 'busy' ? <Loader2 size={13} className="animate-spin" /> : st === 'done' ? <Check size={13} /> : s.n}
                    </span>
                    <span style={{ flex: 1, fontSize: '0.85rem', fontWeight: 600 }}>{s.label}</span>
                    <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                      disabled={busyStep !== null || st === 'done' || !s.ready}
                      onClick={s.action}>
                      {st === 'done' ? 'Done' : st === 'busy' ? 'Working…' : 'Run'}
                    </button>
                  </div>
                );
              })}
            </div>

            {error && (
              <div role="alert" style={{ fontSize: '0.75rem', color: 'var(--danger)', background: 'var(--danger-dim)', padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
                {error}
              </div>
            )}

            {lastTx && (
              <a href={`${EXPLORER_URL}/tx/${lastTx}`} target="_blank" rel="noreferrer" style={{ fontSize: '0.72rem', color: 'var(--theme-accent)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                Latest tx <ExternalLink size={12} />
              </a>
            )}

            {oracleDone && (
              <button className="btn btn-success" onClick={() => onSuccess(did)}>Finish</button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
