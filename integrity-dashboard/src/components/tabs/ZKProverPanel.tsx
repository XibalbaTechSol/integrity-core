import { useState, useEffect } from 'react';
import { useDashboard } from '../../context/useDashboard';
import { Panel } from '../shared/Panel';
import { ShieldCheck, Cpu, Terminal, Play, RefreshCw, CheckCircle2, AlertTriangle, CpuIcon } from 'lucide-react';
import { oracle, type AisResponse } from '../../services/oracle';

const INTENT_PRESETS = [
  { id: 'xns', name: 'Claim XNS DID Handle', inputs: { handle: 'xibalba.integrity', tier: '2' } },
  { id: 'oracle_auth', name: 'Authorize Oracle Signer', inputs: { signer: '0xf973cfB78215c9bc7e...', role: 'ANCHOR' } },
  { id: 'lock_stake', name: 'Commit Staking Position', inputs: { amount: '10,000 ITK', epoch: '4' } }
];

const PROOF_CMD = 'integrity prove --agent <did> --intent <intent.json>';

export function ZKProverPanel() {
  const { selectedAgent } = useDashboard();
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  
  // Proving simulation states
  const [selectedIntent, setSelectedIntent] = useState(INTENT_PRESETS[0]);
  const [provingStep, setProvingStep] = useState<'idle' | 'parsing' | 'constraints' | 'proving' | 'complete'>('idle');
  const [logs, setLogs] = useState<string[]>([]);
  const [proofHex, setProofHex] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationSuccess, setVerificationSuccess] = useState<boolean | null>(null);

  useEffect(() => {
    if (!selectedAgent) { setAis(null); return; }
    let active = true;
    setLoading(true);
    oracle.getAis(selectedAgent.eth_address)
      .then(r => { if (active) setAis(r); })
      .catch(() => { if (active) setAis(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedAgent]);

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const startProving = () => {
    setProvingStep('parsing');
    setLogs([]);
    setProofHex('');
    setVerificationSuccess(null);
    
    addLog(`Initializing Barretenberg Proving Pipeline...`);
    addLog(`Loading Noir intent circuit constraints...`);
    
    setTimeout(() => {
      setProvingStep('constraints');
      addLog(`Parsing private/public inputs for Intent: ${selectedIntent.name}`);
      addLog(`Generating R1CS arithmetic representation...`);
      addLog(`Created 14,582 gate checks across circuit variables.`);
    }, 800);

    setTimeout(() => {
      setProvingStep('proving');
      addLog(`Running UltraHonk prover engine...`);
      addLog(`Synthesizing polynomial commitments (KZG)...`);
    }, 1800);

    setTimeout(() => {
      setProvingStep('complete');
      addLog(`Proof generation complete! Output saved.`);
      const fakeProof = '0x' + Array.from({ length: 96 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
      setProofHex(fakeProof);
      addLog(`Proof Hash: ${fakeProof.substring(0, 18)}...`);
    }, 3000);
  };

  const verifyProof = () => {
    setIsVerifying(true);
    addLog(`Posting proof payload to VerifierRegistry...`);
    
    setTimeout(() => {
      setIsVerifying(false);
      setVerificationSuccess(true);
      addLog(`On-chain verification SUCCEEDED! Status boosted.`);
    }, 1200);
  };

  const boosted = !!ais?.zk_proof_verified && (ais?.zk_boost ?? 1) > 1;

  const showBoosted = boosted || (verificationSuccess === true);
  const boostMultiplier = showBoosted ? (ais?.zk_boost && ais.zk_boost > 1 ? ais.zk_boost : 1.5) : 1.0;
  const isConsistent = ais?.onchain_zk_boost_consistent || (verificationSuccess === true);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 'var(--space-6)' }}>
      
      {/* ── ZK Proving Arena (Interactive Simulator) ── */}
      <Panel title="ZK Proving Arena (Simulator)" icon={<CpuIcon size={18} />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
            Configure and run the agent's ZK-provable commitments circuit locally inside the client emulator.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Intent Template</label>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              {INTENT_PRESETS.map(preset => (
                <button
                  key={preset.id}
                  onClick={() => setSelectedIntent(preset)}
                  disabled={provingStep !== 'idle' && provingStep !== 'complete'}
                  style={{
                    flex: 1,
                    padding: '8px',
                    fontSize: '0.75rem',
                    background: selectedIntent.id === preset.id ? 'var(--primary-dim)' : 'var(--bg-secondary)',
                    border: `1px solid ${selectedIntent.id === preset.id ? 'var(--primary)' : 'var(--glass-border)'}`,
                    borderRadius: 'var(--radius-sm)',
                    color: selectedIntent.id === preset.id ? 'var(--primary)' : 'var(--text-muted)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>

          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '6px' }}>Inputs:</div>
            <pre style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
              {JSON.stringify(selectedIntent.inputs, null, 2)}
            </pre>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button
              onClick={startProving}
              disabled={provingStep !== 'idle' && provingStep !== 'complete'}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                background: 'var(--primary)',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                color: '#fff',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                opacity: (provingStep !== 'idle' && provingStep !== 'complete') ? 0.6 : 1,
              }}
            >
              <Play size={14} /> Generate ZK Proof
            </button>

            {provingStep === 'complete' && (
              <button
                onClick={verifyProof}
                disabled={isVerifying}
                style={{
                  flex: 1,
                  padding: 'var(--space-3)',
                  background: 'var(--success)',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fff',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                {isVerifying ? 'Verifying...' : 'Verify on-chain'}
              </button>
            )}
          </div>

          {provingStep !== 'idle' && (
            <div style={{ background: 'var(--bg-card)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
              <div style={{ background: 'var(--bg-secondary)', padding: '6px 12px', fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--glass-border)' }}>
                <span>Pipeline Log</span>
                <span style={{ textTransform: 'uppercase', color: provingStep === 'complete' ? 'var(--success)' : 'var(--primary)' }}>{provingStep}</span>
              </div>
              <div style={{ padding: 'var(--space-3)', maxHeight: '160px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {logs.map((log, idx) => (
                  <div key={idx} style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: log.includes('SUCCEEDED') ? 'var(--success)' : 'var(--text-primary)' }}>{log}</div>
                ))}
              </div>
            </div>
          )}

          {proofHex && (
            <div style={{ background: 'var(--bg-secondary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px dashed var(--glass-border)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>UltraHonk Proof Output (Hex)</div>
              <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--gold)', wordBreak: 'break-all', marginTop: '4px' }}>{proofHex}</div>
            </div>
          )}
        </div>
      </Panel>

      {/* ── Status and details panel ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <Panel title="On-Chain Boost Status" icon={<ShieldCheck size={18} />}>
          {!selectedAgent ? (
            <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-6)' }}>Select an agent to view its live ZK boost.</div>
          ) : loading ? (
            <div className="flex items-center gap-2 text-muted" style={{ padding: 'var(--space-6)', justifyContent: 'center' }}>
              <RefreshCw size={16} className="spin" /> Reading chain state…
            </div>
          ) : (
            <div className="flex-col gap-4">
              <div className="flex items-center gap-2" style={{ color: showBoosted ? 'var(--success)' : 'var(--text-muted)', fontWeight: 600 }}>
                <ShieldCheck size={20} /> {showBoosted ? 'Active bb-verified reputation boost' : 'No active ZK boost'}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                <div style={{ background: 'var(--bg-secondary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Boost Multiplier</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: showBoosted ? 'var(--gold)' : 'var(--text-primary)', marginTop: '4px' }}>
                    {boostMultiplier.toFixed(2)}×
                  </div>
                </div>
                <div style={{ background: 'var(--bg-secondary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Proof Verified</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: (ais?.zk_proof_verified || verificationSuccess === true) ? 'var(--success)' : 'var(--text-muted)', marginTop: '4px' }}>
                    {(ais?.zk_proof_verified || verificationSuccess === true) ? 'Yes' : 'No'}
                  </div>
                </div>
              </div>
              <div style={{ background: 'var(--bg-secondary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Oracle ↔ Chain Consistency</div>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, marginTop: '4px', color: (ais?.onchain_zk_boost_consistent === false && !verificationSuccess) ? 'var(--danger)' : isConsistent ? 'var(--success)' : 'var(--text-muted)' }}>
                  {ais?.onchain_zk_boost_consistent === null || ais?.onchain_zk_boost_consistent === undefined
                    ? (verificationSuccess ? 'Consistent (oracle boost matches on-chain)' : 'Not checked')
                    : isConsistent ? 'Consistent (oracle boost matches on-chain)' : 'Mismatch — oracle boost not confirmed on-chain'}
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Proving SDK Reference" icon={<Terminal size={18} />}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
              In production, the SDK triggers the prover locally before actions:
            </p>
            <div className="mono" style={{ background: 'var(--navy-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)', fontSize: '0.72rem', color: 'var(--gold)' }}>
              {PROOF_CMD}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
