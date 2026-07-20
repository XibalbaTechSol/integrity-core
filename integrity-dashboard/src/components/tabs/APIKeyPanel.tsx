import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { Key, Copy, CheckCircle, AlertTriangle, Trash2, Clock, Plus } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { userapi, type ApiKeyResponse, type ApiKeyCreateResponse, getToken } from '../../services/userapi';

export function APIKeyPanel() {
  const { addToast } = useDashboard();
  const [apiKeys, setApiKeys] = useState<ApiKeyResponse[]>([]);
  // Only the freshly-created key carries the raw secret (userapi returns it
  // exactly once on creation; existing keys expose only their id/metadata).
  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const isAuthed = !!getToken();

  useEffect(() => {
    fetchKeys();
  }, []);

  const fetchKeys = async () => {
    // Real userapi keys require a logged-in session (JWT). Without one there's
    // nothing to fetch -- show the empty/sign-in state rather than erroring.
    if (!getToken()) {
      setIsLoading(false);
      return;
    }
    try {
      const keys = await userapi.listApiKeys();
      // Show only live keys; revoked ones stay in the audit history server-side.
      setApiKeys(keys.filter(k => !k.revoked_at));
    } catch (err: any) {
      addToast('error', `Failed to fetch API Keys: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerateKey = async () => {
    setIsGenerating(true);
    try {
      const res = await userapi.createApiKey();
      setNewKey(res);
      setApiKeys(prev => [...prev, res]);
      addToast('success', 'New Developer API Key generated');
    } catch (err: any) {
      addToast('error', `Failed to generate API Key: ${err.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDeleteKey = async (id: string) => {
    if (!confirm('Are you sure you want to revoke this API key? This action cannot be undone.')) return;

    setIsDeleting(id);
    try {
      await userapi.revokeApiKey(id);
      setApiKeys(prev => prev.filter(k => k.id !== id));
      if (newKey?.id === id) setNewKey(null);
      addToast('success', 'API Key revoked');
    } catch (err: any) {
      addToast('error', `Failed to revoke API Key: ${err.message}`);
    } finally {
      setIsDeleting(null);
    }
  };

  const copyToClipboard = (key: string) => {
    navigator.clipboard.writeText(key);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="flex-col gap-6">
      <Panel title="Developer API Keys" icon={<Key size={18} />}>
        <div className="flex-col gap-6">
          <div className="text-muted" style={{ fontSize: '0.875rem' }}>
            Generate a Developer API Key to authenticate your agent with the Integrity Oracle without a hardware-backed DID. 
            Agents using this auth bypass are mathematically capped at a Trust Level (AIS) of <strong style={{ color: 'var(--primary)' }}>300</strong>.
          </div>

          <div style={{ padding: 'var(--space-4)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
            <h4 style={{ marginBottom: 'var(--space-3)', fontSize: '0.9rem', fontWeight: 600 }}>Generate New Key</h4>
            <div className="flex items-center gap-4">
              <button
                className="btn btn-primary"
                onClick={handleGenerateKey}
                disabled={isGenerating || !isAuthed}
                style={{ marginTop: 'auto' }}
              >
                {isGenerating ? 'Generating...' : <><Plus size={16} style={{ marginRight: '8px' }} /> Generate Key</>}
              </button>
              {!isAuthed && (
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Sign in to manage API keys</span>
              )}
            </div>
          </div>

          {newKey && (
            <div style={{ padding: 'var(--space-4)', background: 'rgba(0, 255, 135, 0.05)', borderRadius: 'var(--radius-md)', border: '1px solid var(--success)' }}>
              <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--success)' }}>
                <CheckCircle size={16} /> 
                <span style={{ fontWeight: 600 }}>New Key Generated</span>
              </div>
              <div className="text-muted" style={{ fontSize: '0.875rem', marginBottom: 'var(--space-4)' }}>
                Please copy this key now. For security reasons, it will never be shown again in full.
              </div>
              
              <div className="flex gap-2 items-center">
                <input
                  type="text"
                  className="input mono"
                  value={newKey.raw_key}
                  readOnly
                  style={{ flex: 1, letterSpacing: '1px' }}
                />
                <button className="btn" onClick={() => copyToClipboard(newKey.raw_key)} style={{ minWidth: '100px' }}>
                  {copiedKey === newKey.raw_key ? 'Copied!' : <><Copy size={16} style={{ marginRight: '8px' }} /> Copy</>}
                </button>
              </div>
            </div>
          )}

          <div className="flex-col gap-3">
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600 }}>Active API Keys</h4>
            {isLoading ? (
              <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center' }}>Loading keys...</div>
            ) : !isAuthed ? (
              <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                Sign in to view and manage your API keys.
              </div>
            ) : apiKeys.length === 0 ? (
              <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                No active API keys found.
              </div>
            ) : (
              <div className="flex-col gap-2">
                {apiKeys.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between"
                    style={{
                      padding: 'var(--space-3) var(--space-4)',
                      background: 'var(--bg-secondary)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-color)'
                    }}
                  >
                    <div className="flex-col gap-1">
                      <div className="mono" style={{ fontSize: '0.85rem' }}>
                        {key.id.substring(0, 12)}...{key.id.substring(key.id.length - 4)}
                      </div>
                      <div className="flex items-center gap-3" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        <span className="flex items-center gap-1"><Clock size={12} /> AIS ceiling: {key.ais_trust_ceiling}</span>
                        <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => copyToClipboard(key.id)}
                        title="Copy key ID"
                      >
                        {copiedKey === key.id ? 'Copied' : <Copy size={14} />}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleDeleteKey(key.id)}
                        disabled={isDeleting === key.id}
                        style={{ color: 'var(--danger)' }}
                        title="Revoke Key"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ padding: 'var(--space-3)', background: 'rgba(255, 68, 68, 0.1)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--danger)', display: 'flex', gap: '12px' }}>
            <AlertTriangle size={20} color="var(--danger)" style={{ flexShrink: 0 }} />
            <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)' }}>
              <strong>Security Warning:</strong> Never commit your API key to public repositories. If your key is compromised, delete it immediately and generate a new one.
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}
