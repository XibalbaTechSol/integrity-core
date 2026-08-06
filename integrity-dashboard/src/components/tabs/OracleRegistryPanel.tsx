import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Globe, Database, RefreshCw, CheckCircle, Layers, ArrowRight, UserCheck, Shield, Key, Cpu } from 'lucide-react';
import { StatusBadge } from '../shared/StatusBadge';
import { useDashboard } from '../../context/useDashboard';
import { motion } from 'framer-motion';

const RollupStep = ({ title, desc, icon, active }: { title: string, desc: string, icon: React.ReactNode, active?: boolean }) => (
  <div className="flex-col items-center gap-2" style={{ flex: 1, opacity: active ? 1 : 0.4 }}>
     <div style={{ 
       width: '48px', height: '48px', borderRadius: 'var(--radius-sm)', 
       background: active ? 'var(--primary-dim)' : 'var(--bg-secondary)', 
       border: `1px solid ${active ? 'var(--primary)' : 'var(--glass-border)'}`,
       display: 'flex', alignItems: 'center', justifyContent: 'center', color: active ? 'var(--primary)' : 'var(--text-muted)'
     }}>
       {icon}
     </div>
     <div style={{ fontSize: '0.75rem', fontWeight: 600, textAlign: 'center' }}>{title}</div>
     <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0 4px' }}>{desc}</div>
  </div>
);

interface Source {
  id: number;
  name: string;
  uri: string;
  active: boolean;
  trustScore: number;
  isUserNode?: boolean;
}

