import { useEffect, useState } from 'react';
import { ethers } from 'ethers';
import { Panel } from '../shared/Panel';
import { Shield, ArrowRight, Settings, Scale, FileText, Info, CheckCircle, Loader2 } from 'lucide-react';
import { oracle, type ProposalDto } from '../../services/oracle';
import { useDashboard } from '../../context/useDashboard';
import { GOVERNANCE_ADDRESS, ITK_TOKEN_ADDRESS } from '../../constants';
import { GOVERNANCE_ABI } from '../../chain/governance';
import { ERC20_ABI, executeAsAgent } from '../../chain/markets';

// The IntegrityGovernance contract (contracts/src/oracle/IntegrityGovernance.sol) is real and
// tested, but its Base Sepolia deploy is deferred ("build now, defer deploy"). This panel reads
// live proposals from the oracle's /v1/governance/proposals endpoint. Where the contract is NOT
// deployed the oracle returns 503, and the panel stays in its honest "Not Yet Live" state — it
// deliberately does NOT flip to a live-but-empty proposal list (which would read as "DAO is
// live, nobody's proposed" rather than "not deployed"). No mocks, no fabricated tallies.

const STATE_COLOR: Record<string, string> = {
  Active: 'var(--primary)',
  Succeeded: 'var(--success)',
  Queued: 'var(--gold, #d4af37)',
  Executed: 'var(--success)',
  Defeated: '#f43f5e',
  Expired: 'var(--text-muted)',
  Canceled: 'var(--text-muted)',
};

const fmtItk = (wei: string): string => {
  try {
    const n = BigInt(wei) / 10n ** 18n;
    return n.toLocaleString();
  } catch {
    return '0';
  }
};

