import { useEffect, useRef } from 'react';
import { useDashboard } from '../context/DashboardContext';

// Pages like Health and Quant demonstrate the protocol through one specific,
// dedicated agent identity (not whichever agent happens to be globally
// selected elsewhere in the dashboard). This pins the sidebar's Active Agent
// to that DID once (as soon as it's loaded into `agents`), and restores
// whatever was selected before on unmount -- so leaving /quant back to
// /dashboard doesn't strand the user on an agent they never chose.
//
// Deliberately pins only once per mount (not on every `agents` refresh --
// DashboardContext's AIS/stake polling replaces the `agents` array on an
// interval, which would otherwise re-trigger this on every tick and fight
// the user if they manually switch agents while on the page).
export function usePinnedAgent(agentId: string) {
  const { agents, selectedAgent, setSelectedAgent } = useDashboard();
  const hasPinnedRef = useRef(false);
  const previousIdRef = useRef<string | null>(null);
  const stateRef = useRef({ agents, selectedAgent, setSelectedAgent });
  stateRef.current = { agents, selectedAgent, setSelectedAgent };

  useEffect(() => {
    if (hasPinnedRef.current) return;
    const target = agents.find(a => a.id === agentId);
    if (!target) return; // not loaded yet, or not registered -- nothing to pin to

    hasPinnedRef.current = true;
    previousIdRef.current = selectedAgent?.id ?? null;
    if (selectedAgent?.id !== agentId) setSelectedAgent(target);
  }, [agentId, agents, selectedAgent, setSelectedAgent]);

  useEffect(() => {
    return () => {
      if (!hasPinnedRef.current) return;
      const { agents: currentAgents, setSelectedAgent: currentSet } = stateRef.current;
      const restoreId = previousIdRef.current;
      const restoreTo = restoreId ? currentAgents.find(a => a.id === restoreId) : null;
      if (restoreTo) currentSet(restoreTo);
    };
  }, []);
}
