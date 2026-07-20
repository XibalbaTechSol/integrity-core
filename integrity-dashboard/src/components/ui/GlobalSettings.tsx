// @ts-nocheck
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { auth } from '../../firebase';
import { Settings, Save, Shield, Cpu, Network, Database, Loader2, Info } from 'lucide-react';
import { motion } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';
import { API_BASE } from '../../constants';

export const GlobalSettings = () => {
    const [settings, setSettings] = useState({
        wallet_mode: 'SELF_CUSTODIAL',
        rpc_endpoint: 'https://sepolia.base.org',
        itk_token_address: '0xF448c05074D435d256D6fbc1fC059019B86A5408',
        enable_hardware_bridge: false,
        kms_provider: 'LOCAL'
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const isMobile = useIsMobile();

    const fetchSettings = async () => {
        try {
            const res = await axios.get(`${API_BASE}/v1/protocol/settings`);
            setSettings(res.data);
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
            if (!user) return;
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

    if (isLoading) return <div style={{ padding: '40px', textAlign: 'center' }}><Loader2 className="animate-spin" /></div>;

    return (
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
            <div className="enterprise-card" style={{ padding: isMobile ? '20px' : '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: isMobile ? '24px' : '32px' }}>
                    <div style={{ width: isMobile ? '40px' : '48px', height: isMobile ? '40px' : '48px', borderRadius: '12px', background: 'rgba(212, 175, 55, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)', flexShrink: 0 }}>
                        <Settings size={isMobile ? 20 : 24} />
                    </div>
                    <div style={{ overflow: 'hidden' }}>
                        <h2 style={{ fontSize: isMobile ? '1.1rem' : '1.5rem', fontWeight: 900, margin: 0, color: 'white' }}>Protocol Settings</h2>
                        <p style={{ fontSize: isMobile ? '0.7rem' : '0.8rem', color: 'rgba(255,255,255,0.4)', margin: 0 }}>Manage infrastructure and storage parameters.</p>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: isMobile ? '20px' : '32px' }}>
                    {/* Left: Security & Wallet */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                        <section>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                                <Shield size={14} style={{ color: 'var(--gold)' }} />
                                <label style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Storage Strategy</label>
                            </div>
                            <select 
                                value={settings.wallet_mode}
                                onChange={(e) => setSettings({...settings, wallet_mode: e.target.value})}
                                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#0a0b0d', border: '1px solid rgba(255,255,255,0.1)', color: 'white' }}
                            >
                                <option value="SELF_CUSTODIAL">MetaMask / Browser (Self-Custodial)</option>
                                <option value="APP_MANAGED">Xibalba Secure Vault (App-Managed)</option>
                                <option value="HARDWARE_COLD">Hardware Cold Storage (Ledger/Trezor)</option>
                            </select>
                            <p style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', marginTop: '8px' }}>
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
                                onChange={(e) => setSettings({...settings, kms_provider: e.target.value})}
                                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#0a0b0d', border: '1px solid rgba(255,255,255,0.1)', color: 'white' }}
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
                                    onChange={(e) => setSettings({...settings, enable_hardware_bridge: e.target.checked})}
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
                                onChange={(e) => setSettings({...settings, rpc_endpoint: e.target.value})}
                                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#0a0b0d', border: '1px solid rgba(255,255,255,0.1)', color: 'white', fontFamily: 'monospace', fontSize: '0.75rem' }}
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
                                onChange={(e) => setSettings({...settings, itk_token_address: e.target.value})}
                                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#0a0b0d', border: '1px solid rgba(255,255,255,0.1)', color: 'white', fontFamily: 'monospace', fontSize: '0.75rem' }}
                            />
                        </section>

                        <div style={{ marginTop: 'auto', padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', display: 'flex', gap: '12px' }}>
                            <Info size={16} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                            <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', margin: 0 }}>
                                Global settings apply to the entire protocol fleet. Changing the Storage Strategy will affect how new agent identities are generated and anchored.
                            </p>
                        </div>
                    </div>
                </div>

                <div style={{ marginTop: isMobile ? '24px' : '40px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '24px', display: 'flex', justifyContent: isMobile ? 'stretch' : 'flex-end' }}>
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
    );
};
