import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Shield, Eye, EyeOff, Save, Loader2 } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { api } from '../../services/api';

export function PrivacyPanel() {
  const { selectedAgent, addToast, fetchData } = useDashboard();
  const [privacyMode, setPrivacyMode] = useState<'public' | 'pseudonymous' | 'zero_knowledge'>('public');
  const [publishTelemetry, setPublishTelemetry] = useState(true);
  const [publishTransactions, setPublishTransactions] = useState(true);
  const [publishStaking, setPublishStaking] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Initialize values when selectedAgent changes
  useEffect(() => {
    if (selectedAgent) {
      const meta = (selectedAgent as any).metadata || {};
      setPrivacyMode(meta.privacy_mode || 'public');
      setPublishTelemetry(meta.publish_telemetry !== false);
      setPublishTransactions(meta.publish_transactions !== false);
      setPublishStaking(meta.publish_staking !== false);
    }
  }, [selectedAgent]);

  const handleSave = async () => {
    if (!selectedAgent) return;
    setIsSaving(true);
    try {
      await api.updateAgentMetadata(selectedAgent.eth_address, {
        privacy_mode: privacyMode,
        publish_telemetry: publishTelemetry,
        publish_transactions: publishTransactions,
        publish_staking: publishStaking
      });
      addToast('success', 'Privacy configurations updated successfully.');
      await fetchData();
    } catch (err: any) {
      addToast('error', `Failed to update privacy settings: ${err.message}`);
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
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem', color: 'var(--gold)' }}>
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
