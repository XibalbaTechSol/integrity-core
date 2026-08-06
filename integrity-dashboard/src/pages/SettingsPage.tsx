import { useDashboard } from '../context/useDashboard';
import { useSettings } from '../context/SettingsProvider';
import { useState, useEffect } from 'react';
import axios from 'axios';
import { auth } from '../firebase';
import { Settings, Save, Shield, Cpu, Network, Database, Loader2, Info } from 'lucide-react';
import { API_BASE } from '../constants';
import { APIKeyPanel } from '../components/tabs/APIKeyPanel';
import { userapi } from '../services/userapi';

export function SettingsPage() {
  const { fetchData } = useDashboard();
  const { theme, font, setTheme, setFont } = useSettings();
  const [mockMode, setMockMode] = useState(() => localStorage.getItem('integrity_mock_mode') === 'true');
  const [settings, setProtocolSettings] = useState({
      wallet_mode: 'SELF_CUSTODIAL',
      rpc_endpoint: 'https://sepolia.base.org',
      itk_token_address: '0xF448c05074D435d256D6fbc1fC059019B86A5408',
      enable_hardware_bridge: false,
      kms_provider: 'LOCAL'
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const fetchSettings = async () => {
      try {
          const res = await axios.get(`${API_BASE}/v1/protocol/settings`);
          setProtocolSettings(res.data);
      } catch (e) {
          console.error("Failed to fetch settings:", e);
      } finally {
          setIsLoading(false);
      }
  };

  useEffect(() => {
      fetchSettings();
  }, []);

  const handleSave = async () => {
      setIsSaving(true);
      try {
          const user = auth.currentUser;
          if (!user) {
            alert("You must be logged in.");
            return;
          }
          const token = await user.getIdToken();
          await axios.post(`${API_BASE}/v1/protocol/settings`, settings, {
              headers: { Authorization: `Bearer ${token}` }
          });
          alert("Protocol configuration updated successfully.");
      } catch (e) {
          console.error("Save failed:", e);
          alert("Failed to update settings.");
      } finally {
          setIsSaving(false);
      }
  };

  return (
    <div className="dash-section" style={{ padding: '40px' }}>

      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', maxWidth: '900px' }}>
        <div className="enterprise-card p-6" style={{ padding: '32px' }}>
          <h3 className="heading-md mb-6 text-gold">Appearance</h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <div>
              <label className="text-sm font-bold mb-4" style={{ display: 'block' }}>Dashboard Theme</label>
              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                {[
                  { id: 'dark', label: 'Navy & Gold (Default)' },
                  { id: 'xibalba-sovereign', label: 'Xibalba Sovereign (Slate & Blue)' },
                  { id: 'light', label: 'Light' },
                  { id: 'system', label: 'System' }
                ].map(t => (
                  <button
                    key={t.id}
                    className={`btn ${theme === t.id ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setTheme(t.id as any)}
                    style={{ padding: '12px 24px' }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            
            <hr style={{ borderTop: '1px solid var(--border)' }} />
            
            <div>
              <label className="text-sm font-bold mb-4" style={{ display: 'block' }}>Typography Font Family</label>
              <div style={{ display: 'flex', gap: '16px' }}>
                {['Raleway', 'Inter', 'Outfit'].map(f => (
                  <button
                    key={f}
                    className={`btn ${font === f ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setFont(f as any)}
                    style={{ padding: '12px 24px', fontFamily: f }}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="enterprise-card p-6" style={{ padding: '32px' }}>
          <h3 className="heading-md mb-6 text-gold">Dashboard Configurations</h3>
          <p className="text-muted" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
            Configure dashboard state and data mode options.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 0', borderTop: '1px solid var(--border)' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Enable Mock Mode</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Load seeded mock agents instead of only the local Xibalba agent.</div>
            </div>
            <input
              type="checkbox"
              checked={mockMode}
              onChange={async (e) => { 
                const checked = e.target.checked;
                setMockMode(checked); 
                localStorage.setItem('integrity_mock_mode', String(checked)); 
                if (checked) {
                  try {
                    const res = await fetch('/integrity/__/run-demo', { method: 'POST' });
                    if (!res.ok) throw new Error("Failed to trigger demo on host");
                    alert("Demo mode seeded successfully!");
                  } catch (e) {
                    console.error("Failed to seed demo mode:", e);
                    alert("Failed to seed demo mode.");
                  }
                }
                if (fetchData) fetchData(); 
              }}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
          </div>
        </div>

        <div className="enterprise-card p-6" style={{ padding: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(212, 175, 55, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)', flexShrink: 0 }}>
                  <Settings size={24} />
              </div>
              <div style={{ overflow: 'hidden' }}>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 900, margin: 0, color: 'var(--text-primary)' }}>Protocol Config</h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>Manage infrastructure and storage parameters.</p>
              </div>
          </div>

          {isLoading ? (
            <div style={{ padding: '40px', textAlign: 'center' }}><Loader2 className="animate-spin" /></div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
                {/* Left: Security & Wallet */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    <section>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                            <Shield size={14} style={{ color: 'var(--gold)' }} />
                            <label style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Storage Strategy</label>
                        </div>
                        <select 
                            value={settings.wallet_mode}
                            onChange={(e) => setProtocolSettings({...settings, wallet_mode: e.target.value})}
                            style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'var(--glass-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                        >
                            <option value="SELF_CUSTODIAL">MetaMask / Browser (Self-Custodial)</option>
                            <option value="APP_MANAGED">Xibalba Secure Vault (App-Managed)</option>
                            <option value="HARDWARE_COLD">Hardware Cold Storage (Ledger/Trezor)</option>
                        </select>
                        <p style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '8px' }}>
                            Defines the primary signature provider for agent interactions.
                        </p>
                    </section>

                    <section>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                            <Cpu size={14} style={{ color: 'var(--gold)' }} />
                            <label style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>KMS Provider</label>
                        </div>
                        <select 
                            value={settings.kms_provider}
                            onChange={(e) => setProtocolSettings({...settings, kms_provider: e.target.value})}
                            style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'var(--glass-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                        >
                            <option value="LOCAL">Local Encrypted (Development)</option>
                            <option value="AWS_KMS">AWS KMS (Institutional)</option>
                            <option value="FIREBLOCKS">Fireblocks (Enterprise)</option>
                        </select>
                    </section>

                    <section style={{ padding: '16px', background: 'rgba(212, 175, 55, 0.05)', borderRadius: '12px', border: '1px solid rgba(212, 175, 55, 0.1)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <input 
                                type="checkbox" 
                                checked={settings.enable_hardware_bridge}
                                onChange={(e) => setProtocolSettings({...settings, enable_hardware_bridge: e.target.checked})}
                            />
                            <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>Enable Direct Hardware Bridge</span>
                        </div>
                        <p style={{ fontSize: '0.6rem', color: 'rgba(212, 175, 55, 0.6)', marginTop: '4px' }}>
                            Required for direct HID communication with Ledger/Trezor devices via WebUSB.
                        </p>
                    </section>
                </div>

                {/* Right: Network & Token */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    <section>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                            <Network size={14} style={{ color: 'var(--gold)' }} />
                            <label style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>RPC Endpoint</label>
                        </div>
                        <input 
                            type="text"
                            value={settings.rpc_endpoint}
                            onChange={(e) => setProtocolSettings({...settings, rpc_endpoint: e.target.value})}
                            style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'var(--glass-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: '0.75rem' }}
                        />
                    </section>

                    <section>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                            <Database size={14} style={{ color: 'var(--gold)' }} />
                            <label style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>ITK Token Contract</label>
                        </div>
                        <input 
                            type="text"
                            value={settings.itk_token_address}
                            onChange={(e) => setProtocolSettings({...settings, itk_token_address: e.target.value})}
                            style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'var(--glass-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: '0.75rem' }}
                        />
                    </section>

                    <div style={{ marginTop: 'auto', padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', display: 'flex', gap: '12px' }}>
                        <Info size={16} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                        <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', margin: 0 }}>
                            Global settings apply to the entire protocol fleet. Changing the Storage Strategy will affect how new agent identities are generated and anchored.
                        </p>
                    </div>
                </div>
            </div>
          )}

          <div style={{ marginTop: '40px', borderTop: '1px solid var(--border)', paddingTop: '24px', display: 'flex', justifyContent: 'flex-end' }}>
              <button 
                  onClick={handleSave}
                  disabled={isSaving}
                  className="btn btn-primary"
                  style={{ padding: '12px 32px', display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                  {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
                  Save Infrastructure Config
              </button>
          </div>
        </div>
      </div>
      
      <div style={{ marginTop: '24px' }}>
        <APIKeyPanel />
      </div>
    </div>
  );
}
