import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ethers } from 'ethers';
import { ShieldAlert, Search, RefreshCw, Cpu, Users, Wallet, Gauge } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { INTEGRITY_ACCOUNT_ABI, INTEGRITY_KERNEL_ABI } from '../chain/kernel';
import { RPC_URL, KERNEL_REFERENCE } from '../constants';

// Read-only viewer for a Phase I IntegrityAccount + its currently-bound IntegrityKernel
// (contracts/src/kernel/). The kernel carries three reference adapters -- budget,
// reputation-floor, assurance-tier -- surfaced explicitly below as their own sections, not
// folded into a generic "kernel state" blob. Unlike LicenceAccount, a real instance is
// already deployed on Base Sepolia (KERNEL_REFERENCE, from deployments.baseSepolia.json's
// experimentalPhase1Reference block) -- but its own deploy record marks it EXPERIMENTAL,
// NOT AUDITED, so that disclosure is surfaced verbatim here, not paraphrased or dropped.
const LAST_ADDRESS_KEY = 'kernelPage.lastAccountAddress';

interface KernelState {
  accountAddr: string;
  kernelAddr: string;
  guardians: string[];
  guardianThreshold: bigint;
  moduleActionTimelockSeconds: bigint;
  rescueTimelockSeconds: bigint;
  pendingKernelSwap: { newKernel: string; readyAt: bigint };
  kernelSwapNonce: bigint;
  kernelSwapApprovalCount: bigint;
  swapInProgress: boolean;
  pendingGuardianAction: { active: boolean; isCancel: boolean; newKernel: string; targetKernelSwapNonce: bigint };
  pendingGuardianRotation: { active: boolean; isAddition: boolean; guardian: string };
  pendingRescueSweep: { active: boolean; to: string; amount: bigint; sweepFullBalance: boolean; readyAt: bigint };
  kernelBoundAccount: string;
  armed: boolean;
  perOpBudgetWei: bigint;
  cumulativeBudgetWei: bigint;
  cumulativeSpentWei: bigint;
  trackedToken: string;
  tokenPerOpBudgetWei: bigint;
  tokenCumulativeBudgetWei: bigint;
  tokenCumulativeSpentWei: bigint;
  reputationRegistry: string;
  minEffectiveScore: bigint;
  snapshotScore: bigint;
  snapshotIsZkBoosted: boolean;
  snapshotTakenAt: bigint;
  epochLengthSeconds: bigint;
}

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

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 'var(--space-4)',
        padding: 'var(--space-2) 0',
        borderBottom: '1px solid var(--glass-border)',
        fontSize: '0.85rem',
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono, monospace)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

const ZERO = '0x0000000000000000000000000000000000000000';