export function GovernancePanel() {
  const { selectedAgent, walletAddress, addToast } = useDashboard();
  const [proposals, setProposals] = useState<ProposalDto[] | null>(null);
  // null = not-yet-loaded/unknown, false = confirmed not deployed (503), true = live contract.
  const [deployed, setDeployed] = useState<boolean | null>(null);
  const [saAddr, setSaAddr] = useState<string | null>(null);
  const [voteAmounts, setVoteAmounts] = useState<Record<number, string>>({});
  const [votingId, setVotingId] = useState<number | null>(null);

  const refresh = () => {
    oracle
      .getGovernanceProposals()
      .then((rows) => {
        setProposals(rows);
        setDeployed(true);
      })
      .catch(() => setDeployed(false));
  };

  useEffect(() => {
    let cancelled = false;
    oracle
      .getGovernanceProposals()
      .then((rows) => {
        if (cancelled) return;
        setProposals(rows);
        setDeployed(true);
      })
      .catch(() => {
        // 503 (or unreachable) — the Governance contract isn't deployed on this network.
        if (cancelled) return;
        setDeployed(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const did = selectedAgent?.eth_address;
    if (!did) { setSaAddr(null); return; }
    let active = true;
    oracle.resolveSovereignAgent(did).then((a) => { if (active) setSaAddr(a); }).catch(() => { if (active) setSaAddr(null); });
    return () => { active = false; };
  }, [selectedAgent]);

  // castVote(id, support, amount) locks `amount` ITK as a vote — routed through the agent's
  // SovereignAgent.execute like every other write here (IntegrityGovernance pulls ITK from
  // msg.sender, so the SovereignAgent itself must hold + approve it). See chain/governance.ts
  // for why propose/queue/execute stay CLI/SDK-only.
  const handleVote = async (proposalId: number, support: boolean) => {
    if (!selectedAgent) { addToast('error', 'Select an agent first.'); return; }
    if (!walletAddress) { addToast('error', 'Connect the agent controller wallet.'); return; }
    if (!saAddr) { addToast('error', 'This agent has no on-chain SovereignAgent yet.'); return; }
    if (!GOVERNANCE_ADDRESS) { addToast('error', 'IntegrityGovernance is not deployed on this network.'); return; }

    const raw = voteAmounts[proposalId];
    const amt = ethers.parseEther(raw || '0');
    if (amt <= 0n) { addToast('error', 'Enter an ITK amount greater than zero.'); return; }

    setVotingId(proposalId);
    try {
      const eth = (window as any).ethereum;
      if (!eth) throw new Error('No Web3 wallet detected.');
      const signer = await new ethers.BrowserProvider(eth).getSigner();
      const itk = new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_ABI as any, signer);

      const saBal: bigint = await itk.balanceOf(saAddr);
      if (saBal < amt) {
        const need = amt - saBal;
        addToast('info', `Funding your agent with ${ethers.formatEther(need)} $ITK…`);
        await (await itk.transfer(saAddr, need)).wait();
      }

      const allowance: bigint = await itk.allowance(saAddr, GOVERNANCE_ADDRESS);
      if (allowance < amt) {
        addToast('info', 'Approving $ITK for governance…');
        const approveData = new ethers.Interface(ERC20_ABI as any).encodeFunctionData('approve', [GOVERNANCE_ADDRESS, amt]);
        await executeAsAgent(signer, saAddr, ITK_TOKEN_ADDRESS, approveData);
      }

      const voteData = new ethers.Interface(GOVERNANCE_ABI as any).encodeFunctionData('castVote', [proposalId, support, amt]);
      await executeAsAgent(signer, saAddr, GOVERNANCE_ADDRESS, voteData);

      addToast('success', `Voted ${support ? 'FOR' : 'AGAINST'} proposal #${proposalId}.`);
      setVoteAmounts((prev) => ({ ...prev, [proposalId]: '' }));
      refresh();
    } catch (err: any) {
      addToast('error', `Vote failed: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setVotingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {deployed && proposals && (
        <Panel title="On-Chain Proposals (Live)" icon={<Scale size={18} />}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Info size={12} />
            Voting is wallet-signed (below, on Active proposals). Proposing/queuing/executing
            remain CLI/SDK-only for now — see PRODUCTION_GAPS.md §4 for the scoping decision.
          </div>
          {proposals.length === 0 ? (
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', padding: 'var(--space-3)' }}>
              The IntegrityGovernance contract is live on this network, but no proposals have been
              created yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {proposals.map((p) => {
                const total = Number(fmtItk(p.for_votes).replace(/,/g, '')) + Number(fmtItk(p.against_votes).replace(/,/g, ''));
                const forPct = total > 0 ? (Number(fmtItk(p.for_votes).replace(/,/g, '')) / total) * 100 : 0;
                return (
                  <div key={p.id} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '0.7rem', fontWeight: 900, color: 'var(--text-muted)' }}>#{p.id}</span>
                        <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)' }}>{p.description || '(no description)'}</span>
                      </div>
                      <span style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em', color: STATE_COLOR[p.state] ?? 'var(--text-muted)' }}>
                        {p.state === 'Executed' && <CheckCircle size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />}
                        {p.state}
                      </span>
                    </div>
                    <div style={{ height: '6px', background: 'rgba(244,63,94,0.25)', borderRadius: '3px', overflow: 'hidden', margin: '8px 0 6px' }}>
                      <div style={{ width: `${forPct}%`, height: '100%', background: 'var(--success)' }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      <span>FOR {fmtItk(p.for_votes)} ITK</span>
                      <span>AGAINST {fmtItk(p.against_votes)} ITK</span>
                    </div>
                    {p.state === 'Active' && (
                      <div style={{ display: 'flex', gap: '6px', marginTop: '10px', alignItems: 'center' }}>
                        <input
                          type="text"
                          value={voteAmounts[p.id] ?? ''}
                          onChange={(e) => setVoteAmounts((prev) => ({ ...prev, [p.id]: e.target.value }))}
                          placeholder="ITK amount"
                          style={{
                            flex: 1, background: 'rgba(255,255,255,0.03)', border: '1px solid var(--glass-border)',
                            borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '0.75rem',
                            padding: '6px 10px', outline: 'none',
                          }}
                        />
                        <button
                          className="btn btn-sm"
                          disabled={votingId === p.id}
                          onClick={() => handleVote(p.id, true)}
                          style={{ background: 'var(--success)', color: '#052e16', fontWeight: 700 }}
                        >
                          {votingId === p.id ? <Loader2 size={12} className="pulse" /> : 'Vote FOR'}
                        </button>
                        <button
                          className="btn btn-sm"
                          disabled={votingId === p.id}
                          onClick={() => handleVote(p.id, false)}
                          style={{ background: '#f43f5e', color: 'white', fontWeight: 700 }}
                        >
                          {votingId === p.id ? <Loader2 size={12} className="pulse" /> : 'Vote AGAINST'}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      )}

      {deployed === false && (
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
      )}

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
