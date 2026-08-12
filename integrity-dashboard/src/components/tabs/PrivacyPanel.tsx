import { useState, useEffect } from 'react';
import { ethers } from 'ethers';
import { Panel } from '../shared/Panel';
import { Shield, Save, Loader2 } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle } from '../../services/oracle';
import { RPC_URL } from '../../constants';
import { AGENT_PROFILE_ABI, executeAsAgent } from '../../chain/markets';

// Real AgentProfile wiring (no mock api.updateAgentMetadata). AgentProfile only affords
// setProfile(primaryDomain, profileURI) — there is no on-chain field for arbitrary privacy
// flags. So the panel's preferences are serialized into the agent's on-chain profileURI as a
// data: JSON document (a legitimate profile-document pointer that happens to be inline), while
// the agent's existing primaryDomain is preserved. setProfile is admin-gated to the
// SovereignAgent, so the write routes through SovereignAgent.execute (executeAsAgent). The
// current prefs are read straight back from the on-chain profileURI on load.
const DEFAULT_PREFS = { privacy_mode: 'public' as const, publish_telemetry: true, publish_transactions: true, publish_staking: true };

function parseProfileURI(uri: string): typeof DEFAULT_PREFS {
  try {
    if (uri?.startsWith('data:')) {
      const json = decodeURIComponent(uri.slice(uri.indexOf(',') + 1));
      return { ...DEFAULT_PREFS, ...JSON.parse(json) };
    }
  } catch { /* not our JSON document */ }
  return DEFAULT_PREFS;
}