export default function KernelPage() {
  const [address, setAddress] = useState(
    () => localStorage.getItem(LAST_ADDRESS_KEY) ?? KERNEL_REFERENCE?.IntegrityAccount ?? '',
  );
  const [kernel, setKernel] = useState<KernelState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (addr: string) => {
    if (!ethers.isAddress(addr)) {
      setError('Not a valid address.');
      setKernel(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const provider = new ethers.JsonRpcProvider(RPC_URL);
      const accountCode = await provider.getCode(addr);
      if (accountCode === '0x') {
        throw new Error('No contract deployed at this address on this network.');
      }
      const account = new ethers.Contract(addr, INTEGRITY_ACCOUNT_ABI, provider);

      const kernelAddr: string = await account.hook();
      if (!kernelAddr || kernelAddr === ZERO) {
        throw new Error('This account has no kernel installed (hook() returned the zero address).');
      }
      const kernelCode = await provider.getCode(kernelAddr);
      if (kernelCode === '0x') {
        throw new Error(`hook() resolved to ${kernelAddr}, but no contract is deployed there.`);
      }
      const kernelContract = new ethers.Contract(kernelAddr, INTEGRITY_KERNEL_ABI, provider);

      const [
        guardians,
        guardianThreshold,
        moduleActionTimelockSeconds,
        rescueTimelockSeconds,
        pendingKernelSwapRaw,
        kernelSwapNonce,
        swapInProgress,
        pendingGuardianActionRaw,
        pendingGuardianRotationRaw,
        pendingRescueSweepRaw,
        kernelBoundAccount,
        armed,
        perOpBudgetWei,
        cumulativeBudgetWei,
        cumulativeSpentWei,
        trackedToken,
        tokenPerOpBudgetWei,
        tokenCumulativeBudgetWei,
        tokenCumulativeSpentWei,
        reputationRegistry,
        minEffectiveScore,
        snapshotScore,
        snapshotIsZkBoosted,
        snapshotTakenAt,
        epochLengthSeconds,
      ] = await Promise.all([
        account.guardians(),
        account.guardianThreshold(),
        account.moduleActionTimelockSeconds(),
        account.rescueTimelockSeconds(),
        account.pendingKernelSwap(),
        account.kernelSwapNonce(),
        account.swapInProgress(),
        account.pendingGuardianAction(),
        account.pendingGuardianRotation(),
        account.pendingRescueSweep(),
        kernelContract.boundAccount(),
        kernelContract.armed(),
        kernelContract.perOpBudgetWei(),
        kernelContract.cumulativeBudgetWei(),
        kernelContract.cumulativeSpentWei(),
        kernelContract.trackedToken(),
        kernelContract.tokenPerOpBudgetWei(),
        kernelContract.tokenCumulativeBudgetWei(),
        kernelContract.tokenCumulativeSpentWei(),
        kernelContract.reputationRegistry(),
        kernelContract.minEffectiveScore(),
        kernelContract.snapshotScore(),
        kernelContract.snapshotIsZkBoosted(),
        kernelContract.snapshotTakenAt(),
        kernelContract.epochLengthSeconds(),
      ]);

      const kernelSwapApprovalCount: bigint = await account.kernelSwapApprovalCount(kernelSwapNonce);

      setKernel({
        accountAddr: addr,
        kernelAddr,
        guardians,
        guardianThreshold,
        moduleActionTimelockSeconds,
        rescueTimelockSeconds,
        pendingKernelSwap: { newKernel: pendingKernelSwapRaw[0], readyAt: pendingKernelSwapRaw[1] },
        kernelSwapNonce,
        kernelSwapApprovalCount,
        swapInProgress,
        pendingGuardianAction: {
          active: pendingGuardianActionRaw[0],
          isCancel: pendingGuardianActionRaw[1],
          newKernel: pendingGuardianActionRaw[2],
          targetKernelSwapNonce: pendingGuardianActionRaw[3],
        },
        pendingGuardianRotation: {
          active: pendingGuardianRotationRaw[0],
          isAddition: pendingGuardianRotationRaw[1],
          guardian: pendingGuardianRotationRaw[2],
        },
        pendingRescueSweep: {
          active: pendingRescueSweepRaw[0],
          to: pendingRescueSweepRaw[1],
          amount: pendingRescueSweepRaw[2],
          sweepFullBalance: pendingRescueSweepRaw[3],
          readyAt: pendingRescueSweepRaw[4],
        },
        kernelBoundAccount,
        armed,
        perOpBudgetWei,
        cumulativeBudgetWei,
        cumulativeSpentWei,
        trackedToken,
        tokenPerOpBudgetWei,
        tokenCumulativeBudgetWei,
        tokenCumulativeSpentWei,
        reputationRegistry,
        minEffectiveScore,
        snapshotScore,
        snapshotIsZkBoosted,
        snapshotTakenAt,
        epochLengthSeconds,
      });
      localStorage.setItem(LAST_ADDRESS_KEY, addr);
    } catch (e) {
      setKernel(null);
      setError(
        e instanceof Error ? `Could not read this address as an IntegrityAccount: ${e.message}` : 'Could not read this address as an IntegrityAccount.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (address && ethers.isAddress(address)) {
      load(address);
    }
    // `load` is a stable useCallback (no deps) -- only runs on mount, to restore/prefill.
  }, [load]);

  const now = BigInt(Math.floor(Date.now() / 1000));
  const snapshotStale = kernel ? now > kernel.snapshotTakenAt + kernel.epochLengthSeconds : false;
  const boundAccountMismatch = kernel ? kernel.kernelBoundAccount.toLowerCase() !== kernel.accountAddr.toLowerCase() : false;

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
    >
      <Panel title="Kernel & guardians" icon={<Cpu size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: '0 0 var(--space-4)' }}>
          Read-only viewer for a Phase I <code>IntegrityAccount</code> and whichever{' '}
          <code>IntegrityKernel</code> it currently has installed as its hook -- resolved live via{' '}
          <code>hook()</code>, not assumed. The kernel's three reference adapters (budget,
          reputation-floor, assurance-tier) are shown as their own sections below.
        </p>
        {KERNEL_REFERENCE && (
          <div
            style={{
              background: 'color-mix(in srgb, var(--danger, #e5484d) 12%, var(--bg-secondary))',
              border: '1px solid var(--danger, #e5484d)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
              fontSize: '0.8rem',
              marginBottom: 'var(--space-4)',
            }}
          >
            <strong>{KERNEL_REFERENCE.disclosure}</strong>
            <div style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
              Deployed from commit <code>{KERNEL_REFERENCE.deployedFromCommit.slice(0, 12)}</code>.
            </div>
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(address.trim());
          }}
          style={{ display: 'flex', gap: 'var(--space-2)' }}
        >
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x… IntegrityAccount address"
            spellCheck={false}
            style={{
              flex: 1,
              minWidth: 0,
              background: 'var(--bg-secondary)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.85rem',
            }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              background: 'var(--primary)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              padding: '0 var(--space-4)',
              color: 'var(--bg-primary, #000)',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: loading ? 'default' : 'pointer',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? <RefreshCw size={14} className="spin" /> : <Search size={14} />}
            {loading ? 'Reading…' : 'Read'}
          </button>
        </form>
      </Panel>

      {error && (
        <Panel icon={<ShieldAlert size={16} />}>
          <div style={{ color: 'var(--danger, #e5484d)', fontSize: '0.85rem', padding: 'var(--space-2) 0' }}>{error}</div>
        </Panel>
      )}

      {!error && !kernel && !loading && (
        <Panel>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: 'var(--space-6) 0' }}>
            No address loaded yet.
          </div>
        </Panel>
      )}

      {kernel && (
        <>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
            <StatCard
              icon={<Users size={18} />}
              label="Guardian quorum"
              value={`${kernel.guardianThreshold.toString()} / ${kernel.guardians.length}`}
              sub="approvals required / guardian set size"
            />
            <StatCard
              icon={<Wallet size={18} />}
              label="Budget spent (native)"
              value={`${ethers.formatEther(kernel.cumulativeSpentWei)} / ${ethers.formatEther(kernel.cumulativeBudgetWei)} ETH`}
              sub={`${ethers.formatEther(kernel.perOpBudgetWei)} ETH per-op cap`}
            />
            <StatCard
              icon={<Gauge size={18} />}
              label="Reputation floor"
              value={`${kernel.snapshotScore.toString()} / ${kernel.minEffectiveScore.toString()} min`}
              sub={
                snapshotStale
                  ? 'snapshot STALE -- refreshReputationSnapshot() is permissionless'
                  : kernel.snapshotIsZkBoosted
                    ? 'ZK-boosted'
                    : undefined
              }
            />
            <StatCard
              icon={<ShieldAlert size={18} />}
              label="Kernel guard"
              value={kernel.armed ? 'ARMED' : 'idle'}
              sub={kernel.swapInProgress ? 'kernel swap in progress' : undefined}
            />
          </div>

          {boundAccountMismatch && (
            <Panel icon={<ShieldAlert size={16} />}>
              <div style={{ color: 'var(--danger, #e5484d)', fontSize: '0.85rem' }}>
                This kernel's own <code>boundAccount()</code> ({kernel.kernelBoundAccount}) does not match the
                account address queried ({kernel.accountAddr}) -- treat this reading with suspicion.
              </div>
            </Panel>
          )}

          <Panel title="Account & guardians" icon={<Users size={16} />}>
            <Row label="Account address" value={kernel.accountAddr} />
            <Row label="Resolved kernel (hook())" value={kernel.kernelAddr} />
            <Row label="Guardians" value={kernel.guardians.join(', ') || 'none'} />
            <Row label="Module-action timelock" value={`${kernel.moduleActionTimelockSeconds.toString()}s`} />
            <Row label="Rescue timelock" value={`${kernel.rescueTimelockSeconds.toString()}s`} />
          </Panel>

          <Panel title="Kernel-swap governance" icon={<Cpu size={16} />}>
            <Row
              label="Pending kernel swap"
              value={
                kernel.pendingKernelSwap.newKernel === ZERO
                  ? 'none'
                  : `→ ${kernel.pendingKernelSwap.newKernel} (ready at ${new Date(Number(kernel.pendingKernelSwap.readyAt) * 1000).toLocaleString()})`
              }
            />
            <Row
              label="Swap approvals"
              value={`${kernel.kernelSwapApprovalCount.toString()} / ${kernel.guardianThreshold.toString()} (nonce ${kernel.kernelSwapNonce.toString()})`}
            />
            <Row
              label="Guardian emergency action"
              value={
                kernel.pendingGuardianAction.active
                  ? `${kernel.pendingGuardianAction.isCancel ? 'force-cancel' : 'force-propose'} → ${kernel.pendingGuardianAction.newKernel}`
                  : 'none pending'
              }
            />
            <Row
              label="Guardian rotation"
              value={
                kernel.pendingGuardianRotation.active
                  ? `${kernel.pendingGuardianRotation.isAddition ? 'add' : 'remove'} ${kernel.pendingGuardianRotation.guardian}`
                  : 'none pending'
              }
            />
            <Row
              label="Rescue sweep"
              value={
                kernel.pendingRescueSweep.active
                  ? `${kernel.pendingRescueSweep.sweepFullBalance ? 'full balance' : ethers.formatEther(kernel.pendingRescueSweep.amount) + ' ETH'} → ${kernel.pendingRescueSweep.to}`
                  : 'none pending'
              }
            />
          </Panel>

          <Panel title="Budget adapter" icon={<Wallet size={16} />}>
            <Row label="Native: per-op cap" value={`${ethers.formatEther(kernel.perOpBudgetWei)} ETH`} />
            <Row label="Native: cumulative cap / spent" value={`${ethers.formatEther(kernel.cumulativeBudgetWei)} / ${ethers.formatEther(kernel.cumulativeSpentWei)} ETH`} />
            <Row
              label="Declared token"
              value={
                kernel.trackedToken === ZERO ? (
                  'disabled'
                ) : (
                  <>
                    {kernel.trackedToken}
                    <br />
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                      {ethers.formatEther(kernel.tokenCumulativeSpentWei)} / {ethers.formatEther(kernel.tokenCumulativeBudgetWei)} spent
                      (assumes 18 decimals), {ethers.formatEther(kernel.tokenPerOpBudgetWei)} per-op cap
                    </span>
                  </>
                )
              }
            />
          </Panel>

          <Panel title="Reputation-floor & assurance-tier adapters" icon={<Gauge size={16} />}>
            <Row label="Reputation registry" value={kernel.reputationRegistry} />
            <Row label="Minimum effective score" value={kernel.minEffectiveScore.toString()} />
            <Row label="Cached snapshot score" value={kernel.snapshotScore.toString()} />
            <Row label="ZK-boosted" value={kernel.snapshotIsZkBoosted ? 'yes' : 'no'} />
            <Row label="Snapshot taken at" value={new Date(Number(kernel.snapshotTakenAt) * 1000).toLocaleString()} />
            <Row label="Epoch length" value={`${kernel.epochLengthSeconds.toString()}s`} />
            <Row
              label="Snapshot status"
              value={
                <span style={{ color: snapshotStale ? 'var(--danger, #e5484d)' : 'var(--success, #30a46c)', fontWeight: 600 }}>
                  {snapshotStale ? 'STALE' : 'fresh'}
                </span>
              }
            />
          </Panel>
        </>
      )}
    </motion.div>
  );
}
