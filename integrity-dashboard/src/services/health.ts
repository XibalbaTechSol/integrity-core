import { useEffect, useState } from 'react';
import { ethers } from 'ethers';
import { BCC_MIDDLEWARE_URL, GRAPH_MEMORY_URL, ORACLE_URL, SHIELD_BACKEND_URL } from '../config';
import { RPC_URL } from '../constants';

// Lifted out of AppHeader.tsx (which used this inline) so the Guided System Test wizard
// (Developer page) can share one source of truth for "is this service actually reachable"
// instead of duplicating the fetch+timeout logic. Oracle's /healthz is a documented no-op
// (see PRODUCTION_GAPS.md -- the project's own Docker healthcheck avoids it too), so this
// intentionally does NOT probe it; a real DB-touching endpoint would be a better choice if
// oracle's own health semantics ever change, but that's a separate decision from this hook.
export type ServiceState = 'checking' | 'online' | 'offline';

export interface ServiceCheck {
  key: string;
  label: string;
  status: ServiceState;
  detail?: string;
}

const httpChecks = [
  { key: 'oracle', label: 'Oracle', url: `${ORACLE_URL}/healthz`, fixHint: `Oracle not reachable at ${ORACLE_URL} -- run \`cargo run --bin oracle-backend\` in integrity-oracle/.` },
  { key: 'bcc', label: 'BCC middleware', url: `${BCC_MIDDLEWARE_URL}/health`, fixHint: `BCC middleware not reachable at ${BCC_MIDDLEWARE_URL} -- run bcc_middleware's FastAPI app (see its README).` },
  { key: 'memory', label: 'Cortex / Memory', url: `${GRAPH_MEMORY_URL}/api/status`, fixHint: `Cortex local_api not reachable at ${GRAPH_MEMORY_URL} -- run \`python -m xibalba_cortex.local_api --home ~/.hermes/xibalba-cortex\` in xibalba-cortex/.` },
  { key: 'shield', label: 'Shield', url: `${SHIELD_BACKEND_URL}/api/shield/health`, fixHint: `Shield backend not reachable at ${SHIELD_BACKEND_URL} -- run \`python -m shield.backend.api --admin-token dev-shield-admin\` in xibalba-shield/.` },
] as const;

const KERNEL_FIX_HINT = `Anvil RPC not reachable at ${RPC_URL} -- run \`make chain\` in integrity-core/, then deploy the kernel-bridge testbed (contracts/script/DeployKernelBridgeTestbed.s.sol).`;

async function checkHttp(url: string): Promise<ServiceState> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2500) });
    return response.ok ? 'online' : 'offline';
  } catch {
    return 'offline';
  }
}

async function checkKernelRpc(): Promise<ServiceState> {
  try {
    const provider = new ethers.JsonRpcProvider(RPC_URL);
    await provider.getBlockNumber();
    return 'online';
  } catch {
    return 'offline';
  }
}

export function useServiceHealth(pollIntervalMs = 15000): ServiceCheck[] {
  const [states, setStates] = useState<Record<string, ServiceState>>(() =>
    Object.fromEntries([...httpChecks.map((c) => [c.key, 'checking']), ['kernel', 'checking']]) as Record<string, ServiceState>,
  );

  useEffect(() => {
    let cancelled = false;
    const runChecks = async () => {
      const results = await Promise.all([
        ...httpChecks.map(async (c) => [c.key, await checkHttp(c.url)] as const),
        (async () => ['kernel', await checkKernelRpc()] as const)(),
      ]);
      if (!cancelled) setStates(Object.fromEntries(results));
    };
    void runChecks();
    const interval = window.setInterval(runChecks, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pollIntervalMs]);

  return [
    ...httpChecks.map((c) => ({ key: c.key, label: c.label, status: states[c.key] ?? 'checking', detail: states[c.key] === 'offline' ? c.fixHint : undefined })),
    { key: 'kernel', label: 'Kernel bridge (RPC)', status: states.kernel ?? 'checking', detail: states.kernel === 'offline' ? KERNEL_FIX_HINT : undefined },
  ];
}