export function PrivacyPanel() {
  const { selectedAgent, addToast, walletAddress, connectWallet } = useDashboard();
  const [privacyMode, setPrivacyMode] = useState<'public' | 'pseudonymous' | 'zero_knowledge'>('public');
  const [publishTelemetry, setPublishTelemetry] = useState(true);
  const [publishTransactions, setPublishTransactions] = useState(true);
  const [publishStaking, setPublishStaking] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Load the real prefs from the agent's on-chain AgentProfile.profileURI.
  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    (async () => {
      try {
        const detail = await oracle.getAgent(selectedAgent.eth_address);
        const profileAddr = detail.primitives?.agent_profile;
        if (!profileAddr || /^0x0+$/i.test(profileAddr)) return;
        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const profile = new ethers.Contract(profileAddr, AGENT_PROFILE_ABI, provider);
        const uri: string = await profile.profileURI();
        if (!active) return;
        const p = parseProfileURI(uri);
        setPrivacyMode(p.privacy_mode);
        setPublishTelemetry(p.publish_telemetry);
        setPublishTransactions(p.publish_transactions);
        setPublishStaking(p.publish_staking);
      } catch { /* leave defaults */ }
    })();
    return () => { active = false; };
  }, [selectedAgent]);

  const handleSave = async () => {
    if (!selectedAgent) return;
    if (!walletAddress) { addToast('error', 'Connect the agent controller wallet to save on-chain.'); return; }
    setIsSaving(true);
    try {
      const detail = await oracle.getAgent(selectedAgent.eth_address);
      const profileAddr = detail.primitives?.agent_profile;
      const sovereignAgent = detail.primitives?.sovereign_agent;
      if (!profileAddr || /^0x0+$/i.test(profileAddr)) throw new Error('Agent has no deployed AgentProfile clone.');
      if (!sovereignAgent || /^0x0+$/i.test(sovereignAgent)) throw new Error('Agent has no on-chain SovereignAgent.');

      const eth = (window as any).ethereum;
      const signer = await new ethers.BrowserProvider(eth).getSigner();
      // Preserve the agent's existing primaryDomain; only the profileURI changes.
      const readProfile = new ethers.Contract(profileAddr, AGENT_PROFILE_ABI, signer);
      const primaryDomain: string = await readProfile.primaryDomain();

      const prefs = { privacy_mode: privacyMode, publish_telemetry: publishTelemetry, publish_transactions: publishTransactions, publish_staking: publishStaking };
      const profileURI = 'data:application/json,' + encodeURIComponent(JSON.stringify(prefs));
      const data = new ethers.Interface(AGENT_PROFILE_ABI as any).encodeFunctionData('setProfile', [primaryDomain, profileURI]);

      addToast('info', 'Writing profile to chain…');
      // Route through the real SovereignAgent (admin of the AgentProfile), NOT the DID.
      await executeAsAgent(signer, sovereignAgent, profileAddr, data);
      addToast('success', 'Privacy configurations written on-chain.');
    } catch (err: any) {
      addToast('error', `Failed to update profile: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (!selectedAgent) {
    return (
      <Panel title="Privacy & Security Options" icon={<Shield size={18} />}>
        <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center' }}>
          Select an agent from the sidebar to configure privacy settings.
        </div>
      </Panel>
    );
  }

  return (
    <Panel title="Privacy & Security Options" icon={<Shield size={18} />}>
      <div className="flex-col gap-6">
        <div className="text-muted" style={{ fontSize: '0.875rem' }}>
          Configure data visibility, credential exposure, and cryptographic zero-knowledge constraints for this agent.
        </div>

        {/* Privacy Mode */}
        <div style={{ padding: 'var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <h4 style={{ marginBottom: 'var(--space-2)', fontSize: '0.9rem', fontWeight: 600 }}>Privacy Mode</h4>
          <p className="text-muted" style={{ fontSize: '0.75rem', marginBottom: 'var(--space-4)' }}>
            Specify the degree of cryptographic abstraction used for agent verification on-chain.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-4)' }}>
            <label 
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: 'var(--space-4)',
                background: privacyMode === 'public' ? 'var(--primary-dim)' : 'var(--bg-primary)',
                border: `1px solid ${privacyMode === 'public' ? 'var(--primary)' : 'var(--border-color)'}`,
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem' }}>
                <input 
                  type="radio" 
                  name="privacyMode" 
                  value="public" 
                  checked={privacyMode === 'public'} 
                  onChange={() => setPrivacyMode('public')}
                />
                Public Mode
              </div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Transparent execution tracking and telemetry.</span>
            </label>

            <label 
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: 'var(--space-4)',
                background: privacyMode === 'pseudonymous' ? 'var(--primary-dim)' : 'var(--bg-primary)',
                border: `1px solid ${privacyMode === 'pseudonymous' ? 'var(--primary)' : 'var(--border-color)'}`,
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem' }}>
                <input 
                  type="radio" 
                  name="privacyMode" 
                  value="pseudonymous" 
                  checked={privacyMode === 'pseudonymous'} 
                  onChange={() => setPrivacyMode('pseudonymous')}
                />
                Pseudonymous
              </div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Decouples real-world metadata; binds identity strictly to cryptographic DID.</span>
            </label>

            <label 
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: 'var(--space-4)',
                background: privacyMode === 'zero_knowledge' ? 'var(--primary-dim)' : 'var(--bg-primary)',
                border: `1px solid ${privacyMode === 'zero_knowledge' ? 'var(--primary)' : 'var(--border-color)'}`,
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem', color: 'var(--theme-accent)' }}>
                <input 
                  type="radio" 
                  name="privacyMode" 
                  value="zero_knowledge" 
                  checked={privacyMode === 'zero_knowledge'} 
                  onChange={() => setPrivacyMode('zero_knowledge')}
                />
                Zero-Knowledge
              </div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Noir standard ZK-proofs verifying metrics and scores without telemetry disclosure.</span>
            </label>
          </div>
        </div>

        {/* Toggles */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 600, margin: 0 }}>Data Publishing Consents</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Publish Telemetry Logs</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Enable streaming system performance logs and entropy signals.</div>
              </div>
              <input 
                type="checkbox" 
                checked={publishTelemetry} 
                onChange={(e) => setPublishTelemetry(e.target.checked)} 
                style={{ width: '16px', height: '16px' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Publish Transaction History</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Expose task executions, outcome compliance, and dispute history.</div>
              </div>
              <input 
                type="checkbox" 
                checked={publishTransactions} 
                onChange={(e) => setPublishTransactions(e.target.checked)} 
                style={{ width: '16px', height: '16px' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Publish Staking Data</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Allow public verification of locked collateral and sacrifice score.</div>
              </div>
              <input 
                type="checkbox" 
                checked={publishStaking} 
                onChange={(e) => setPublishStaking(e.target.checked)} 
                style={{ width: '16px', height: '16px' }}
              />
            </div>

          </div>
        </div>

        {/* Save Button */}
        <button 
          className="btn btn-primary" 
          onClick={handleSave} 
          disabled={isSaving}
          style={{ alignSelf: 'flex-end', display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          {isSaving ? <Loader2 size={16} className="spin" /> : <Save size={16} />}
          Save Privacy Configurations
        </button>
      </div>
    </Panel>
  );
}