export function OracleRegistryPanel() {
  const { addToast, selectedAgent } = useDashboard();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);

  // Registration Form State
  const [nodeName, setNodeName] = useState('');
  const [endpointUri, setEndpointUri] = useState('');
  const [stakeCollateral, setStakeCollateral] = useState('5000');
  const [isRegistering, setIsRegistering] = useState(false);
  const [regStep, setRegStep] = useState<number>(0);
  const [regLogs, setRegLogs] = useState<string[]>([]);

  const fetchSources = async () => {
    setLoading(true);
    try {
      const data: Source[] = [
        { id: 1, name: 'National Medical Library', uri: 'https://nml.gov/api', active: true, trustScore: 980 },
        { id: 2, name: 'Global Financial Index', uri: 'https://gfi.com/realtime', active: true, trustScore: 950 },
        { id: 3, name: 'Weather Pattern Oracle', uri: 'https://weather.intg/v1', active: false, trustScore: 400 },
        { id: 4, name: 'PubMed Central Verified', uri: 'https://pmc.nih.gov/v3', active: true, trustScore: 995 },
        { id: 5, name: 'Wikipedia', uri: 'https://en.wikipedia.org/w/api.php', active: true, trustScore: 990, isUserNode: true },
      ];
      
      // Keep any user registered nodes
      const userNodes = sources.filter(s => s.isUserNode);
      setSources([...data, ...userNodes]);
    } catch (err) {
      console.error('Failed to fetch sources:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      if (mounted) {
        await fetchSources();
      }
    };
    load();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRegisterNode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) {
      addToast('error', 'Please select an agent wallet to execute contract operations.');
      return;
    }
    if (!nodeName || !endpointUri) {
      addToast('error', 'All registration inputs must be filled.');
      return;
    }

    setIsRegistering(true);
    setRegStep(1);
    setRegLogs(['[TX-INIT] Instantiating registerOracleNode smart contract transaction...']);

    const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

    try {
      // Step 1: Lock ITK Staking Collateral
      await delay(1200);
      setRegStep(2);
      setRegLogs(prev => [
        ...prev,
        `[LOCK] Locking ${stakeCollateral} ITK staking collateral from owner: ${selectedAgent.eth_address}...`,
        `[LOCK] Staking contract approved. Escrow balance committed.`
      ]);

      // Step 2: Generate Cryptographic Consensus Keys
      await delay(1200);
      setRegStep(3);
      setRegLogs(prev => [
        ...prev,
        `[KEYGEN] Generating BLS threshold signature keys for oracle node...`,
        `[KEYGEN] Verification key generated: 0x9b54c8a2bde77d12a9...`
      ]);

      // Step 3: Broadcast Registration to Base L2
      await delay(1500);
      setRegStep(4);
      setRegLogs(prev => [
        ...prev,
        `[BROADCAST] Broadcasting registerOracleNode transaction to Base L2 Sepolia...`,
        `[BROADCAST] Transaction Hash: 0x768fa2bf97eb483d2dd5da060b8ccfeaea7096cc723e1f5517aff7e980...`,
        `[BROADCAST] Block Confirmation: #12,884,952. Gas Used: 184,200 gwei.`
      ]);

      // Step 4: Consensus Sync & Finalization
      await delay(1200);
      setRegStep(5);
      setRegLogs(prev => [
        ...prev,
        `[SYNC] Synchronizing node state across 3 core network validators...`,
        `[SUCCESS] Node active. Registration finalized by oracle network consensus.`
      ]);

      await delay(800);
      
      const newNode: Source = {
        id: sources.length + 1,
        name: nodeName,
        uri: endpointUri,
        active: true,
        trustScore: 900,
        isUserNode: true
      };

      setSources(prev => [...prev, newNode]);
      addToast('success', `Oracle node ${nodeName} registered successfully at 0x768f...`);
      
      // Reset form
      setNodeName('');
      setEndpointUri('');
    } catch (err: any) {
      setRegLogs(prev => [...prev, `[ERROR] Registration aborted: ${err.message}`]);
      addToast('error', `Failed to register oracle: ${err.message}`);
    } finally {
      setIsRegistering(false);
    }
  };

  return (
    <div className="flex-col gap-6">
      <div className="grid-cols-2">
        <div className="flex-col gap-6">
          <Panel 
            title="World Awareness: Oracle Registry" 
            icon={<Globe size={18} />}
            action={
              <button className="btn btn-icon" onClick={fetchSources} disabled={loading}>
                <RefreshCw size={14} className={loading ? 'spin' : ''} />
              </button>
            }
          >
            <div className="flex-col gap-4">
              <div className="text-muted" style={{ fontSize: '0.85rem' }}>
                Authorized off-chain data providers verified by the Integrity Protocol. Consensus nodes read these endpoints to audit agent outputs.
              </div>

              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Source Name</th>
                      <th>URI Endpoint</th>
                      <th>Trust Score</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map(source => (
                      <tr key={source.id} style={{ borderLeft: source.isUserNode ? '2px solid var(--primary)' : 'none' }}>
                        <td style={{ fontWeight: 600 }}>
                          <div className="flex items-center gap-2">
                            {source.name}
                            {source.isUserNode && <span style={{ fontSize: '0.55rem', background: 'var(--primary-dim)', color: 'var(--primary)', padding: '1px 4px', borderRadius: '2px', fontWeight: 700 }}>OWNED</span>}
                          </div>
                        </td>
                        <td className="mono" style={{ fontSize: '0.75rem' }}>{source.uri}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div style={{ width: '50px', height: '6px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden' }}>
                              <div style={{ width: `${source.trustScore / 10}%`, height: '100%', background: source.trustScore > 800 ? 'var(--success)' : 'var(--warning)' }}></div>
                            </div>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{source.trustScore}</span>
                          </div>
                        </td>
                        <td><StatusBadge status={source.active ? 'Active' : 'Inactive'} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>

          <Panel title="Forensic Rollup Visualizer (Layer 0 to L2)" icon={<Layers size={18} />}>
             <div className="flex-col gap-8" style={{ padding: 'var(--space-4) 0' }}>
                <div className="flex items-start justify-between relative">
                   <div style={{ position: 'absolute', top: '24px', left: '10%', right: '10%', height: '2px', background: 'var(--glass-border)', zIndex: 0 }}></div>
                   
                   <RollupStep 
                     active title="Ingestion" 
                     desc="Raw telemetry ingestion from agent edge" 
                     icon={<Database size={20} />} 
                   />
                   <ArrowRight size={16} style={{ marginTop: '16px', color: 'var(--text-muted)', zIndex: 1 }} />
                   <RollupStep 
                     active title="Batching" 
                     desc="Asynchronous buffer (flushing every 100 tx)" 
                     icon={<Layers size={20} />} 
                   />
                   <ArrowRight size={16} style={{ marginTop: '16px', color: 'var(--text-muted)', zIndex: 1 }} />
                   <RollupStep 
                     active title="Merkle Root" 
                     desc="Cryptographic commitment generation" 
                     icon={<CheckCircle size={20} />} 
                   />
                   <ArrowRight size={16} style={{ marginTop: '16px', color: 'var(--text-muted)', zIndex: 1 }} />
                   <RollupStep 
                     active title="L2 Settlement" 
                     desc="On-chain anchor to Base via Rollup Daemon" 
                     icon={<Globe size={20} />} 
                   />
                </div>

                <div style={{ background: 'var(--navy-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-4)' }}>
                   <div className="flex justify-between items-center mb-4">
                      <div className="flex items-center gap-2">
                        <StatusBadge status="Active" />
                        <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Batch ID: 88f2-a231-42cd</span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>Estimated Settlement: 142.2s</div>
                   </div>
                   
                   <div className="flex-col gap-2">
                      <div className="flex justify-between text-muted" style={{ fontSize: '0.65rem' }}>
                        <span>Merkle Path Verification</span>
                        <span>100% Complete</span>
                      </div>
                      <div style={{ width: '100%', height: '4px', background: 'var(--bg-secondary)', borderRadius: '2px', overflow: 'hidden' }}>
                        <motion.div 
                          initial={{ width: 0 }}
                          animate={{ width: '100%' }}
                          transition={{ duration: 2, repeat: Infinity }}
                          style={{ height: '100%', background: 'var(--primary)' }}
                        />
                      </div>
                   </div>
                </div>
             </div>
          </Panel>
        </div>

        <div className="flex-col gap-6">
          {/* Oracle Registration Panel */}
          <Panel title="Oracle Node Registration Portal" icon={<UserCheck size={18} />}>
            <div className="flex-col gap-4">
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Deploy your consensus infrastructure as an active data node. Staking ITK collateral is required to secure honest report attestations and align game-theoretic behavior.
              </div>

              <form onSubmit={handleRegisterNode} className="flex-col gap-3">
                <div className="form-group">
                  <label className="form-label" htmlFor="node-name">Node Alias / Provider Name</label>
                  <input 
                    id="node-name"
                    type="text" 
                    className="input" 
                    placeholder="e.g. Wisconsin Compute Core" 
                    required 
                    value={nodeName}
                    onChange={e => setNodeName(e.target.value)}
                    disabled={isRegistering}
                  />
                </div>
                
                <div className="form-group">
                  <label className="form-label" htmlFor="endpoint-uri">API Endpoint URI</label>
                  <input 
                    id="endpoint-uri"
                    type="url" 
                    className="input" 
                    placeholder="https://oracle.my-node.intg/api/v1" 
                    required 
                    value={endpointUri}
                    onChange={e => setEndpointUri(e.target.value)}
                    disabled={isRegistering}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="stake-collateral">ITK Staking Collateral (Min 5,000 ITK)</label>
                  <input 
                    id="stake-collateral"
                    type="number" 
                    className="input" 
                    min="5000"
                    required
                    value={stakeCollateral}
                    onChange={e => setStakeCollateral(e.target.value)}
                    disabled={isRegistering}
                  />
                </div>

                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  style={{ marginTop: '4px' }} 
                  disabled={isRegistering || !selectedAgent}
                >
                  {isRegistering ? <RefreshCw className="animate-spin" size={16} /> : <Cpu size={16} />}
                  Register Oracle Node
                </button>
              </form>

              {/* Registration Pipeline Logs & Steps */}
              {(isRegistering || regStep > 0) && (
                <div 
                  style={{ 
                    border: '1px solid var(--glass-border)', 
                    background: 'rgba(0,0,0,0.2)', 
                    borderRadius: 'var(--radius-sm)', 
                    padding: '12px',
                    marginTop: '4px'
                  }}
                >
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Shield size={14} className="text-primary" /> Contract Deployment Pipeline
                  </div>
                  
                  {/* Visual steps */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px', gap: '4px' }}>
                    {[
                      { step: 1, label: 'Collateral', icon: <Shield size={12} /> },
                      { step: 2, label: 'KeyGen', icon: <Key size={12} /> },
                      { step: 3, label: 'Broadcast', icon: <Globe size={12} /> },
                      { step: 4, label: 'Sync', icon: <Cpu size={12} /> }
                    ].map(s => {
                      const isCompleted = regStep > s.step;
                      const isActive = regStep === s.step;
                      return (
                        <div key={s.step} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: isActive || isCompleted ? 1 : 0.3 }}>
                          <div style={{ 
                            width: '24px', 
                            height: '24px', 
                            borderRadius: '50%', 
                            background: isCompleted ? 'var(--success)' : isActive ? 'var(--primary)' : 'rgba(255,255,255,0.05)',
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center', 
                            color: '#fff',
                            marginBottom: '4px' 
                          }}>
                            {isCompleted ? <CheckCircle size={14} /> : s.icon}
                          </div>
                          <span style={{ fontSize: '0.6rem', fontWeight: 500, color: isActive ? 'var(--primary)' : 'var(--text-muted)' }}>{s.label}</span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Terminal console */}
                  <div 
                    style={{ 
                      background: 'rgba(0, 0, 0, 0.4)', 
                      padding: '8px', 
                      borderRadius: '4px', 
                      fontFamily: 'monospace', 
                      fontSize: '0.65rem', 
                      color: '#a0a0a0', 
                      lineHeight: 1.45,
                      maxHeight: '100px',
                      overflowY: 'auto' 
                    }}
                  >
                    {regLogs.map((log, idx) => (
                      <div key={idx}>{log}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Panel>

          <Panel title="Oracle Consensus Network Status" icon={<Globe size={18} />}>
            <div className="flex-col gap-4" style={{ padding: '4px 0' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                Active peer consensus nodes validating agent state reports. Multi-signature consensus (2/3 nodes minimum) is required to commit telemetry data to the Base Sepolia L2 anchor ledger.
              </div>
              
              <div className="flex justify-between items-center" style={{ gap: '16px', background: 'var(--bg-secondary)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)', margin: '4px 0' }}>
                {[
                  { name: 'Node 1 (Primary)', role: 'State Attestation', region: 'us-east' },
                  { name: 'Node 2 (Validator)', role: 'ZK Verification', region: 'eu-central' },
                  { name: 'Node 3 (Arbiter)', role: 'Dispute Monitor', region: 'ap-northeast' }
                ].map((node, i) => (
                  <div key={i} className="flex-col items-center" style={{ flex: 1, textAlign: 'center', gap: '4px' }}>
                    <motion.div 
                      animate={{ scale: [1, 1.08, 1], opacity: [0.8, 1, 0.8] }}
                      transition={{ duration: 3, delay: i * 0.5, repeat: Infinity }}
                      style={{ 
                        width: '40px', 
                        height: '40px', 
                        borderRadius: '50%', 
                        background: 'var(--primary-dim)', 
                        border: '2px solid var(--primary)', 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        color: 'var(--primary)',
                        margin: '0 auto 6px'
                      }}
                    >
                      <Globe size={18} />
                    </motion.div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>{node.name}</div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{node.role}</div>
                    <div style={{ fontSize: '0.6rem', color: 'var(--success)', fontWeight: 800, marginTop: '2px', letterSpacing: '0.05em' }}>● ONLINE ({node.region.toUpperCase()})</div>
                  </div>
                ))}
              </div>

              <div className="flex justify-between items-center" style={{ fontSize: '0.8rem', borderTop: '1px solid var(--glass-border)', paddingTop: '10px', marginTop: '2px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Consensus Threshold: <strong style={{ color: 'var(--text-primary)' }}>2/3 Signatures (67%)</strong></span>
                <span style={{ color: 'var(--success)', fontWeight: 600 }}>Stability Index: 99.98%</span>
              </div>
            </div>
          </Panel>

          <Panel title="Recent Settlement Proofs" icon={<Database size={18} />}>
            <div className="flex-col gap-3">
               {[1, 2, 3].map(i => (
                 <div key={i} style={{ padding: 'var(--space-3)', background: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
                   <div className="flex justify-between items-center">
                     <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>L2 Anchor #{4200 + i}</span>
                     <span className="mono" style={{ fontSize: '0.65rem', color: 'var(--primary)' }}>0xMerkle_{i*88}...</span>
                   </div>
                   <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                     Settled on Base @ Block #12,884,9{i}
                   </div>
                 </div>
               ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
