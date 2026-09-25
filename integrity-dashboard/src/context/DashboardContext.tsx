import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { ethers } from 'ethers';
import { oracle, AgentSummary } from '../services/oracle';
import { userapi, getToken, UserResponse } from '../services/userapi';
import { BASE_SEPOLIA_CHAIN_ID } from '../constants';
import { ALLOW_UNSCOPED_AGENT_DIRECTORY } from '../config';
import { graphMemory } from '../services/graphMemory';

// Some browser/embedding contexts (e.g. a sandboxed automation profile) throw on any
// localStorage access rather than just returning null -- these calls run during initial
// render (the walletAddress useState initializer below), so an unguarded throw here takes
// down this provider and therefore every route MainAppLayout wraps, not just this file.
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
    // Best-effort only -- see safeLocalStorageGet's comment.
  }
}

function sharedScopeFromUrl(): { agentId: string; storeId: string } {
  try {
    const params = new URLSearchParams(window.location.search);
    return { agentId: params.get('agent_id') || '', storeId: params.get('store_id') || '' };
  } catch {
    return { agentId: '', storeId: '' };
  }
}

function writeSharedScope(agentId: string, storeId = ''): void {
  try {
    const url = new URL(window.location.href);
    const params = url.searchParams;
    if (agentId) params.set('agent_id', agentId); else params.delete('agent_id');
    if (storeId) params.set('store_id', storeId); else params.delete('store_id');
    window.history.replaceState({}, '', `${url.pathname}${params.toString() ? `?${params}` : ''}${url.hash}`);
  } catch {
    // URL persistence is a best-effort cross-origin handoff hint.
  }
}

export interface Agent {
  /** The agent's DID — historically named `eth_address` across this codebase (see
   *  oracle.ts's resolveSovereignAgent comment); never use this as an on-chain
   *  address, resolve the real SovereignAgent via oracle.resolveSovereignAgent(id). */
  id: string;
  eth_address: string;
  controller?: string | null;
  name?: string | null;
  alias?: string | null;
  verification_tier: number;
  current_ais?: number;
  staked_itk?: number;
  tee_verified?: boolean;
  /** Cortex's mounted-store namespace. A DID alone is not a unique memory authority. */
  store_id?: string;
  profile_id?: string;
  store_access?: string;
  writable?: boolean;
  namespace_key?: string;
  namespace_state?: 'cortex' | 'unavailable';
}

export interface ApiKey {
  id: string;
  name: string;
  key: string;
  permissions: 'Read-Only' | 'Read/Write';
  expiresAt: string | null;
}

interface User {
  name: string;
  email: string;
  avatarUrl: string;
}

interface Stats {
  active_nodes: number;
  aggregate_ais: number;
  protocol_staked_itk: number;
}

interface DashboardContextType {
  activeTrace: any;
  setActiveTrace: (trace: any) => void;
  selectedSpanId: string | null;
  setSelectedSpanId: (id: string | null) => void;
  selectedAgent: Agent | null;
  setSelectedAgent: (agent: Agent) => void;
  selectAgent: (agent: Agent) => void;
  agents: Agent[];
  agentsLoading: boolean;
  layoutMode: 'sidebar' | 'header';
  setLayoutMode: (mode: 'sidebar' | 'header') => void;
  theme: 'dark' | 'light' | 'cyber';
  setTheme: (theme: 'dark' | 'light' | 'cyber') => void;
  fontFamily: string;
  setFontFamily: (font: string) => void;
  fontSize: 'small' | 'medium' | 'large';
  setFontSize: (size: 'small' | 'medium' | 'large') => void;
  apiKeys: ApiKey[];
  setApiKeys: (keys: ApiKey[]) => void;
  user: User | null;
  signOut: () => Promise<void>;
  walletAddress: string | null;
  connectWallet: () => Promise<boolean>;
  addToast: (type: 'success' | 'error' | 'info', message: string) => void;
  stats: Stats | null;
}

const LAST_AGENT_KEY = 'integrity_mvp_last_agent';
const WALLET_KEY = 'integrity_wallet_connected';

function agentFromSummary(s: AgentSummary): Agent {
  return {
    id: s.id,
    eth_address: s.id,
    controller: s.controller ?? null,
    name: s.name ?? null,
    alias: s.handle ?? s.name ?? null,
    verification_tier: s.verification_tier,
    namespace_state: 'unavailable',
  };
}

