import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Key, ShieldCheck, User, Globe, Code } from 'lucide-react';
import { useDashboard } from '../context/useDashboard';
import { Panel } from '../components/shared/Panel';
import { IdentityPanel } from '../components/tabs/IdentityPanel';
import { PrivacyPanel } from '../components/tabs/PrivacyPanel';
import { getTier } from '../types';

// ─── Tier badge colours ───────────────────────────────────────────────────────
const TIER_COLORS: Record<string, string> = {
  AAA: 'var(--success)',
  AA:  '#34d399',
  A:   'var(--primary)',
  B:   '#f59e0b',
  C:   'var(--danger)',
};

// ─── Section fade/slide animation ────────────────────────────────────────────
const sectionVariants = {
  hidden:  { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.15 } },
} as any;

// ─── Component ────────────────────────────────────────────────────────────────
export function IdentityPage() {
  const { selectedAgent, activeTab, setActiveTab } = useDashboard();

  // ── Derived values ──────────────────────────────────────────────────────────
  // eth_address actually holds the agent's DID (did:integrity:…), so never re-wrap a value
  // that's already a DID — doing so produced a malformed `did:xibalba:did:integrity:…`.
  const rawDid    = (selectedAgent as any)?.did_document?.id ?? selectedAgent?.eth_address ?? null;
  const did       = rawDid ? (rawDid.startsWith('did:') ? rawDid : `did:xibalba:${rawDid}`) : null;
  const ais       = selectedAgent?.current_ais ?? null;
  const tier      = ais !== null ? getTier(ais) : null;
  const tierColor = tier ? TIER_COLORS[tier] : 'var(--text-muted)';
  const teeVerified = selectedAgent?.tee_verified ?? false;

  // ── Truncate long DID for display ──────────────────────────────────────────
  const shortDID = did
    ? did.length > 36
      ? `${did.slice(0, 18)}\u2026${did.slice(-14)}`
      : did
    : null;



  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', minHeight: 0 }}>



      {/* ── Agent identity card strip ──────────────────────────────────────── */}
      {selectedAgent ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.05 }}
        >
          <Panel>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 'var(--space-4)',
                padding: 'var(--space-2) 0',
              }}
            >
              {/* DID */}
              <div style={statCardStyle}>
                <div style={statLabelStyle}>
                  <Key size={12} style={{ marginRight: 4 }} />
                  Decentralized ID
                </div>
                <div
                  className="mono"
                  title={did ?? '\u2014'}
                  style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}
                >
                  {shortDID ?? <span style={{ color: 'var(--text-muted)' }}>Not Registered</span>}
                </div>
              </div>

              {/* AIS Score */}
              <div style={statCardStyle}>
                <div style={statLabelStyle}>AIS Score</div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--primary)', lineHeight: 1 }}>
                  {ais !== null ? ais.toFixed(1) : '\u2014'}
                </div>
              </div>

              {/* Verification Tier badge */}
              <div style={statCardStyle}>
                <div style={statLabelStyle}>Verification Tier</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  {tier ? (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '3px 10px',
                        borderRadius: '999px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        letterSpacing: '0.04em',
                        background: `${tierColor}22`,
                        color: tierColor,
                        border: `1px solid ${tierColor}55`,
                      }}
                    >
                      {tier}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>\u2014</span>
                  )}
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    L{selectedAgent.verification_tier}
                  </span>
                </div>
              </div>

              {/* ZK proof status — sourced from the oracle's zk_proof_verified, a real bb-verified
                  ZK-boost signal. NOT hardware TEE attestation (this protocol doesn't implement
                  one); labeled honestly as ZK proof rather than a fabricated SGX/TEE state. */}
              <div style={statCardStyle}>
                <div style={statLabelStyle}>ZK Proof Boost</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {teeVerified ? (
                    <>
                      <ShieldCheck size={18} color="var(--gold, #f59e0b)" />
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--gold, #f59e0b)' }}>
                        Verified (bb)
                      </span>
                    </>
                  ) : (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Not Boosted</span>
                  )}
                </div>
              </div>
            </div>
          </Panel>
        </motion.div>
      ) : (
        /* ── Empty state ─────────────────────────────────────────────────── */
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.05 }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 'var(--space-3)',
            padding: 'var(--space-10) var(--space-6)',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-lg)',
            border: '1px dashed var(--border-color)',
            textAlign: 'center',
          }}
        >
          <User size={40} color="var(--text-muted)" strokeWidth={1.5} />
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Select an agent from the sidebar to manage identity
          </p>
        </motion.div>
      )}

      {/* ── Sub-navigation Tab Bar ───────────────────────────────────────── */}

      {/* ── Section content (Tabbed Component Mount) ────────────────────── */}
      <div style={{ marginTop: 'var(--space-2)' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            {activeTab === 'identity' && (
              <div className="flex-col gap-6">
                <IdentityPanel />
                <PrivacyPanel />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── Shared micro-styles ─────────────────────────────────────────────────────
const statCardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  padding: 'var(--space-3) var(--space-4)',
  background: 'var(--bg-primary)',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--border-color)',
  minWidth: 0,
};

const statLabelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  fontSize: '0.7rem',
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 2,
};
