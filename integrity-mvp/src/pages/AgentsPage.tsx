import { Users, Activity, ShieldCheck, Database, Link, Terminal } from 'lucide-react';
import { TopBar } from '../components/TopBar';
import { useState, useMemo, useEffect } from 'react';
import { NotionDatabase } from '../components/NotionDatabase';
import { createColumnHelper } from '@tanstack/react-table';
import { oracle, type AgentSummary } from '../services/oracle';
import { ClaimAgentModal } from '../components/ClaimAgentModal';
import { RegisterAgentModal } from '../components/RegisterAgentModal';

interface AgentRow extends AgentSummary {
  ais: number | null;
}

const TIER_LABELS: Record<number, string> = { 0: 'UNVERIFIED', 1: 'SOVEREIGN', 2: 'LINKED', 3: 'INSTITUTIONAL' };

export const AgentsPage = () => {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [claimAddress, setClaimAddress] = useState('');
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [operatingEnclave, setOperatingEnclave] = useState('AWS Nitro Enclave');
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);

  const refetchAgents = async () => {
    try {
      const summaries = await oracle.listAgents();
      const withAis = await Promise.all(
        summaries.map(async (agent) => {
          const ais = await oracle.getAis(agent.id).then(r => r.ais).catch(() => null);
          return { ...agent, ais };
        }),
      );
      setAgents(withAis);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Failed to reach the oracle');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refetchAgents();
  }, []);

  const avgAis = useMemo(() => {
    const scored = agents.filter((a): a is AgentRow & { ais: number } => a.ais !== null);
    if (!scored.length) return null;
    return Math.round(scored.reduce((sum, a) => sum + a.ais, 0) / scored.length);
  }, [agents]);

  // NotionDatabase Columns
  const columnHelper = createColumnHelper<AgentRow>();
  const columns = useMemo(() => [
    columnHelper.accessor('id', {
      header: 'Identifier (DID)',
      cell: info => <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}><ShieldCheck size={16} color="var(--success)" />{info.getValue()}</div>,
      size: 320,
    }),
    columnHelper.accessor('verification_tier', {
      header: 'Verification Tier',
      cell: info => <span className={`badge ${info.getValue() >= 1 ? 'badge-success' : 'badge-warning'}`}>{TIER_LABELS[info.getValue()] ?? `TIER ${info.getValue()}`}</span>,
      size: 160,
    }),
    columnHelper.accessor('ais', {
      header: 'AIS Score',
      cell: info => {
        const v = info.getValue();
        return v === null
          ? <span style={{ color: 'var(--text-muted)' }}>—</span>
          : <span style={{ fontWeight: 600, color: v > 700 ? 'var(--success)' : 'var(--danger)' }}>{Math.round(v)}</span>;
      },
      size: 120,
    }),
    columnHelper.accessor('created_at', {
      header: 'Registered',
      cell: info => <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{new Date(info.getValue()).toLocaleDateString()}</span>,
      size: 150,
    }),
  ], [columnHelper]);

  return (
    <div className="main-content" style={{ display: 'flex', flexDirection: 'column', height: '100vh', position: 'relative' }}>
      <TopBar title="Agent Fleet Management">
        {loadError && (
          <div style={{ padding: '6px 12px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid var(--danger)', borderRadius: '6px', color: 'var(--danger)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={14} /> <span><strong>Sync Failed:</strong> {loadError}</span>
          </div>
        )}
      </TopBar>

      <div className="page-content" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px', flexShrink: 0 }}>
          {/* Register Agent Card */}
          <div className="card glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
              <div style={{ width: '40px', height: '40px', background: 'rgba(212, 175, 55, 0.1)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Users size={20} color="var(--gold)" />
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-primary)' }}>Register New Agent</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Deploy primitives to Base L2</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '16px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Agent Name</label>
                <input
                  type="text"
                  className="input-field"
                  placeholder="e.g. Clinical Auditor v3"
                  value={agentName}
                  onChange={e => setAgentName(e.target.value)}
                  style={{ width: '100%', background: 'var(--bg-main)' }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Operating Enclave</label>
                <select
                  className="input-field"
                  value={operatingEnclave}
                  onChange={e => setOperatingEnclave(e.target.value)}
                  style={{ width: '100%', background: 'var(--bg-main)', color: 'var(--text-primary)' }}
                >
                  <option value="AWS Nitro Enclave">AWS Nitro Enclave</option>
                  <option value="Azure Confidential VM">Azure Confidential VM</option>
                  <option value="GCP TDX">GCP TDX</option>
                </select>
              </div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid var(--primary)', borderRadius: '8px', display: 'flex', gap: '12px', marginTop: '8px', alignItems: 'center' }}>
              <Terminal size={20} color="var(--primary)" />
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5, flex: 1 }}>
                This will deploy the 5 Agent Primitives via <code style={{ color: 'var(--primary)' }}>AgentPrimitivesFactory.sol</code> on Base L2.
              </div>
              <button
                className="btn btn-primary"
                style={{ padding: '8px 16px', whiteSpace: 'nowrap' }}
                onClick={() => setIsRegisterModalOpen(true)}
              >
                Deploy
              </button>
            </div>
          </div>

          {/* Claim Agent Card */}
          <div className="card glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
              <div style={{ width: '40px', height: '40px', background: 'hsla(var(--bg-panel-hsl) / 0.8)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-color)' }}>
                <Link size={20} color="var(--text-primary)" />
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-primary)' }}>Claim Existing Agent</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Connect an existing SovereignAgent contract</div>
              </div>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Agent Contract Address (Base L2)</label>
              <input
                type="text"
                className="input-field"
                placeholder="0x..."
                value={claimAddress}
                onChange={e => setClaimAddress(e.target.value)}
                style={{ width: '100%', background: 'var(--bg-main)' }}
              />
            </div>
            <div style={{ padding: '16px', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '8px', display: 'flex', gap: '12px', marginTop: '8px', alignItems: 'center' }}>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5, flex: 1 }}>
                You must hold the admin key.
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: '8px 16px', background: 'white', color: 'black', whiteSpace: 'nowrap' }}
                onClick={() => setIsClaimModalOpen(true)}
              >
                Verify & Claim
              </button>
            </div>
          </div>
        </div>

        <ClaimAgentModal
          isOpen={isClaimModalOpen}
          defaultAddress={claimAddress}
          onClose={() => setIsClaimModalOpen(false)}
          onSuccess={() => { setIsClaimModalOpen(false); refetchAgents(); }}
        />
        <RegisterAgentModal
          isOpen={isRegisterModalOpen}
          initialAlias={agentName}
          initialVertical={agentName.toLowerCase().includes('clinical') ? 1 : 0}
          onClose={() => setIsRegisterModalOpen(false)}
          onSuccess={() => { setIsRegisterModalOpen(false); refetchAgents(); }}
        />
        <div className="grid grid-3 mb-6" style={{ flexShrink: 0, gap: '24px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', padding: '24px', background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '16px', position: 'relative', overflow: 'hidden', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: 'var(--gold)' }}></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, margin: 0 }}>Registered Agents</h3>
              <Database size={18} color="var(--gold)" opacity={0.8} />
            </div>
            <div style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', fontFamily: 'var(--font-mono)' }}>
              {isLoading ? '—' : agents.length}
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Live from <code style={{color: 'var(--text-primary)'}}>GET /v1/agents</code></div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', padding: '24px', background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '16px', position: 'relative', overflow: 'hidden', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: 'var(--success)' }}></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, margin: 0 }}>Verified Agents</h3>
              <Activity size={18} color="var(--success)" opacity={0.8} />
            </div>
            <div style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', fontFamily: 'var(--font-mono)' }}>
              {isLoading ? '—' : agents.filter(a => a.verification_tier >= 1).length}
              <span style={{ fontSize: '1.2rem', color: 'var(--text-muted)' }}> / {agents.length}</span>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tier ≥ 1 (Sovereign+)</div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', padding: '24px', background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '16px', position: 'relative', overflow: 'hidden', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: 'var(--accent-primary)' }}></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, margin: 0 }}>Avg Network AIS</h3>
              <ShieldCheck size={18} color="var(--accent-primary)" opacity={0.8} />
            </div>
            <div style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--accent-primary)', marginBottom: '8px', fontFamily: 'var(--font-mono)' }}>
              {avgAis ?? '—'}
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Across scored agents</div>
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          <NotionDatabase
            title="Deployed Agents Database"
            data={agents}
            columns={columns}
            readOnly={true}
          />
        </div>
      </div>


    </div>
  );
};