function agentFromOwnedRecord(record: { agent_did: string; live_data: Record<string, unknown> | null }): Agent {
  const live = record.live_data;
  const verificationTier = typeof live?.verification_tier === 'number' ? live.verification_tier : 0;
  return {
    id: record.agent_did,
    eth_address: record.agent_did,
    controller: null,
    name: null,
    alias: null,
    verification_tier: verificationTier,
    namespace_state: 'unavailable',
  };
}

function userFromWallet(address: string): User {
  return {
    name: `${address.substring(0, 6)}...${address.substring(address.length - 4)}`,
    email: '',
    avatarUrl: `https://api.dicebear.com/7.x/identicon/svg?seed=${address}`,
  };
}

function userFromResponse(u: UserResponse): User {
  return {
    name: u.name || u.email,
    email: u.email,
    avatarUrl: u.photoURL || `https://api.dicebear.com/7.x/identicon/svg?seed=${u.email}`,
  };
}

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export const DashboardProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeTrace, setActiveTrace] = useState<any>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const sharedScope = sharedScopeFromUrl();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() => {
    if (sharedScope.agentId && sharedScope.storeId) return `${sharedScope.storeId}:${sharedScope.agentId}`;
    return safeLocalStorageGet(LAST_AGENT_KEY);
  });
  // Derived from `agents` (not a separate copy) so per-agent enrichment — AIS, stake,
  // zk-boost — fetched below flows straight through to whatever holds the selection.
  const selectedAgent = agents.find(a => (a.namespace_key || a.id) === selectedAgentId) || null;
  const [layoutMode, setLayoutMode] = useState<'sidebar' | 'header'>('sidebar');
  const [theme, setTheme] = useState<'dark' | 'light' | 'cyber'>('dark');
  const [fontFamily, setFontFamily] = useState<string>('Raleway');
  const [fontSize, setFontSize] = useState<'small' | 'medium' | 'large'>('medium');
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [walletAddress, setWalletAddress] = useState<string | null>(() => safeLocalStorageGet(WALLET_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  const setSelectedAgent = useCallback((agent: Agent) => {
    const key = agent.namespace_key || agent.id;
    setSelectedAgentId(key);
    safeLocalStorageSet(LAST_AGENT_KEY, key);
    writeSharedScope(agent.id, agent.store_id || (agent.namespace_key?.startsWith(`${key.split(':')[0]}:`) ? key.split(':')[0] : ''));
  }, []);

  const addToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    console.log(`[Toast ${type}] ${message}`);
  }, []);

  // Returns whether a wallet was actually connected — callers (e.g. AuthPage's
  // handleWalletAuth) must not navigate to an authenticated route on a false return,
  // since every failure path here is handled by an addToast rather than a thrown error.
  const connectWallet = useCallback(async (): Promise<boolean> => {
    const ethereum = (window as any).ethereum;
    if (typeof ethereum === 'undefined') {
      addToast('error', 'No Ethereum wallet found');
      return false;
    }
    try {
      const accounts = await ethereum.request({ method: 'eth_requestAccounts' });
      const chainIdHex = await ethereum.request({ method: 'eth_chainId' });
      const targetHex = `0x${BASE_SEPOLIA_CHAIN_ID.toString(16)}`;
      if (chainIdHex !== targetHex) {
        try {
          await ethereum.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: targetHex }] });
        } catch (switchErr: any) {
          if (switchErr.code === 4902) {
            addToast('error', 'Add the Base Sepolia network to your wallet, then reconnect.');
          }
        }
      }
      setWalletAddress(accounts[0]);
      safeLocalStorageSet(WALLET_KEY, accounts[0]);
      return true;
    } catch (err) {
      console.error(err);
      addToast('error', 'Wallet connection failed');
      return false;
    }
  }, [addToast]);

  // Agent scope is an authorization boundary. Prefer the authenticated userapi ownership
  // projection; do not use Oracle's global directory for ordinary dashboard selection.
  // The global directory remains available only behind an explicit operator/dev flag and
  // must never be treated as proof that the current principal controls an agent.
  useEffect(() => {
    let active = true;
    setAgentsLoading(true);
    const load = async () => {
      try {
        // Cortex is the authoritative namespace projection. Its authenticated HttpOnly
        // session is shared through the same-origin /cortex-api proxy, so Dashboard can
        // mirror the exact `{store_id, agent_id}` roster even when its separate UserAPI
        // session has expired. UserAPI ownership still enriches the rows and remains the
        // authorization boundary for Dashboard-only financial mutations.
        const cortexResult = await Promise.all([
          graphMemory.agents().catch(() => null),
          graphMemory.accountMe().catch(() => null),
        ]);
        let owned: Awaited<ReturnType<typeof userapi.myAgents>> = [];
        if (getToken()) {
          [owned] = await Promise.all([
            userapi.myAgents().catch(() => []),
          ]);
        }
        if (!active) return;
        const usable = owned.filter(record => record.error === null && record.live_data !== null);
        const real = usable.map(agentFromOwnedRecord);
        const baseByDid = new Map(real.map(agent => [agent.id, agent]));
        const [cortex, cortexAccount] = cortexResult;
        // `/api/agents` is already an authenticated, account-scoped Cortex endpoint.
        // Do not require a second `/api/auth/me` round-trip: a valid roster response is
        // sufficient evidence, and the extra identity probe caused Dashboard to discard
        // a valid Cortex roster when the two cookie paths were momentarily out of sync.
        const cortexAuthenticated = Array.isArray(cortex?.agents);
        // Preserve every exact {store_id, agent_id} workspace from Cortex, including
        // read-only stores. Never collapse by DID and never merge profile stores.
        const scoped = (cortexAuthenticated ? (cortex?.agents || []) : [])
            .map(workspace => {
              const base = baseByDid.get(workspace.agent_id) || {
                id: workspace.agent_id,
                eth_address: workspace.agent_id,
                verification_tier: 0,
              };
              return {
                ...base,
                alias: workspace.agent_name || workspace.device_name || base.alias,
                store_id: workspace.store_id,
                profile_id: workspace.profile_id,
                store_access: workspace.store_access,
                writable: workspace.writable,
                namespace_key: `${workspace.store_id}:${workspace.agent_id}`,
                namespace_state: 'cortex' as const,
              };
            });
          const visible = scoped.length ? scoped : real;
          const lastId = sharedScope.agentId && sharedScope.storeId ? `${sharedScope.storeId}:${sharedScope.agentId}` : safeLocalStorageGet(LAST_AGENT_KEY);
          const restored = lastId && visible.find(a => a.namespace_key === lastId || (!a.namespace_key && a.id === lastId));
          setAgents(visible);
          setSelectedAgentId((restored || visible[0])?.namespace_key || (restored || visible[0])?.id || null);
          return;
      } catch (err) {
        console.warn('Agent scope unavailable; showing empty agent fleet', err);
        if (active) {
          setAgents([]);
          setSelectedAgentId(null);
        }
      } finally {
        if (active) setAgentsLoading(false);
      }
    };
    void load();
    const reload = () => { void load(); };
    window.addEventListener('integrity-auth-changed', reload);
    return () => {
      active = false;
      window.removeEventListener('integrity-auth-changed', reload);
    };
  }, []);

  // Refresh the selected agent's live AIS once it's chosen, so downstream cards
  // (sidebar, header) show a real current score rather than the bare summary.
  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    oracle.getAis(selectedAgent.eth_address)
      .then(ais => {
        if (!active) return;
        setAgents(prev => prev.map(a => (a.namespace_key || a.id) === (selectedAgent.namespace_key || selectedAgent.id) ? { ...a, current_ais: ais.ais, tee_verified: ais.zk_boost > 1 } : a));
      })
      .catch(() => { /* agent may not have telemetry yet — leave current_ais unset */ });
    // A DID can be present in the off-chain directory before CORE has a
    // controller/primitives binding. Do not poll an on-chain stake route for
    // that state; the resulting 404 is expected, not a browser error.
    // The unscoped directory is a read-only operator/dev view. Avoid a per-agent stake
    // fan-out there: it exhausts public RPC limits and is not an authorization signal.
    if (!selectedAgent.controller || ALLOW_UNSCOPED_AGENT_DIRECTORY) return () => { active = false; };
    oracle.getStake(selectedAgent.eth_address)
      .then(stake => {
        if (!active) return;
        // total_stake is a raw wei string off the chain (Slasher.stakes) — convert to ITK.
        setAgents(prev => prev.map(a => (a.namespace_key || a.id) === (selectedAgent.namespace_key || selectedAgent.id) ? { ...a, staked_itk: Number(ethers.formatEther(stake.total_stake)) } : a));
      })
      .catch(() => { /* no Slasher clone yet */ });
    return () => { active = false; };
  }, [selectedAgent?.namespace_key, selectedAgent?.id]);

  // Protocol-wide stats aggregated live from the real agent set (no single oracle
  // endpoint returns network-wide AIS/stake — this is derived, real aggregation,
  // not a mock; see PRODUCTION_GAPS.md).
  useEffect(() => {
    if (ALLOW_UNSCOPED_AGENT_DIRECTORY) {
      setStats(null);
      return;
    }
    if (agents.length === 0) { setStats(agentsLoading ? null : { active_nodes: 0, aggregate_ais: 0, protocol_staked_itk: 0 }); return; }
    let active = true;
    Promise.all([
      oracle.getLeaderboard().catch(() => []),
      Promise.all(agents.map(a => a.controller ? oracle.getStake(a.eth_address).catch(() => null) : Promise.resolve(null))),
    ]).then(([leaderboard, stakes]) => {
      if (!active) return;
      const scores = leaderboard.map(e => Number(e.effective_score)).filter(n => !Number.isNaN(n));
      const aggregate_ais = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
      const protocol_staked_itk = stakes.reduce((sum, s) => sum + (s ? Number(ethers.formatEther(s.total_stake)) : 0), 0);
      setStats({ active_nodes: agents.length, aggregate_ais, protocol_staked_itk });
    });
    return () => { active = false; };
  }, [agents.length, agentsLoading]);

  // Real user identity: prefer a userapi session (email/password auth), fall back to
  // a wallet-derived view model. No fabricated name/email when neither is present.
  useEffect(() => {
    let active = true;
    const load = () => {
      // Always attempts the cookie-authenticated bootstrap, regardless of this tab's local
      // "authed" marker: the marker is per-tab sessionStorage, but the real credential is a
      // cookie shared across every tab, so a freshly opened tab must still be able to pick up
      // an existing session. A missing/expired cookie just 401s and falls back below.
      userapi.meIfSignedIn()
        .then(u => { if (active) setUser(u ? userFromResponse(u) : (walletAddress ? userFromWallet(walletAddress) : null)); });
    };
    load();
    window.addEventListener('integrity-auth-changed', load);
    return () => { active = false; window.removeEventListener('integrity-auth-changed', load); };
  }, [walletAddress]);

  // Revokes the session server-side and clears the local marker; the 'integrity-auth-changed'
  // listener above then re-runs and drops `user` back to a wallet-derived view (or null).
  const signOut = useCallback(async () => { await userapi.logout(); }, []);

  // Real API keys from userapi (requires a session — see AuthPage).
  useEffect(() => {
    if (!getToken()) { setApiKeys([]); return; }
    userapi.listApiKeys()
      .then(keys => setApiKeys(keys.map(k => ({
        id: k.id,
        name: `Key ${k.id.substring(0, 8)}`,
        key: `xib_****${k.id.slice(-4)}`,
        permissions: 'Read/Write' as const,
        expiresAt: k.revoked_at,
      }))))
      .catch(() => setApiKeys([]));
  }, [user]);

  // Theme & Typography side-effects
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.style.setProperty('font-family', `'${fontFamily}', sans-serif`);
    if (fontSize === 'small') document.body.style.fontSize = '14px';
    else if (fontSize === 'large') document.body.style.fontSize = '18px';
    else document.body.style.fontSize = '16px';
  }, [theme, fontFamily, fontSize]);

  return (
    <DashboardContext.Provider value={{
      activeTrace, setActiveTrace,
      selectedSpanId, setSelectedSpanId,
      selectedAgent, setSelectedAgent, selectAgent: setSelectedAgent,
      agents, agentsLoading,
      layoutMode, setLayoutMode,
      theme, setTheme,
      fontFamily, setFontFamily,
      fontSize, setFontSize,
      apiKeys, setApiKeys,
      user, signOut,
      walletAddress, connectWallet, addToast,
      stats,
    }}>
      {children}
    </DashboardContext.Provider>
  );
};

export const useDashboard = () => {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider');
  return ctx;
};
