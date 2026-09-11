import React from 'react';
import { ethers } from 'ethers';
import { X, Loader2, Check, ExternalLink } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';
import {
  AGENT_PRIMITIVES_FACTORY_ADDRESS,
  ITK_TOKEN_ADDRESS,
  ORACLE_SIGNER_ADDRESS,
  DOMAINS,
  DOMAIN_REGISTRY_ADDRESS,
  XIBALBA_AGENT_REGISTRY_ADDRESS,
  RPC_URL,
  EXPLORER_URL,
  BASE_SEPOLIA_CHAIN_ID,
} from '../../constants';
import {
  SOVEREIGN_AGENT_ABI, SOVEREIGN_AGENT_BYTECODE,
  STATE_ANCHOR_ABI, STATE_ANCHOR_BYTECODE,
} from '../../chain/bytecode';

// Real on-chain agent registration (Class C), the ethers port of integrity-dashboard's
// RegisterAgentModal. Runs the exact sequence integrity-sdk's registration.py does:
//   1. Deploy the agent's own SovereignAgent (account contract, DID baked in).
//   2. Deploy its own StateAnchor (admin = the SovereignAgent).
//   3. Fund the SovereignAgent with the enforced 100 ITK registration bond.
//   4. Grant the oracle anchor role, anchor the non-zero genesis memory root as the
//      agent, and approve the factory to pull the bond (all routed through execute).
//   5. AgentPrimitivesFactory.registerPrimitives clones the remaining 5 primitives and
//      atomically registers all 7 into XibalbaAgentRegistry.
//   6. Record the agent in the oracle DB (which independently re-verifies the 7
//      addresses against the registry on-chain before accepting).
// Progress is persisted after every confirmation so a browser or workstation restart
// resumes from the confirmed step rather than orphaning deployed contracts.

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
const GENESIS_VAULT_ROOT = ethers.id('integrity.trust-vault.genesis.v1');
const MIN_REGISTRATION_BOND = ethers.parseEther('100');
const ERC20_ABI = [
  'function balanceOf(address account) view returns (uint256)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)',
  'function approve(address spender, uint256 amount) returns (bool)',
] as const;

const PROGRESS_KEY = `integrity.registration.v2.${BASE_SEPOLIA_CHAIN_ID}`;

