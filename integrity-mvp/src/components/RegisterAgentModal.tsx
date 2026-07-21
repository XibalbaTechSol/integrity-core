import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Rocket, Lock, Fingerprint, Code, CheckCircle, Loader2, AlertCircle, Play, ChevronRight, ChevronLeft } from 'lucide-react';
import { useAccount, useWalletClient, usePublicClient } from 'wagmi';
import { useToast } from '../contexts/ToastContext';
import { abis } from '../chain/abis';
import { singleton, deployments } from '../chain/deployments';
import { SOVEREIGN_AGENT_ABI, SOVEREIGN_AGENT_BYTECODE, STATE_ANCHOR_ABI, STATE_ANCHOR_BYTECODE } from '../chain/bytecode';
import { encodeFunctionData } from 'viem';
import { ORACLE_URL } from '../config';

interface RegisterAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  initialAlias?: string;
  initialVertical?: number;
}

export function RegisterAgentModal({ isOpen, onClose, onSuccess, initialAlias = '', initialVertical = 0 }: RegisterAgentModalProps) {
  const { addToast } = useToast();
  const { address: connectedAddress, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();

  const [step, setStep] = useState(1);
  const [isBusy, setIsBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form inputs
  const [alias, setAlias] = useState('');
  const [did, setDid] = useState('');
  const [vertical, setVertical] = useState<number>(0); // 0 = None, 1 = Healthcare
  const [profileURI, setProfileURI] = useState('');

  useEffect(() => {
    if (isOpen) {
      if (initialAlias.trim()) {
        const cleanAlias = initialAlias.trim();
        setAlias(cleanAlias);
        const slug = cleanAlias.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
        const randomSuffix = Math.floor(Math.random() * 1000);
        setDid(`did:integrity:${slug}-${randomSuffix}`);
        setProfileURI(`ipfs://${slug}-profile-${randomSuffix}`);
      } else {
        const randomSuffix = Math.floor(Math.random() * 1000);
        setAlias(`Clinical Auditor v${randomSuffix}`);
        setDid(`did:integrity:auditor-${randomSuffix}`);
        setProfileURI(`ipfs://auditor-profile-${randomSuffix}`);
      }
      setVertical(initialVertical);
      setStep(1);
      setErrorMsg(null);
      setSovereignAgentAddress(null);
      setStateAnchorAddress(null);
      setGrantTxHash(null);
      setRegisterTxHash(null);
      setOracleRegistered(false);
    }
  }, [isOpen, initialAlias, initialVertical]);

  // Deployed addresses and hashes
  const [sovereignAgentAddress, setSovereignAgentAddress] = useState<string | null>(null);
  const [stateAnchorAddress, setStateAnchorAddress] = useState<string | null>(null);
  const [grantTxHash, setGrantTxHash] = useState<string | null>(null);
  const [registerTxHash, setRegisterTxHash] = useState<string | null>(null);
  const [oracleRegistered, setOracleRegistered] = useState(false);

  // Address singletons & configs
  const factoryAddress = singleton('AgentPrimitivesFactory') as `0x${string}`;
  const oracleSignerAddress = deployments.protocolAddresses.oracleSigner as `0x${string}`;
  const domainId = deployments.domains[vertical === 1 ? 'healthcare.integrity' : 'general.integrity'];

  const nextStep = () => setStep(s => s + 1);
  const prevStep = () => setStep(s => s - 1);

  const handleDeploySovereignAgent = async () => {
    if (!isConnected || !connectedAddress || !walletClient || !publicClient) {
      addToast('error', 'Connect a wallet first.');
      return;
    }
    if (!did.trim()) {
      addToast('error', 'Enter a valid DID string');
      return;
    }

    setIsBusy(true);
    setErrorMsg(null);
    addToast('info', 'Deploying SovereignAgent contract...');

    try {
      const hash = await walletClient.deployContract({
        abi: SOVEREIGN_AGENT_ABI,
        bytecode: `0x${SOVEREIGN_AGENT_BYTECODE.replace(/^0x/, '')}`,
        args: [did.trim(), connectedAddress, oracleSignerAddress, factoryAddress],
        account: connectedAddress,
      });

      const receipt = await publicClient.waitForTransactionReceipt({ hash });
      if (!receipt.contractAddress) {
        throw new Error('SovereignAgent deployment transaction succeeded, but did not return a contract address.');
      }

      setSovereignAgentAddress(receipt.contractAddress);
      addToast('success', `SovereignAgent deployed at ${receipt.contractAddress}`);
      nextStep();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'SovereignAgent deployment failed.');
      addToast('error', 'SovereignAgent deployment failed.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleDeployStateAnchor = async () => {
    if (!isConnected || !connectedAddress || !walletClient || !publicClient || !sovereignAgentAddress) {
      addToast('error', 'Prerequisites missing.');
      return;
    }

    setIsBusy(true);
    setErrorMsg(null);
    addToast('info', 'Deploying StateAnchor contract...');

    try {
      const hash = await walletClient.deployContract({
        abi: STATE_ANCHOR_ABI,
        bytecode: `0x${STATE_ANCHOR_BYTECODE.replace(/^0x/, '')}`,
        args: [sovereignAgentAddress as `0x${string}`],
        account: connectedAddress,
      });

      const receipt = await publicClient.waitForTransactionReceipt({ hash });
      if (!receipt.contractAddress) {
        throw new Error('StateAnchor deployment transaction succeeded, but did not return a contract address.');
      }

      setStateAnchorAddress(receipt.contractAddress);
      addToast('success', `StateAnchor deployed at ${receipt.contractAddress}`);
      nextStep();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'StateAnchor deployment failed.');
      addToast('error', 'StateAnchor deployment failed.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleGrantAnchorRole = async () => {
    if (!isConnected || !connectedAddress || !walletClient || !publicClient || !sovereignAgentAddress || !stateAnchorAddress) {
      addToast('error', 'Prerequisites missing.');
      return;
    }

    setIsBusy(true);
    setErrorMsg(null);
    addToast('info', 'Granting ANCHOR_ROLE to oracle signer...');

    try {
      const anchorRoleBytes = '0x8bdfd7e189cc59c3a30e8dbdbdfdbdfd5bdfdbd1d73981881881881881881881' as const;
      const grantCalldata = encodeFunctionData({
        abi: [
          {
            name: 'grantRole',
            type: 'function',
            stateMutability: 'nonpayable',
            inputs: [
              { name: 'role', type: 'bytes32' },
              { name: 'account', type: 'address' }
            ],
            outputs: []
          }
        ],
        functionName: 'grantRole',
        args: [anchorRoleBytes, oracleSignerAddress]
      });

      // SovereignAgent.execute(stateAnchor, 0, grantCalldata)
      const hash = await walletClient.writeContract({
        address: sovereignAgentAddress as `0x${string}`,
        abi: abis.SovereignAgent,
        functionName: 'execute',
        args: [stateAnchorAddress, 0n, grantCalldata],
        account: connectedAddress
      });

      await publicClient.waitForTransactionReceipt({ hash });
      setGrantTxHash(hash);
      addToast('success', 'ANCHOR_ROLE successfully granted to Oracle Signer!');
      nextStep();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'Role grant transaction failed.');
      addToast('error', 'Failed to grant ANCHOR_ROLE.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleRegisterPrimitivesOnChain = async () => {
    if (!isConnected || !connectedAddress || !walletClient || !publicClient || !sovereignAgentAddress || !stateAnchorAddress) {
      addToast('error', 'Prerequisites missing.');
      return;
    }

    setIsBusy(true);
    setErrorMsg(null);
    addToast('info', 'Executing registerPrimitives on-chain factory...');

    try {
      const hash = await walletClient.writeContract({
        address: factoryAddress,
        abi: abis.AgentPrimitivesFactory,
        functionName: 'registerPrimitives',
        args: [
          sovereignAgentAddress,
          stateAnchorAddress,
          did.trim(),
          domainId,
          vertical,
          profileURI.trim() || 'ipfs://placeholder'
        ],
        account: connectedAddress
      });

      await publicClient.waitForTransactionReceipt({ hash });
      setRegisterTxHash(hash);
      addToast('success', 'Cloned & registered all 7 agent primitives!');
      nextStep();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'Primitives registration failed.');
      addToast('error', 'Primitives registration failed.');
    } finally {
      setIsBusy(false);
    }
  };

  const handleRegisterWithOracle = async () => {
    if (!sovereignAgentAddress || !stateAnchorAddress) {
      addToast('error', 'Contract deployment references missing.');
      return;
    }
    if (!publicClient) {
      addToast('error', 'Blockchain provider not ready.');
      return;
    }

    setIsBusy(true);
    setErrorMsg(null);
    addToast('info', 'Registering agent primitives with the Oracle database...');

    try {
      // Look up generated primitives from on-chain via Registry resolveAgent read to be 100% accurate,
      // or calculate them since factory registers them. Let's read them from the registry to be fully safe!
      const registryRecord = await publicClient.readContract({
        address: singleton('XibalbaAgentRegistry'),
        abi: abis.XibalbaAgentRegistry,
        functionName: 'resolveAgent',
        args: [sovereignAgentAddress as `0x${string}`]
      });

      const primitives = (registryRecord as any).primitives;

      // Submit POST /v1/agent/register to oracle backend
      const res = await fetch(`${ORACLE_URL}/v1/agent/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          did: did.trim(),
          did_document: {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": did.trim(),
            "verificationMethod": [{
              "id": `${did.trim()}#key-1`,
              "type": "Ed25519VerificationKey2020",
              "controller": did.trim(),
              "publicKeyMultibase": `z${connectedAddress}` // Multibase format placeholder
            }]
          },
          primitives: {
            sovereign_agent: sovereignAgentAddress,
            state_anchor: stateAnchorAddress,
            reputation_registry: primitives.reputationRegistry,
            slasher: primitives.slasher,
            verifier_registry: primitives.verifierRegistry,
            compliance_gate: primitives.complianceGate,
            agent_profile: primitives.agentProfile
          },
          eth_address_hex: connectedAddress,
          verification_tier: 1
        })
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Oracle registration failed: ${res.status} ${text}`);
      }

      setOracleRegistered(true);
      addToast('success', 'Agent successfully index-registered with the Oracle!');
      nextStep();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'Oracle registration failed.');
      addToast('error', 'Oracle indexing failed.');
    } finally {
      setIsBusy(false);
    }
  };

  const autofillDemo = () => {
    const randomSuffix = Math.floor(Math.random() * 1000);
    setAlias(`Clinical Auditor v${randomSuffix}`);
    setDid(`did:integrity:auditor-${randomSuffix}`);
    setProfileURI(`ipfs://auditor-profile-${randomSuffix}`);
  };

  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'var(--bg-main)', opacity: 0.85, backdropFilter: 'blur(8px)' }}
      />

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '650px',
          maxHeight: 'calc(100vh - 64px)',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
        }}
      >
        {/* Header */}
        <div style={{ padding: 'var(--space-6)', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--navy-light)' }}>
          <div className="flex items-center gap-3">
            <Rocket size={20} color="var(--primary)" />
            <div>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>Register New Agent</h3>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Step {step} of 6: {getStepTitle(step)}</span>
            </div>
          </div>
          <button onClick={onClose} className="btn btn-icon" aria-label="Close modal"><X size={20} /></button>
        </div>

        {/* Progress bar */}
        <div style={{ height: '3px', background: 'rgba(255,255,255,0.05)', width: '100%' }}>
          <div style={{ height: '100%', background: 'var(--primary)', width: `${(step / 6) * 100}%`, transition: 'width 0.3s ease' }}></div>
        </div>

        <div style={{ padding: 'var(--space-8)', overflowY: 'auto', flex: 1 }}>
          {errorMsg && (
            <div style={{ padding: '12px', background: 'rgba(244,63,94,0.1)', color: '#f43f5e', border: '1px solid rgba(244,63,94,0.2)', borderRadius: '8px', fontSize: '0.8rem', display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '16px' }}>
              <AlertCircle size={16} />
              <div style={{ flex: 1, wordBreak: 'break-word' }}>{errorMsg}</div>
            </div>
          )}

          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>Configure core parameters for your autonomous agent identity.</p>
                  <button className="btn btn-sm btn-secondary" onClick={autofillDemo}>Autofill Demo</button>
                </div>
                <div className="flex-col gap-4">
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>Agent Name / Alias</label>
                    <input type="text" className="input" placeholder="e.g. AuditBot-01" value={alias} onChange={e => setAlias(e.target.value)} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>DID Identifier (did:integrity:...)</label>
                    <input type="text" className="input" placeholder="did:integrity:..." value={did} onChange={e => setDid(e.target.value)} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>Target Domain</label>
                      <select className="input" style={{ width: '100%', height: '40px', background: 'var(--bg-main)' }} value={vertical} onChange={e => setVertical(Number(e.target.value))}>
                        <option value={0}>General Domain (general.integrity)</option>
                        <option value={1}>Healthcare Domain (healthcare.integrity)</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>Profile URI (Metadata)</label>
                      <input type="text" className="input" placeholder="ipfs://..." value={profileURI} onChange={e => setProfileURI(e.target.value)} />
                    </div>
                  </div>
                </div>

                <div style={{ borderTop: '1px solid var(--border)', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
                  <button className="btn btn-primary" onClick={nextStep} disabled={!alias || !did}>Continue <ChevronRight size={16} /></button>
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '0 0 8px' }}>Deploy SovereignAgent (Core Account)</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Deploy the agent's unique on-chain identity contract. The deploying wallet address will be set as the owner and controller of this agent.
                  </p>
                </div>

                {sovereignAgentAddress ? (
                  <div style={{ padding: '16px', background: 'rgba(16,185,129,0.05)', border: '1px solid var(--success)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>SovereignAgent Contract Address</div>
                    <code className="mono" style={{ fontSize: '0.85rem' }}>{sovereignAgentAddress}</code>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem', background: 'rgba(255,255,255,0.02)', padding: '12px', border: '1px dashed var(--border)', borderRadius: '8px' }}>
                    <Play size={16} /> Click deploy to request signature and submit contract.
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                  <button className="btn btn-ghost" onClick={prevStep} disabled={isBusy}><ChevronLeft size={16} /> Back</button>
                  {sovereignAgentAddress ? (
                    <button className="btn btn-primary" onClick={nextStep}>Next step <ChevronRight size={16} /></button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleDeploySovereignAgent} disabled={isBusy}>
                      {isBusy ? <><Loader2 className="spin" size={16} /> Deploying...</> : 'Deploy Contract'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div key="step3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '0 0 8px' }}>Deploy StateAnchor</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Deploy the tamper-evident state root anchor. This contract stores state updates signed by the agent or oracle and anchors them to the block.
                  </p>
                </div>

                {stateAnchorAddress ? (
                  <div style={{ padding: '16px', background: 'rgba(16,185,129,0.05)', border: '1px solid var(--success)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>StateAnchor Contract Address</div>
                    <code className="mono" style={{ fontSize: '0.85rem' }}>{stateAnchorAddress}</code>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem', background: 'rgba(255,255,255,0.02)', padding: '12px', border: '1px dashed var(--border)', borderRadius: '8px' }}>
                    <Play size={16} /> Awaiting deployment...
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                  <button className="btn btn-ghost" onClick={prevStep} disabled={isBusy}><ChevronLeft size={16} /> Back</button>
                  {stateAnchorAddress ? (
                    <button className="btn btn-primary" onClick={nextStep}>Next step <ChevronRight size={16} /></button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleDeployStateAnchor} disabled={isBusy}>
                      {isBusy ? <><Loader2 className="spin" size={16} /> Deploying...</> : 'Deploy StateAnchor'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}

            {step === 4 && (
              <motion.div key="step4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '0 0 8px' }}>Grant Oracle Anchor Role</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Authorizes the protocol oracle's validator key to submit anchor roots to this agent's `StateAnchor` contract.
                    Routes through `SovereignAgent.execute` to configure access controls on the StateAnchor.
                  </p>
                </div>

                {grantTxHash ? (
                  <div style={{ padding: '16px', background: 'rgba(16,185,129,0.05)', border: '1px solid var(--success)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Transaction Receipt</div>
                    <code className="mono" style={{ fontSize: '0.85rem' }}>{grantTxHash}</code>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem', background: 'rgba(255,255,255,0.02)', padding: '12px', border: '1px dashed var(--border)', borderRadius: '8px' }}>
                    <Lock size={16} /> Awaiting execution transaction...
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                  <button className="btn btn-ghost" onClick={prevStep} disabled={isBusy}><ChevronLeft size={16} /> Back</button>
                  {grantTxHash ? (
                    <button className="btn btn-primary" onClick={nextStep}>Next step <ChevronRight size={16} /></button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleGrantAnchorRole} disabled={isBusy}>
                      {isBusy ? <><Loader2 className="spin" size={16} /> Granting Role...</> : 'Authorize Oracle'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}

            {step === 5 && (
              <motion.div key="step5" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '0 0 8px' }}>Register Primitives Factory</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Executes `AgentPrimitivesFactory.registerPrimitives` to clone 5 proxy primitives (Slasher, ReputationRegistry, VerifierRegistry, ComplianceGate, AgentProfile) and register all 7 in `XibalbaAgentRegistry`.
                  </p>
                </div>

                {registerTxHash ? (
                  <div style={{ padding: '16px', background: 'rgba(16,185,129,0.05)', border: '1px solid var(--success)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success)', fontWeight: 800, textTransform: 'uppercase', marginBottom: '4px' }}>Registration Tx Hash</div>
                    <code className="mono" style={{ fontSize: '0.85rem' }}>{registerTxHash}</code>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem', background: 'rgba(255,255,255,0.02)', padding: '12px', border: '1px dashed var(--border)', borderRadius: '8px' }}>
                    <Fingerprint size={16} /> Awaiting registry commit...
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                  <button className="btn btn-ghost" onClick={prevStep} disabled={isBusy}><ChevronLeft size={16} /> Back</button>
                  {registerTxHash ? (
                    <button className="btn btn-primary" onClick={nextStep}>Next step <ChevronRight size={16} /></button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleRegisterPrimitivesOnChain} disabled={isBusy}>
                      {isBusy ? <><Loader2 className="spin" size={16} /> Registering...</> : 'Commit Registration'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}

            {step === 6 && (
              <motion.div key="step6" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="flex-col gap-6">
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '0 0 8px' }}>Oracle Synchronization</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Synchronizes your newly registered primitives with the off-chain Xibalba Identity Oracle to enable telemetry ingestion and score calculation.
                  </p>
                </div>

                {oracleRegistered ? (
                  <div style={{ textAlign: 'center', padding: 'var(--space-6) 0' }}>
                    <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'rgba(16,185,129,0.1)', color: 'var(--success)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', border: '1px solid var(--success)' }}>
                      <CheckCircle size={40} />
                    </div>
                    <h5 style={{ fontSize: '1.1rem', fontWeight: 700, margin: '0 0 4px' }}>Registration Successful!</h5>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>The agent has been indexed by the oracle.</p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem', background: 'rgba(255,255,255,0.02)', padding: '12px', border: '1px dashed var(--border)', borderRadius: '8px' }}>
                    <Code size={16} /> Awaiting index sync...
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                  <button className="btn btn-ghost" onClick={prevStep} disabled={isBusy || oracleRegistered}><ChevronLeft size={16} /> Back</button>
                  {oracleRegistered ? (
                    <button className="btn btn-primary" onClick={() => { onSuccess(); onClose(); }}>Done</button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleRegisterWithOracle} disabled={isBusy}>
                      {isBusy ? <><Loader2 className="spin" size={16} /> Registering...</> : 'Sync with Oracle'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}

function getStepTitle(step: number) {
  switch(step) {
    case 1: return "Identity Config";
    case 2: return "SovereignAgent Deploy";
    case 3: return "StateAnchor Deploy";
    case 4: return "Authorize Oracle";
    case 5: return "Register Primitives";
    case 6: return "Oracle Sync";
    default: return "";
  }
}
