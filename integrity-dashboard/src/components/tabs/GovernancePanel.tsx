import { Panel } from '../shared/Panel';
import { Shield, ArrowRight, Settings, Scale, FileText, Info } from 'lucide-react';

// Honest gap — NOT a silent mock. There is no Governance/Proposal contract in contracts/
// (verified), so on-chain proposals and voting genuinely do not exist yet. The old panel
// fabricated all of it: hardcoded MOCK_PROPOSALS, localStorage persistence, Math.random()
// vote tallies, and api.getProposals/voteProposal/createProposal with "offline mode"
// fallbacks that faked success. Rather than simulate a DAO that isn't deployed, this panel
// now shows the real design roadmap (descriptive, clearly future) plus an explicit
// not-yet-on-chain notice. When a Governance contract ships, wire real reads/writes here.

export function GovernancePanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <Panel title="On-Chain Governance — Not Yet Live" icon={<Info size={18} />}>
        <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start', padding: 'var(--space-3)', background: 'var(--primary-dim)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-md)' }}>
          <Shield size={22} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 4 }}>No Governance contract is deployed yet.</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.55 }}>
              Proposal creation, token-weighted voting, and on-chain execution are part of the protocol's
              roadmap (below) but have no deployed contract on Base Sepolia today. This panel deliberately
              shows nothing to vote on rather than simulating proposals — consistent with the protocol's
              "no silent mocks" rule. The design it will implement is described below.
            </p>
          </div>
        </div>
      </Panel>

      <Panel title="Blueprint for Decentralized Autonomy (Roadmap)" icon={<Shield size={18} />}>
        <div className="flex-col gap-4">
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            The <strong>Xibalba Integrity Protocol</strong> plans a transition from a single-operator oracle
            model to a decentralized DAO, moving reputation criteria, dispute audits, and system parameters
            to token-holder consensus. The phases below are a <strong>planned roadmap</strong>, not a live system.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)', borderTop: '1px solid var(--glass-border)', paddingTop: '16px', marginTop: '4px' }}>
            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 800, textTransform: 'uppercase', marginBottom: 8 }}>Phase 1 — Current</div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Single-Operator Oracle</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>Protocol roles (oracle/arbitrator/disputer) held by one operator on the Base Sepolia testnet, attesting agent execution + telemetry to the on-chain ledger.</p>
            </div>
            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 800, textTransform: 'uppercase', marginBottom: 8 }}>Phase 2 — Planned</div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Hybrid Governed System</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>A Governance contract lets ITK holders vote on core economic parameters, staking thresholds, and verification delays. (Requires the contract that does not yet exist.)</p>
            </div>
            <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 800, textTransform: 'uppercase', marginBottom: 8 }}>Phase 3 — Target</div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '4px' }}>Full DAO Autonomy</div>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>ZK-verified dispute pipelines trigger DAO-arbitrated slashing and parameter changes with no privileged operator.</p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-4)', marginTop: 'var(--space-2)' }}>
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--glass-border)', padding: '16px', borderRadius: 'var(--radius-md)', display: 'flex', gap: '12px' }}>
              <div style={{ color: 'var(--primary)', marginTop: '2px' }}><Settings size={20} /></div>
              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Decentralized Parameter Adjustment</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  Would let token-holders vote on variables such as minimum ITK stake, the liquidation ratio, and telemetry weights.
                </p>
              </div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--glass-border)', padding: '16px', borderRadius: 'var(--radius-md)', display: 'flex', gap: '12px' }}>
              <div style={{ color: 'var(--success)', marginTop: '2px' }}><Scale size={20} /></div>
              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>Decentralized Dispute Mitigation</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  Would replace operator scoring overrides with a collateral-weighted validation game — the existing per-agent Slasher is the real primitive this builds on.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Planned Proposal Execution Pipeline" icon={<FileText size={18} />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            The intended lifecycle once a Governance contract is deployed — shown as design, not an active pipeline.
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-secondary)', padding: '16px 24px', borderRadius: 'var(--radius-md)', border: '1px solid var(--glass-border)', overflowX: 'auto' }}>
            {[
              ['1', 'Draft Check', 'Requires ITK stake'],
              ['2', 'Active Voting', 'Fixed window | quorum'],
              ['3', 'Timelock Queue', 'Execution cooldown'],
              ['4', 'Settled Execution', 'On-chain state commit'],
            ].map(([n, title, sub], i, arr) => (
              <div key={n} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
                  <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>{n}</div>
                  <div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>{title}</div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{sub}</div>
                  </div>
                </div>
                {i < arr.length - 1 && <ArrowRight size={14} className="text-muted" />}
              </div>
            ))}
          </div>
        </div>
      </Panel>
    </div>
  );
}
