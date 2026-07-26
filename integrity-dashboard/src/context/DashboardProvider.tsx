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
import { auth } from '../firebase';
import { onAuthStateChanged, signOut as firebaseSignOut } from 'firebase/auth';
import type { UserResponse } from '../services/userapi';

// Maps the real oracle DTOs (DID-keyed AgentSummary + AisResponse) onto the
// legacy dashboard `Agent` shape the UI renders. The new system has no agent
// "name" field (the DID fingerprint IS the identity), so the alias is derived
// from the DID exactly as integrity-dashboard's AgentContext does. `eth_address` is
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
    alias: summary.name || `Agent ${summary.id.slice(-8)}`,
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

// Single source of truth for tab-deep-linking. MUST match the union of every tab App.tsx
// routes to a page (see DashboardShell's is<Page> checks) — previously two duplicated inline
// lists that had both drifted, omitting `shield`/`cognition`/`reasoning`/`diagnostics`/`oracle`
// (so deep-linking `#/integrity#shield` was silently rejected and stayed on the wrong page)
// while listing dead tabs (`advanced`/`profile`/`settings`) no page renders.
const VALID_TABS: TabId[] = [
  'telemetry',                                   // Intelligence
  'cognition', 'reasoning', 'diagnostics',       // Cognition
  'wallet', 'staking', 'credit', 'markets', 'stability', // Finance
  'factory', 'zk', 'oracle', 'ledger',           // Contracts
  'governance', 'compliance', 'shield', 'quarantine',    // Shield
  'identity', 'apikeys',                         // Identity
];

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentAddr, setSelectedAgentAddr] = useState<string | null>(null);
  const [stats, setStats] = useState<ProtocolStats | null>(null);
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [walletBalance, setWalletBalance] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [user, setUser] = useState<UserResponse | null>(null);
  
  const toastCounter = useRef(0);
  
  // Resolve initial tab from URL hash (e.g. #/integrity#compliance)
  const getInitialTab = (): TabId => {
    const hash = window.location.hash;
    const parts = hash.split('#');
    const candidate = (parts[parts.length - 1] || '').replace(/^\//, '') as TabId;
    if (VALID_TABS.includes(candidate)) {
      return candidate;
    }
    return 'telemetry';
  };

  const [activeTab, setActiveTabInternal] = useState<TabId>(getInitialTab);

  const setActiveTab = useCallback((tab: TabId) => {
    setActiveTabInternal(tab);
    // Update hash to keep E2E tests in sync
    const currentHash = window.location.hash;
    const parts = currentHash.split('#');
    if (parts.length >= 2) {
      // Retain the router path (e.g., /integrity) and append #tab
      window.location.hash = `#${parts[1].split('?')[0]}#${tab}`;
    } else {
      window.location.hash = `#/integrity#${tab}`;
    }
  }, []);

  useEffect(() => {
    (window as any).__setActiveTab = (tab: any) => {
      setActiveTab(tab);
    };

    const handleHashChange = () => {
      const hash = window.location.hash;
      const parts = hash.split('#');
      const candidate = (parts[parts.length - 1] || '').replace(/^\//, '') as TabId;
      if (VALID_TABS.includes(candidate)) {
        setActiveTabInternal(candidate);
      }
    };


    window.addEventListener('hashchange', handleHashChange);
    return () => {
      window.removeEventListener('hashchange', handleHashChange);
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

  const signIn = useCallback(async (email: string, password: string) => {
    // Left empty, logic moved to AuthPage.tsx
  }, [addToast]);

  const signUp = useCallback(async (email: string, password: string) => {
    // Left empty, logic moved to AuthPage.tsx
  }, [addToast]);

  const signOut = useCallback(async () => {
    await firebaseSignOut(auth);
    addToast('info', 'Signed out');
  }, [addToast]);

  useEffect(() => {
    const savedWallet = localStorage.getItem('integrity_wallet_connected');
    if (savedWallet) {
      setWalletAddress(savedWallet);
    }
  }, []);

  useEffect(() => {
    const mockUser = localStorage.getItem('firebase:mock_user');
    if (mockUser) {
      setUser(JSON.parse(mockUser));
      return;
    }

    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      if (firebaseUser) {
        setUser({
          id: firebaseUser.uid,
          email: firebaseUser.email || '',
          created_at: firebaseUser.metadata.creationTime || new Date().toISOString(),
          name: firebaseUser.displayName || undefined,
          photoURL: firebaseUser.photoURL || undefined
        });
      } else {
        setUser(null);
      }
    });
    return () => unsubscribe();
  }, []);

  const fetchData = useCallback(async () => {
    try {
      // Real agent list from the oracle (DID-keyed; mock/seeded agents are gated
      // server-side by the mock_mode flag, not client-side). AIS is per-agent, so fetch each agent's
      // real score; a per-agent AIS failure degrades only that agent's scores
      // to 0 (it still lists) rather than failing the whole load.
      const summaries = await oracle.listAgents();
      // Accumulate protocol-wide open disputes as we already iterate each agent's
      // stake (Slashers are per-agent clones with no singleton dispute index, so
      // summing StakeDto.open_disputes here is the zero-extra-fan-out way to a real
      // `active_disputes` — see docs/design/dashboard-wiring.md).
      let openDisputes = 0;
      const allAgents: Agent[] = await Promise.all(
        summaries.map(async (s) => {
          // Real AIS + real on-chain stake, in parallel. Either failing degrades
          // only that field (scores 0 / stake 0), never the whole load.
          const [ais, stake] = await Promise.all([
            oracle.getAis(s.id).catch(() => null),
            oracle.getStake(s.id).catch(() => null),
          ]);
          const agent = mapOracleAgent(s, ais);
          if (stake) {
            agent.staked_itk = Number(stake.total_stake) / 1e18;
            openDisputes += stake.open_disputes || 0;
          }
          return agent;
        }),
      );

      // Protocol-wide singleton aggregates the per-agent loop can't derive
      // (marketplace volume + capital-pool totals). Best-effort: a failure leaves
      // these at 0 rather than failing the whole load.
      const protocolStats = await oracle.getStats().catch(() => null);

      // The selected agent's real deployed contracts = its on-chain primitive
      // set (getAgent().primitives). Fetched only for the focused agent (like
      // the old per-selected credit fetch) to avoid N registry round-trips.
      const currentAddr = selectedAgentAddr || (allAgents.length > 0 ? allAgents[0].eth_address : null);
      if (currentAddr) {
        try {
          const [detail, credit] = await Promise.all([
            oracle.getAgent(currentAddr).catch(() => null),
            oracle.getCredit(currentAddr).catch(() => null),
          ]);
          const idx = allAgents.findIndex((a) => a.eth_address === currentAddr);
          if (idx >= 0) {
            const patch: Partial<Agent> = {};
            if (detail?.primitives) {
              patch.owned_contracts = primitivesToContracts(detail.primitives, allAgents[idx].registered_at);
            }
            if (credit) {
              // Map the real A2ACapitalPool position onto the panel's credit shape.
              // Escrowed = the agent's live available capital line; released =
              // disbursed ("borrowed"); clawed-back = returned ("repaid"). No real
              // credit-score / per-loan detail exists in the aggregate, so those
              // stay 0 / empty rather than fabricated.
              patch.credit_profile = {
                credit_score: 0,
                max_borrow_limit: Number(credit.escrowed) / 1e18,
                active_loans: [],
                total_borrowed: Number(credit.released) / 1e18,
                total_repaid: Number(credit.clawed_back) / 1e18,
                default_count: 0,
              };
            }
            allAgents[idx] = { ...allAgents[idx], ...patch };
          }
        } catch {
          /* agent detail unresolved (not fully registered) — leave enrichments unset */
        }
      }

      setAgents(allAgents);
      setIsBackendOffline(false);

      // Protocol stats: every field now real. The client-derivable ones
      // (nodes/AIS/stake/contracts/disputes) come from the per-agent loop above; the
      // singleton aggregates (market volume, capital pool) come from /v1/stats. TVL
      // is composed here — protocol stake + escrowed credit + market volume — so
      // stake has exactly one source of truth (docs/design/dashboard-wiring.md).
      const aggregate_ais = allAgents.length
        ? Math.round(allAgents.reduce((sum, a) => sum + a.current_ais, 0) / allAgents.length)
        : 0;
      const protocol_staked_itk = allAgents.reduce((sum, a) => sum + (a.staked_itk || 0), 0);
      const escrowed_credit = protocolStats ? Number(protocolStats.escrowed_credit) / 1e18 : 0;
      const total_marketplace_volume = protocolStats ? Number(protocolStats.total_marketplace_volume) / 1e18 : 0;
      const total_loans_volume = protocolStats ? Number(protocolStats.released_credit) / 1e18 : 0;
      setStats({
        active_nodes: allAgents.length,
        aggregate_ais,
        protocol_staked_itk,
        active_disputes: openDisputes,
        // Each registered agent owns its 7 primitive contracts (real deployed
        // clones); the protocol total is that count. Markets/other contracts
        // would add to this once their count endpoint exists.
        total_contracts: allAgents.length * PRIMITIVE_CONTRACTS.length,
        total_loans_volume,
        total_marketplace_volume,
        tvl: protocol_staked_itk + escrowed_credit + total_marketplace_volume,
      });

      if (!selectedAgentAddr && allAgents.length > 0) {
        setSelectedAgentAddr(allAgents[0].eth_address);
      }
    } catch (err) {
      console.error('fetchData failed:', err);
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
      signIn,
      signUp,
      signOut,
      fetchData,
      addToast,
      removeToast
    }}>
      {children}
    </DashboardContext.Provider>
  );
}
