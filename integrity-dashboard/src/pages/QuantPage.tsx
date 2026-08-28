import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ethers } from 'ethers';
import { Activity, ShieldCheck, Wallet, ListChecks } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { oracle, AgentResponse, AisResponse, WalletResponse, AgentEventDto } from '../services/oracle';
import { usePinnedAgent } from '../hooks/usePinnedAgent';

// xibalba-quant's Integrity Protocol DID. Fixed and stable ahead of on-chain
// registration -- integrity_sdk.did.load_or_create_did("xibalba-quant") is
// deterministic from its locally-generated Ed25519 keypair, so this DID
// does not change once Phase 2 (registration) runs; it's just unresolvable
// on-chain until then. See ~/.claude/plans/velvet-gathering-rivest.md.
const QUANT_AGENT_ID = 'did:integrity:7d0ecae532e6a72855267492051a7e7ec3262f5bdc3afc8cee0a1dfca4c438f8';

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        flex: 1,
        minWidth: 0,
      }}
    >
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--primary-dim)',
          border: '1px solid var(--primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--primary)',
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '2px' }}>
          {label}
        </div>
        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--theme-accent)', fontVariantNumeric: 'tabular-nums' }}>
          {value}
        </div>
        {sub && <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function QuantPage() {
  usePinnedAgent(QUANT_AGENT_ID);
  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [events, setEvents] = useState<AgentEventDto[]>([]);
  const [notRegistered, setNotRegistered] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setNotRegistered(false);

    oracle
      .getAgent(QUANT_AGENT_ID)
      .then((a) => {
        if (!active) return;
        setAgent(a);
        // These three only make sense once the agent is actually registered
        // on-chain -- fetched after, not in parallel, so a 404 on getAgent
        // alone explains "not registered yet" instead of three separate
        // failed calls each needing their own explanation.
        Promise.allSettled([
          oracle.getAis(QUANT_AGENT_ID),
          oracle.getWallet(QUANT_AGENT_ID),
          oracle.getEvents(QUANT_AGENT_ID, 25),
        ]).then(([aisR, walletR, eventsR]) => {
          if (!active) return;
          if (aisR.status === 'fulfilled') setAis(aisR.value);
          if (walletR.status === 'fulfilled') setWallet(walletR.value);
          if (eventsR.status === 'fulfilled') setEvents(eventsR.value);
        });
      })
      .catch(() => {
        if (active) setNotRegistered(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
    >
      <Panel title="xibalba-quant" icon={<Activity size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: 0 }}>
          Autonomous trading agent — a real-world stress test of Integrity Protocol's Behavioral
          Commitment Chain mediation pipeline under live, autonomous financial decisions. Every
          trade is gated through a real signed commitment and OPA policy verdict before it
          executes; nothing here is simulated. DID:{' '}
          <code style={{ fontSize: '0.75rem', wordBreak: 'break-all' }}>{QUANT_AGENT_ID}</code>
        </p>
      </Panel>

      {loading && (
        <Panel>
          <div className="skeleton" style={{ height: '80px', borderRadius: 'var(--radius-md)' }} />
        </Panel>
      )}

      {!loading && notRegistered && (
        <Panel icon={<ShieldCheck size={16} />}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: 'var(--space-6) 0' }}>
            Not registered on Integrity Protocol yet. This page will populate once the on-chain
            registration step (Phase 2 of the build plan) runs — nothing to show here is faked
            in the meantime.
          </div>
        </Panel>
      )}

      {!loading && agent && (
        <>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
            <StatCard
              icon={<ShieldCheck size={18} />}
              label="Verification Tier"
              value={String(agent.verification_tier)}
              sub={agent.verification_tier < 1 ? 'unverified — trades will be denied' : undefined}
            />
            <StatCard icon={<Activity size={18} />} label="AIS Score" value={ais ? ais.ais.toFixed(1) : '—'} />
            <StatCard
              icon={<Wallet size={18} />}
              label="ITK Balance"
              value={wallet ? Number(ethers.formatEther(wallet.itk_balance)).toLocaleString() : '—'}
            />
            <StatCard icon={<ListChecks size={18} />} label="Recorded Events" value={String(events.length)} />
          </div>

          <Panel title="Recent activity" icon={<ListChecks size={16} />}>
            {events.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: 'var(--space-4) 0' }}>
                No recorded telemetry events yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {events.map((e, i) => (
                  <div
                    key={i}
                    style={{
                      border: '1px solid var(--glass-border)',
                      borderRadius: 'var(--radius-md)',
                      padding: 'var(--space-3)',
                      fontSize: '0.8rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                      <span>{e.event_name ?? 'event'}</span>
                      <span>{new Date(e.time).toLocaleString()}</span>
                    </div>
                    {e.body && <div style={{ marginTop: '4px' }}>{e.body}</div>}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Trade rationale & decision history" icon={<ListChecks size={16} />}>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: 'var(--space-4) 0' }}>
              Per-trade rationale and rejected-commitment history live in xibalba-cortex's
              memory store, not the oracle — not wired into this dashboard yet. Query it
              directly via cortex's memory_recall for now.
            </div>
          </Panel>
        </>
      )}
    </motion.div>
  );
}
