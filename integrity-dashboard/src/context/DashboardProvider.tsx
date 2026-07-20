import { useState, useEffect, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';
import { oracle, type AgentSummary, type AisResponse, type PrimitiveSetDto } from '../services/oracle';
import type { Agent, ContractType, OwnedContract, ProtocolStats, TabId } from '../types';

// The agent's real deployed contracts in this protocol ARE its primitive set
// (resolved on-chain via XibalbaAgentRegistry, returned by getAgent().primitives).
// Map each non-zero primitive address to an OwnedContract labeled by its type.
// Financial fields (revenue/collateral) have no source and stay 0 — real address,
// honest zeros, never fabricated.
const PRIMITIVE_CONTRACTS: { key: keyof PrimitiveSetDto; type: ContractType }[] = [
  { key: 'sovereign_agent', type: 'SovereignAgent' },
  { key: 'state_anchor', type: 'StateAnchor' },
  { key: 'reputation_registry', type: 'ReputationRegistry' },
  { key: 'slasher', type: 'Slasher' },
  { key: 'verifier_registry', type: 'VerifierRegistry' },
  { key: 'compliance_gate', type: 'ComplianceGate' },
  { key: 'agent_profile', type: 'AgentProfile' },
];
function primitivesToContracts(p: PrimitiveSetDto, deployedAt: string): OwnedContract[] {
  return PRIMITIVE_CONTRACTS.filter((l) => p[l.key] && !/^0x0+$/i.test(p[l.key])).map((l) => ({
    contract_address: p[l.key],
    contract_type: l.type,
    deployed_at: deployedAt,
    chain: 'Base Sepolia',
    revenue_generated: 0,
    collateral_value: 0,
    is_collateralized: false,
    claim_type: 'deployed',
    status: 'active',
  }));
}
import { DashboardContext } from './useDashboard';
import type { ToastMessage } from './useDashboard';
import { auth, googleProvider } from '../firebase';
import { signInWithPopup, signOut as firebaseSignOut } from 'firebase/auth';

// Maps the real oracle DTOs (DID-keyed AgentSummary + AisResponse) onto the
// legacy dashboard `Agent` shape the UI renders. The new system has no agent
// "name" field (the DID fingerprint IS the identity), so the alias is derived
// from the DID exactly as integrity-mvp's AgentContext does. `eth_address` is
// keyed to the DID here — the UI selects/keys agents on it, and the real
// on-chain address is resolved later via getAgent().primitives (Class B/C
// wiring, see docs/design/dashboard-wiring.md). Fields with no oracle source
// yet (staked_itk, credit, contracts) are left at neutral defaults until their
// Class B read endpoints exist — real-or-absent, never fabricated.
function mapOracleAgent(summary: AgentSummary, ais: AisResponse | null): Agent {
  const c = ais?.components;
  return {
    agent_id: summary.id,
    eth_address: summary.id,
    alias: `Agent ${summary.id.slice(-8)}`,
    model_class: 'unknown',
    current_ais: ais?.ais ?? 0,
    verification_tier: summary.verification_tier,
    compliance_score: c?.compliance ?? 0,
    entropy_score: c?.entropy ?? 0,
    grounding_score: c?.grounding ?? 0,
    sacrifice_score: c?.sacrifice ?? 0,
    tee_verified: ais?.zk_proof_verified ?? false,
    staked_itk: 0,
    registered_at: summary.created_at,
    last_active: summary.created_at,
  };
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentAddr, setSelectedAgentAddr] = useState<string | null>(null);
  const [stats, setStats] = useState<ProtocolStats | null>(null);
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [walletBalance, setWalletBalance] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [user, setUser] = useState<any>(null);
  
  const toastCounter = useRef(0);
  
  const [activeTab, setActiveTab] = useState<TabId>('telemetry');

  useEffect(() => {
    (window as any).__setActiveTab = (tab: any) => {
      setActiveTab(tab);
    };
  }, [setActiveTab]);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const addToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    toastCounter.current += 1;
    const id = `toast_${toastCounter.current}`;
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => removeToast(id), 5000);
  }, [removeToast]);

  const connectWallet = useCallback(async () => {
    const ethereum = (window as Window & typeof globalThis & { ethereum?: any }).ethereum;
    if (ethereum) {
      try {
        const accounts = await ethereum.request({ method: 'eth_requestAccounts' });
        if (accounts.length > 0) {
          // Switch to Base Sepolia if not already on it
          const chainId = await ethereum.request({ method: 'eth_chainId' });
          if (parseInt(chainId, 16) !== 84532) {
            try {
              await ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: '0x14a34' }], // 84532 in hex
              });
            } catch (switchError: any) {
              // This error code indicates that the chain has not been added to MetaMask.
              if (switchError.code === 4902) {
                await ethereum.request({
                  method: 'wallet_addEthereumChain',
                  params: [
                    {
                      chainId: '0x14a34',
                      chainName: 'Base Sepolia',
                      nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
                      rpcUrls: ['https://sepolia.base.org'],
                      blockExplorerUrls: ['https://sepolia.basescan.org'],
                    },
                  ],
                });
              }
            }
          }
          setWalletAddress(accounts[0]);
          localStorage.setItem('integrity_wallet_connected', accounts[0]);
          addToast('success', 'Wallet connected to Base Sepolia');
        }
      } catch (err: any) {
        addToast('error', `Wallet connection failed: ${err.message}`);
      }
    } else {
      addToast('error', 'Web3 wallet not detected');
    }
  }, [addToast]);

  const signInWithGoogle = useCallback(async () => {
    try {
      await signInWithPopup(auth, googleProvider);
      addToast('success', 'Authenticated with Google successfully');
    } catch (err: any) {
      addToast('error', `Authentication failed: ${err.message}`);
    }
  }, [addToast]);

  const signOut = useCallback(async () => {
    try {
      await firebaseSignOut(auth);
      addToast('info', 'Signed out from Google');
    } catch (err: any) {
      addToast('error', `Sign out failed: ${err.message}`);
    }
  }, [addToast]);

  useEffect(() => {
    const savedWallet = localStorage.getItem('integrity_wallet_connected');
    if (savedWallet) {
      setWalletAddress(savedWallet);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged((u) => {
      setUser(u);
    });
    return () => unsubscribe();
  }, []);

  const fetchData = useCallback(async () => {
    try {
      // Real agent list from the oracle (DID-keyed, mock-agent-* filtered out
      // by oracle.listAgents itself). AIS is per-agent, so fetch each agent's
      // real score; a per-agent AIS failure degrades only that agent's scores
      // to 0 (it still lists) rather than failing the whole load.
      const summaries = await oracle.listAgents();
      const allAgents: Agent[] = await Promise.all(
        summaries.map(async (s) => {
          // Real AIS + real on-chain stake, in parallel. Either failing degrades
          // only that field (scores 0 / stake 0), never the whole load.
          const [ais, stake] = await Promise.all([
            oracle.getAis(s.id).catch(() => null),
            oracle.getStake(s.id).catch(() => null),
          ]);
          const agent = mapOracleAgent(s, ais);
          if (stake) agent.staked_itk = Number(stake.total_stake) / 1e18;
          return agent;
        }),
      );

      // The selected agent's real deployed contracts = its on-chain primitive
      // set (getAgent().primitives). Fetched only for the focused agent (like
      // the old per-selected credit fetch) to avoid N registry round-trips.
      const currentAddr = selectedAgentAddr || (allAgents.length > 0 ? allAgents[0].eth_address : null);
      if (currentAddr) {
        try {
          const detail = await oracle.getAgent(currentAddr);
          const idx = allAgents.findIndex((a) => a.eth_address === currentAddr);
          if (detail.primitives && idx >= 0) {
            allAgents[idx] = {
              ...allAgents[idx],
              owned_contracts: primitivesToContracts(detail.primitives, allAgents[idx].registered_at),
            };
          }
        } catch {
          /* primitives unresolved (agent not fully registered) — leave unset */
        }
      }

      setAgents(allAgents);
      setIsBackendOffline(false);

      // Protocol stats derivable from the real agent set. Fields with no oracle
      // source yet (stake, disputes, contracts, loan/market volume, TVL) stay 0
      // until their Class B read endpoints exist (docs/design/dashboard-wiring.md)
      // -- shown as zero, never fabricated.
      const aggregate_ais = allAgents.length
        ? Math.round(allAgents.reduce((sum, a) => sum + a.current_ais, 0) / allAgents.length)
        : 0;
      setStats({
        active_nodes: allAgents.length,
        aggregate_ais,
        protocol_staked_itk: allAgents.reduce((sum, a) => sum + (a.staked_itk || 0), 0),
        active_disputes: 0,
        // Each registered agent owns its 7 primitive contracts (real deployed
        // clones); the protocol total is that count. Markets/other contracts
        // would add to this once their count endpoint exists.
        total_contracts: allAgents.length * PRIMITIVE_CONTRACTS.length,
        total_loans_volume: 0,
        total_marketplace_volume: 0,
        tvl: 0,
      });

      if (!selectedAgentAddr && allAgents.length > 0) {
        setSelectedAgentAddr(allAgents[0].eth_address);
      }
    } catch {
      setIsBackendOffline(true);
    } finally {
      setIsLoading(false);
    }
  }, [selectedAgentAddr]);


  useEffect(() => {
    let mounted = true;
    const load = async () => {
       setIsLoading(true);
       await fetchData();
       if (!mounted) return;
    };
    load();
    const interval = setInterval(fetchData, 15000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [fetchData]);

  const selectedAgent = agents.find(a => a.eth_address === selectedAgentAddr) || null;

  return (
    <DashboardContext.Provider value={{
      agents,
      selectedAgent,
      stats,
      walletAddress,
      walletBalance,
      activeTab,
      isLoading,
      isBackendOffline,
      toasts,
      user,
      selectAgent: setSelectedAgentAddr,
      setActiveTab,
      connectWallet,
      signInWithGoogle,
      signOut,
      fetchData,
      addToast,
      removeToast
    }}>
      {children}
    </DashboardContext.Provider>
  );
}
