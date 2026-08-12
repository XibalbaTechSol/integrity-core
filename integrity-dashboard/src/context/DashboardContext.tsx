import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { ethers } from 'ethers';
import { oracle, AgentSummary } from '../services/oracle';
import { userapi, getToken, UserResponse } from '../services/userapi';
import { BASE_SEPOLIA_CHAIN_ID } from '../constants';

export interface Agent {
  /** The agent's DID — historically named `eth_address` across this codebase (see
   *  oracle.ts's resolveSovereignAgent comment); never use this as an on-chain
   *  address, resolve the real SovereignAgent via oracle.resolveSovereignAgent(id). */
  id: string;
  eth_address: string;
  name?: string | null;
  alias?: string | null;
  verification_tier: number;
  current_ais?: number;
  staked_itk?: number;
  tee_verified?: boolean;
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
  walletAddress: string | null;
  connectWallet: () => void;
  addToast: (type: 'success' | 'error' | 'info', message: string) => void;
  stats: Stats | null;
}

const LAST_AGENT_KEY = 'integrity_mvp_last_agent';
const WALLET_KEY = 'integrity_wallet_connected';

function agentFromSummary(s: AgentSummary): Agent {
  return {
    id: s.id,
    eth_address: s.id,
    name: s.name ?? null,
    alias: s.handle ?? s.name ?? null,
    verification_tier: s.verification_tier,
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
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  // Derived from `agents` (not a separate copy) so per-agent enrichment — AIS, stake,
  // zk-boost — fetched below flows straight through to whatever holds the selection.
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || null;
  const [layoutMode, setLayoutMode] = useState<'sidebar' | 'header'>('sidebar');
  const [theme, setTheme] = useState<'dark' | 'light' | 'cyber'>('dark');
  const [fontFamily, setFontFamily] = useState<string>('Raleway');
  const [fontSize, setFontSize] = useState<'small' | 'medium' | 'large'>('medium');
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [walletAddress, setWalletAddress] = useState<string | null>(() => localStorage.getItem(WALLET_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  const setSelectedAgent = useCallback((agent: Agent) => {
    setSelectedAgentId(agent.id);
    localStorage.setItem(LAST_AGENT_KEY, agent.id);
  }, []);

  const addToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    console.log(`[Toast ${type}] ${message}`);
  }, []);

  const connectWallet = useCallback(async () => {
    const ethereum = (window as any).ethereum;
    if (typeof ethereum === 'undefined') {
      addToast('error', 'No Ethereum wallet found');
      return;
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
      localStorage.setItem(WALLET_KEY, accounts[0]);
    } catch (err) {
      console.error(err);
      addToast('error', 'Wallet connection failed');
    }
  }, [addToast]);

  // Load the real agent fleet from the oracle — no client-side mock filter, the oracle
  // itself gates mock/seeded agents server-side.
  useEffect(() => {
    let active = true;
    setAgentsLoading(true);
    oracle.listAgents()
      .then(summaries => {
        if (!active) return;
        const real = summaries.map(agentFromSummary);
        setAgents(real);
        const lastId = localStorage.getItem(LAST_AGENT_KEY);
        const restored = lastId && real.find(a => a.id === lastId);
        setSelectedAgentId((restored || real[0])?.id ?? null);
      })
      .catch(err => {
        console.error('Failed to load agent fleet from oracle', err);
        if (active) setAgents([]);
      })
      .finally(() => { if (active) setAgentsLoading(false); });
    return () => { active = false; };
  }, []);

  // Refresh the selected agent's live AIS once it's chosen, so downstream cards
  // (sidebar, header) show a real current score rather than the bare summary.
  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    oracle.getAis(selectedAgent.eth_address)
      .then(ais => {
        if (!active) return;
        setAgents(prev => prev.map(a => a.id === selectedAgent.id ? { ...a, current_ais: ais.ais, tee_verified: ais.zk_boost > 1 } : a));
      })
      .catch(() => { /* agent may not have telemetry yet — leave current_ais unset */ });
    oracle.getStake(selectedAgent.eth_address)
      .then(stake => {
        if (!active) return;
        // total_stake is a raw wei string off the chain (Slasher.stakes) — convert to ITK.
        setAgents(prev => prev.map(a => a.id === selectedAgent.id ? { ...a, staked_itk: Number(ethers.formatEther(stake.total_stake)) } : a));
      })
      .catch(() => { /* no Slasher clone yet */ });
    return () => { active = false; };
  }, [selectedAgent?.id]);

  // Protocol-wide stats aggregated live from the real agent set (no single oracle
  // endpoint returns network-wide AIS/stake — this is derived, real aggregation,
  // not a mock; see PRODUCTION_GAPS.md).
  useEffect(() => {
    if (agents.length === 0) { setStats(agentsLoading ? null : { active_nodes: 0, aggregate_ais: 0, protocol_staked_itk: 0 }); return; }
    let active = true;
    Promise.all([
      oracle.getLeaderboard().catch(() => []),
      Promise.all(agents.map(a => oracle.getStake(a.eth_address).catch(() => null))),
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
      if (getToken()) {
        userapi.me()
          .then(u => { if (active) setUser(userFromResponse(u)); })
          .catch(() => { if (active) setUser(walletAddress ? userFromWallet(walletAddress) : null); });
      } else {
        setUser(walletAddress ? userFromWallet(walletAddress) : null);
      }
    };
    load();
    window.addEventListener('integrity-auth-changed', load);
    return () => { active = false; window.removeEventListener('integrity-auth-changed', load); };
  }, [walletAddress]);

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
      user,
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
