import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { userapi, getToken } from '../services/userapi';

// Some browser/embedding contexts throw on any localStorage access rather than returning
// null -- see DashboardContext.tsx's identical helper for why this must never be unguarded
// (this provider's useState initializer runs during initial render, so an unguarded throw
// here takes down every route this provider wraps).
function safeLocalStorageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeLocalStorageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Best-effort only.
  }
}

export type Theme = 'light' | 'dark' | 'cyber' | 'xibalba';
export type Font = 'Inter' | 'Roboto' | 'Fira Code' | 'Playfair Display' | 'System Default';

// Mirrors userapi's real ApiKeyResponse — there is no per-key name/permissions/expiry
// on the backend, only an AIS trust ceiling and revocation state. `rawKey` is present
// only immediately after creation (the backend never returns the secret again).
export interface ApiKey {
  id: string;
  aisTrustCeiling: number;
  revokedAt: string | null;
  createdAt: string;
  rawKey?: string;
}

interface SettingsState {
  theme: Theme;
  font: Font;
  fontSize: number;
  appName: string;
  headerStyle: 'solid' | 'transparent' | 'blur';
  animationsEnabled: boolean;
  apiKeys: ApiKey[];
}

interface SettingsContextType extends SettingsState {
  updateSettings: (newSettings: Partial<Omit<SettingsState, 'apiKeys'>>) => void;
  createApiKey: () => Promise<void>;
  deleteApiKey: (id: string) => Promise<void>;
  apiKeysAuthed: boolean;
}

const defaultSettings: Omit<SettingsState, 'apiKeys'> = {
  theme: 'dark',
  font: 'System Default',
  fontSize: 16,
  appName: 'Integrity MVP', // matches index.html's static <title> so applying it on mount is a no-op, not a flash
  headerStyle: 'solid',
  animationsEnabled: true,
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<Omit<SettingsState, 'apiKeys'>>(() => {
    const saved = safeLocalStorageGet('appSettings');
    return saved ? { ...defaultSettings, ...JSON.parse(saved) } : defaultSettings;
  });
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);

  useEffect(() => {
    safeLocalStorageSet('appSettings', JSON.stringify(settings));
    document.documentElement.setAttribute('data-theme', settings.theme);
    document.documentElement.style.setProperty('--font-family',
      settings.font === 'System Default' ? 'system-ui, -apple-system, sans-serif' : `"${settings.font}", sans-serif`
    );
    document.documentElement.style.setProperty('--base-font-size', `${settings.fontSize}px`);
    // SettingsPage's own caption claims "This title appears in headers and notifications" --
    // that was never true (appName was stored but nothing read it back). Actually apply it.
    document.title = settings.appName || 'Xibalba MVP';
  }, [settings]);

  const refreshApiKeys = useCallback(() => {
    if (!getToken()) { setApiKeys([]); return; }
    userapi.listApiKeys()
      .then(keys => setApiKeys(keys.map(k => ({ id: k.id, aisTrustCeiling: k.ais_trust_ceiling, revokedAt: k.revoked_at, createdAt: k.created_at }))))
      .catch(() => setApiKeys([]));
  }, []);

  useEffect(() => {
    refreshApiKeys();
    window.addEventListener('integrity-auth-changed', refreshApiKeys);
    return () => window.removeEventListener('integrity-auth-changed', refreshApiKeys);
  }, [refreshApiKeys]);

  const updateSettings = (newSettings: Partial<Omit<SettingsState, 'apiKeys'>>) => {
    setSettings(prev => ({ ...prev, ...newSettings }));
  };

  const createApiKey = async () => {
    const created = await userapi.createApiKey();
    setApiKeys(prev => [...prev, {
      id: created.id,
      aisTrustCeiling: created.ais_trust_ceiling,
      revokedAt: created.revoked_at,
      createdAt: created.created_at,
      rawKey: created.raw_key,
    }]);
  };

  const deleteApiKey = async (id: string) => {
    await userapi.revokeApiKey(id);
    refreshApiKeys();
  };

  return (
    <SettingsContext.Provider value={{ ...settings, apiKeys, updateSettings, createApiKey, deleteApiKey, apiKeysAuthed: !!getToken() }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) throw new Error('useSettings must be used within SettingsProvider');
  return context;
};