interface RegistrationProgress {
  controller: string;
  did: string;
  sovereignAgent: string | null;
  stateAnchor: string | null;
  funded: boolean;
  anchorGranted: boolean;
  genesisAnchored: boolean;
  bondApproved: boolean;
  primitives: Record<string, string> | null;
  oracleDone: boolean;
  lastTx: string | null;
}

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
  // Keep the generated DID as the safe default, but allow an operator to register
  // an existing identity (for example the Shield DID already bound to this device).
  // This must be chosen before the first wallet-signed step; changing an identity
  // after contracts are deployed would make the on-chain DID/contract binding
  // inconsistent.
  const [did, setDid] = React.useState(() => `did:integrity:${ethers.id(`agent-${Date.now()}`).slice(2, 34)}`);

  const [sovereignAgent, setSovereignAgent] = React.useState<string | null>(null);
  const [stateAnchor, setStateAnchor] = React.useState<string | null>(null);
  const [funded, setFunded] = React.useState(false);
  const [anchorGranted, setAnchorGranted] = React.useState(false);
  const [genesisAnchored, setGenesisAnchored] = React.useState(false);
  const [bondApproved, setBondApproved] = React.useState(false);
  const [primitives, setPrimitives] = React.useState<Record<string, string> | null>(null);
  const [oracleDone, setOracleDone] = React.useState(false);
  const [lastTx, setLastTx] = React.useState<string | null>(null);
  const [progressLoaded, setProgressLoaded] = React.useState(false);

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
    if (!walletAddress) return;
    try {
      const raw = localStorage.getItem(PROGRESS_KEY);
      const saved = raw ? JSON.parse(raw) as RegistrationProgress : null;
      if (saved?.controller.toLowerCase() === walletAddress.toLowerCase()) {
        setDid(saved.did);
        setSovereignAgent(saved.sovereignAgent);
        setStateAnchor(saved.stateAnchor);
        setFunded(saved.funded);
        setAnchorGranted(saved.anchorGranted);
        setGenesisAnchored(saved.genesisAnchored);
        setBondApproved(saved.bondApproved);
        setPrimitives(saved.primitives);
        setOracleDone(saved.oracleDone);
        setLastTx(saved.lastTx);
      }
    } catch {
      try { localStorage.removeItem(PROGRESS_KEY); } catch { /* storage may be disabled */ }
    } finally {
      setProgressLoaded(true);
    }
  }, [walletAddress]);

  React.useEffect(() => {
    if (!walletAddress || !progressLoaded) return;
    const progress: RegistrationProgress = {
      controller: walletAddress, did, sovereignAgent, stateAnchor, funded,
      anchorGranted, genesisAnchored, bondApproved, primitives, oracleDone, lastTx,
    };
    try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress)); } catch { /* storage may be disabled */ }
  }, [walletAddress, progressLoaded, did, sovereignAgent, stateAnchor, funded, anchorGranted, genesisAnchored, bondApproved, primitives, oracleDone, lastTx]);

  React.useEffect(() => {
    if (!walletAddress) {
      setPreflight(null);
      return;
    }
    let cancelled = false;
    setPreflight('checking');
    (async () => {
      try {
        const eth = (window as any).ethereum;
        const provider = eth ? new ethers.BrowserProvider(eth) : new ethers.JsonRpcProvider(RPC_URL);
        const registry = new ethers.Contract(XIBALBA_AGENT_REGISTRY_ADDRESS, AGENT_REGISTRY_ROLE_ABI, provider);
        const token = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, provider);
        const [hasRole, walletBondBalance, agentBondBalance]: [boolean, bigint, bigint] = await Promise.all([
          registry.hasRole(REGISTRAR_ROLE, AGENT_PRIMITIVES_FACTORY_ADDRESS),
          token.balanceOf(walletAddress),
          sovereignAgent ? token.balanceOf(sovereignAgent) : Promise.resolve(0n),
        ]);
        const bondBalance = walletBondBalance + agentBondBalance;
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
        if (bondBalance < MIN_REGISTRATION_BOND) {
          if (!cancelled) setPreflight({ error: `The connected wallet and partially deployed SovereignAgent need at least 100 ITK combined for the enforced registration bond; current balance is ${ethers.formatEther(bondBalance)} ITK. Fund it through the approved Base Sepolia faucet/operator path before spending registration gas.` });
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
  }, [walletAddress, vertical, domainId, sovereignAgent]);

  const stepState = (n: number): StepState => {
    if (busyStep === n) return 'busy';
    if (n === 1 && sovereignAgent) return 'done';
    if (n === 2 && stateAnchor) return 'done';
    if (n === 3 && funded) return 'done';
    if (n === 4 && anchorGranted) return 'done';
    if (n === 5 && genesisAnchored) return 'done';
    if (n === 6 && bondApproved) return 'done';
    if (n === 7 && primitives) return 'done';
    if (n === 8 && oracleDone) return 'done';
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
    if (!/^did:integrity:[A-Za-z0-9._:-]+$/.test(did)) {
      throw new Error('Enter a valid did:integrity identifier before deploying.');
    }
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

  const fundRegistrationBond = () => run(3, async () => {
    if (!sovereignAgent) throw new Error('Deploy the SovereignAgent first.');
    const signer = await getSigner();
    const token = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, signer);
    const balance: bigint = await token.balanceOf(sovereignAgent);
    if (balance < MIN_REGISTRATION_BOND) {
      const tx = await token.transfer(sovereignAgent, MIN_REGISTRATION_BOND - balance);
      await tx.wait();
      setLastTx(tx.hash);
    }
    setFunded(true);
    addToast('success', 'SovereignAgent holds the 100 ITK registration bond.');
  });

  const grantAnchorRole = () => run(4, async () => {
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

  const anchorGenesisRoot = () => run(5, async () => {
    if (!sovereignAgent || !stateAnchor) throw new Error('Deploy both contracts first.');
    const signer = await getSigner();
    const anchor = new ethers.Contract(stateAnchor, STATE_ANCHOR_ABI, signer);
    const currentRoot: string = await anchor.latestRoot();
    if (currentRoot === ethers.ZeroHash) {
      const data = anchor.interface.encodeFunctionData('anchorRoot', [GENESIS_VAULT_ROOT]);
      const sa = new ethers.Contract(sovereignAgent, SOVEREIGN_AGENT_ABI, signer);
      addToast('info', 'Anchoring the agent-authorized genesis memory root…');
      const tx = await sa.execute(stateAnchor, 0n, data);
      await tx.wait();
      setLastTx(tx.hash);
    }
    setGenesisAnchored(true);
    addToast('success', 'Genesis memory root anchored.');
  });

  const approveRegistrationBond = () => run(6, async () => {
    if (!sovereignAgent) throw new Error('Deploy and fund the SovereignAgent first.');
    const signer = await getSigner();
    const token = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI, signer);
    const allowance: bigint = await token.allowance(sovereignAgent, AGENT_PRIMITIVES_FACTORY_ADDRESS);
    if (allowance < MIN_REGISTRATION_BOND) {
      const data = token.interface.encodeFunctionData('approve', [AGENT_PRIMITIVES_FACTORY_ADDRESS, MIN_REGISTRATION_BOND]);
      const sa = new ethers.Contract(sovereignAgent, SOVEREIGN_AGENT_ABI, signer);
      addToast('info', 'Approving the registration bond through the SovereignAgent…');
      const tx = await sa.execute(ITK_TOKEN_ADDRESS, 0n, data);
      await tx.wait();
      setLastTx(tx.hash);
    }
    setBondApproved(true);
    addToast('success', 'Registration bond approved.');
  });

  const registerPrimitives = () => run(7, async () => {
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

  const registerWithOracle = () => run(8, async () => {
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
    setProgressLoaded(false);
    try { localStorage.removeItem(PROGRESS_KEY); } catch { /* storage may be disabled */ }
    addToast('success', 'Agent registered. Welcome to the network.');
    onSuccess(did);
  });

  const STEPS = [
    { n: 1, label: 'Deploy SovereignAgent', action: deploySovereignAgent, ready: preflight === 'ok' },
    { n: 2, label: 'Deploy StateAnchor', action: deployStateAnchor, ready: !!sovereignAgent },
    { n: 3, label: 'Fund 100 ITK registration bond', action: fundRegistrationBond, ready: !!sovereignAgent },
    { n: 4, label: 'Grant ANCHOR_ROLE to oracle', action: grantAnchorRole, ready: funded && !!stateAnchor },
    { n: 5, label: 'Anchor genesis memory root', action: anchorGenesisRoot, ready: anchorGranted },
    { n: 6, label: 'Approve factory bond', action: approveRegistrationBond, ready: genesisAnchored },
    { n: 7, label: 'Register 7 primitives (factory)', action: registerPrimitives, ready: bondApproved },
    { n: 8, label: 'Record in oracle', action: registerWithOracle, ready: !!primitives },
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
          Deploys this agent's own contracts, anchors its genesis memory, bonds 100 ITK, and registers its full 7-primitive set on Base Sepolia. Confirmed progress survives a browser or workstation restart. DID: <code style={{ color: 'var(--theme-accent)' }}>{did}</code>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ra-did">DID to register</label>
          <input
            id="ra-did"
            className="input"
            value={did}
            onChange={(e) => setDid(e.target.value.trim())}
            disabled={sovereignAgent !== null}
            pattern="did:integrity:.+"
            aria-describedby="ra-did-help"
          />
          <small id="ra-did-help" className="text-muted">
            Use the existing Shield DID here when registering the device-bound agent; leave the generated value for a new identity.
          </small>
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
