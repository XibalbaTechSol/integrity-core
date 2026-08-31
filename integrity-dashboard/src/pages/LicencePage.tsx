import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ethers } from 'ethers';
import { FileText, ShieldAlert, Search, RefreshCw, Wallet, Lock, Unlock } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { LICENCE_ACCOUNT_ABI } from '../chain/licence';
import { withRetry } from '../chain/retry';
import { RPC_URL, LICENCE_REFERENCE } from '../constants';

// Read-only viewer for a LicenceAccount (contracts/src/licence/LicenceAccount.sol) --
// the Phase II tracer-bullet ERC-6551 licence account. Deployed ONE PER LICENCE (no
// factory singleton), so this page still takes an address directly rather than
// resolving one purely from constants.ts -- but `deployments.baseSepolia.json` DOES
// record one real reference deployment (`experimentalPhase2LicenceReference`,
// `LICENCE_REFERENCE` below), so the page defaults to that address on first visit
// (before anything is saved to localStorage) instead of starting blank. A user can
// still paste any other LicenceAccount address; empty/error states past that default
// are real, not decorative.
const LAST_ADDRESS_KEY = 'licencePage.lastAddress';

interface LicenceState {
  owner: string;
  tokenChainId: bigint;
  tokenContract: string;
  tokenId: bigint;
  volumeCapTotal: bigint;
  consumedUnits: bigint;
  royaltyPricePerUnitWei: bigint;
  licenceStartTime: bigint;
  licenceEndTime: bigint;
  state: bigint;
  armed: boolean;
  armedCommittedBalance: bigint;
  balance: bigint;
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

export default function LicencePage() {
  const [address, setAddress] = useState(
    () => localStorage.getItem(LAST_ADDRESS_KEY) ?? LICENCE_REFERENCE?.tokenBoundAccount ?? ''
  );
  const [queried, setQueried] = useState<string | null>(null);
  const [licence, setLicence] = useState<LicenceState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (addr: string) => {
    if (!ethers.isAddress(addr)) {
      setError('Not a valid address.');
      setLicence(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await withRetry(async () => {
      const provider = new ethers.JsonRpcProvider(RPC_URL);
      const code = await provider.getCode(addr);
      if (code === '0x') {
        throw new Error('No contract deployed at this address on this network.');
      }
      const contract = new ethers.Contract(addr, LICENCE_ACCOUNT_ABI, provider);
      const [
        owner,
        token,
        volumeCapTotal,
        consumedUnits,
        royaltyPricePerUnitWei,
        licenceStartTime,
        licenceEndTime,
        state,
        armed,
        armedCommittedBalance,
        balance,
      ] = await Promise.all([
        contract.owner(),
        contract.token(),
        contract.volumeCapTotal(),
        contract.consumedUnits(),
        contract.royaltyPricePerUnitWei(),
        contract.licenceStartTime(),
        contract.licenceEndTime(),
        contract.state(),
        contract.armed(),
        contract.armedCommittedBalance(),
        provider.getBalance(addr),
      ]);
      setLicence({
        owner,
        tokenChainId: token[0],
        tokenContract: token[1],
        tokenId: token[2],
        volumeCapTotal,
        consumedUnits,
        royaltyPricePerUnitWei,
        licenceStartTime,
        licenceEndTime,
        state,
        armed,
        armedCommittedBalance,
        balance,
      });
      setQueried(addr);
      localStorage.setItem(LAST_ADDRESS_KEY, addr);
      });
    } catch (e) {
      setLicence(null);
      setError(
        e instanceof Error
          ? `Could not read this address as a LicenceAccount: ${e.message}`
          : 'Could not read this address as a LicenceAccount.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (address && ethers.isAddress(address)) {
      load(address);
    }
    // `load` is a stable useCallback (no deps), so this only runs on mount --
    // restores the last-viewed address without re-firing on every keystroke.
  }, [load]);

  // --- write actions -- owner-gated on-chain already (consume/armTransfer/disarmTransfer all
  // check msg.sender == owner() themselves), but the UI hides/labels around that too rather
  // than letting a non-owner submit a transaction that can only ever revert.
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [actionBusy, setActionBusy] = useState<'consume' | 'arm' | 'disarm' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [consumeUnits, setConsumeUnits] = useState('1');
  const [armAmount, setArmAmount] = useState('');

  const getSigner = async () => {
    const eth = (window as unknown as { ethereum?: ethers.Eip1193Provider }).ethereum;
    if (!eth) throw new Error('No wallet extension found (window.ethereum is undefined).');
    return new ethers.BrowserProvider(eth).getSigner();
  };

  const connectWallet = async () => {
    setConnecting(true);
    setActionError(null);
    try {
      const signer = await getSigner();
      setWalletAddress(await signer.getAddress());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not connect wallet.');
    } finally {
      setConnecting(false);
    }
  };

  const runAction = async (kind: 'consume' | 'arm' | 'disarm', fn: (contract: ethers.Contract) => Promise<ethers.ContractTransactionResponse>) => {
    if (!queried) return;
    setActionBusy(kind);
    setActionError(null);
    setActionSuccess(null);
    try {
      const signer = await getSigner();
      const contract = new ethers.Contract(queried, LICENCE_ACCOUNT_ABI, signer);
      const tx = await fn(contract);
      setActionSuccess(`Transaction submitted: ${tx.hash} -- waiting for confirmation…`);
      await tx.wait();
      setActionSuccess(`Confirmed: ${tx.hash}`);
      await load(queried);
    } catch (e) {
      const err = e as { shortMessage?: string; reason?: string; message?: string };
      setActionError(err.shortMessage || err.reason || err.message || 'Transaction failed.');
    } finally {
      setActionBusy(null);
    }
  };

  const handleConsume = () => {
    if (!licence) return;
    const units = BigInt(consumeUnits || '0');
    if (units <= 0n) {
      setActionError('Units must be greater than zero.');
      return;
    }
    const royaltyDue = units * licence.royaltyPricePerUnitWei;
    runAction('consume', (c) => c.consume(units, { value: royaltyDue }));
  };

  const handleArm = () => {
    const committed = ethers.parseEther(armAmount || '0');
    runAction('arm', (c) => c.armTransfer(committed));
  };

  const handleDisarm = () => {
    runAction('disarm', (c) => c.disarmTransfer());
  };

  const now = BigInt(Math.floor(Date.now() / 1000));
  const licenceStatus = licence
    ? now < licence.licenceStartTime
      ? 'not yet active'
      : now > licence.licenceEndTime
        ? 'expired'
        : 'active'
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
    >
      <Panel title="Licence account" icon={<FileText size={16} />}>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: '0 0 var(--space-4)' }}>
          Read-only viewer for a <code>LicenceAccount</code> (Phase II tracer-bullet ERC-6551
          account -- volume cap, royalty, expiry, transfer-drain guard). Deployed one per
          licence, not a singleton -- paste the deployed contract's address below. Nothing is
          simulated or backfilled: if the address isn't a live <code>LicenceAccount</code> on
          this network, that's shown as an error, not blank/default values.
        </p>
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
            placeholder="0x… licence account address"
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

      {!error && !licence && !loading && (
        <Panel>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: 'var(--space-6) 0' }}>
            No address loaded yet.
          </div>
        </Panel>
      )}

      {licence && queried && (
        <>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
            <StatCard
              icon={<FileText size={18} />}
              label="Volume consumed"
              value={`${licence.consumedUnits.toString()} / ${licence.volumeCapTotal.toString()}`}
              sub={
                licence.volumeCapTotal > 0n
                  ? `${((Number(licence.consumedUnits) / Number(licence.volumeCapTotal)) * 100).toFixed(1)}% of cap`
                  : undefined
              }
            />
            <StatCard
              icon={<FileText size={18} />}
              label="Royalty per unit"
              value={`${ethers.formatEther(licence.royaltyPricePerUnitWei)} ETH`}
            />
            <StatCard
              icon={<FileText size={18} />}
              label="Accrued balance"
              value={`${ethers.formatEther(licence.balance)} ETH`}
              sub="native balance = b_I (eq. 16), no separate accounting variable"
            />
            <StatCard
              icon={<ShieldAlert size={18} />}
              label="Transfer-drain guard"
              value={licence.armed ? 'ARMED' : 'disarmed'}
              sub={licence.armed ? `committed ≥ ${ethers.formatEther(licence.armedCommittedBalance)} ETH` : undefined}
            />
          </div>

          <Panel title="Licence terms & state" icon={<FileText size={16} />}>
            <Row label="Address" value={queried} />
            <Row label="Owner (current licensee)" value={licence.owner} />
            <Row
              label="Token"
              value={`chain ${licence.tokenChainId.toString()} · ${licence.tokenContract} · #${licence.tokenId.toString()}`}
            />
            <Row
              label="Status"
              value={
                <span
                  style={{
                    color:
                      licenceStatus === 'active'
                        ? 'var(--success, #30a46c)'
                        : licenceStatus === 'expired'
                          ? 'var(--danger, #e5484d)'
                          : 'var(--text-muted)',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    fontSize: '0.75rem',
                  }}
                >
                  {licenceStatus}
                </span>
              }
            />
            <Row label="Start" value={new Date(Number(licence.licenceStartTime) * 1000).toLocaleString()} />
            <Row label="End" value={new Date(Number(licence.licenceEndTime) * 1000).toLocaleString()} />
            <Row label="State counter" value={licence.state.toString()} />
          </Panel>

          <Panel title="Manage this licence" icon={<Wallet size={16} />}>
            {!walletAddress ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
                  Connect the owner's wallet to consume units, or arm/disarm the transfer-drain guard.
                </p>
                <button
                  onClick={connectWallet}
                  disabled={connecting}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-2)',
                    background: 'var(--primary)',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-3) var(--space-4)',
                    color: 'var(--bg-primary, #000)',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: connecting ? 'default' : 'pointer',
                    opacity: connecting ? 0.6 : 1,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {connecting ? <RefreshCw size={14} className="spin" /> : <Wallet size={14} />}
                  {connecting ? 'Connecting…' : 'Connect wallet'}
                </button>
              </div>
            ) : walletAddress.toLowerCase() !== licence.owner.toLowerCase() ? (
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Connected as <code>{walletAddress}</code>, but this licence's owner is{' '}
                <code>{licence.owner}</code> -- every write here is owner-gated on-chain, so
                connect that wallet to manage it.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--space-2)' }}>
                    Consume units
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                    <input
                      type="number"
                      min="1"
                      value={consumeUnits}
                      onChange={(e) => setConsumeUnits(e.target.value)}
                      style={{
                        width: '120px',
                        background: 'var(--bg-secondary)',
                        border: '1px solid var(--glass-border)',
                        borderRadius: 'var(--radius-md)',
                        padding: 'var(--space-3)',
                        color: 'var(--text-primary)',
                        fontSize: '0.85rem',
                      }}
                    />
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      units × {ethers.formatEther(licence.royaltyPricePerUnitWei)} ETH ={' '}
                      {ethers.formatEther(BigInt(consumeUnits || '0') * licence.royaltyPricePerUnitWei)} ETH royalty
                    </span>
                    <button
                      onClick={handleConsume}
                      disabled={actionBusy !== null}
                      style={{
                        background: 'var(--primary)',
                        border: 'none',
                        borderRadius: 'var(--radius-md)',
                        padding: 'var(--space-3) var(--space-4)',
                        color: 'var(--bg-primary, #000)',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        cursor: actionBusy ? 'default' : 'pointer',
                        opacity: actionBusy ? 0.6 : 1,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {actionBusy === 'consume' ? 'Consuming…' : 'Consume'}
                    </button>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--space-2)' }}>
                    Transfer-drain guard
                  </div>
                  {licence.armed ? (
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Armed at {ethers.formatEther(licence.armedCommittedBalance)} ETH committed.
                      </span>
                      <button
                        onClick={handleDisarm}
                        disabled={actionBusy !== null}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 'var(--space-2)',
                          background: 'var(--bg-secondary)',
                          border: '1px solid var(--glass-border)',
                          borderRadius: 'var(--radius-md)',
                          padding: 'var(--space-3) var(--space-4)',
                          color: 'var(--text-primary)',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          cursor: actionBusy ? 'default' : 'pointer',
                          opacity: actionBusy ? 0.6 : 1,
                        }}
                      >
                        <Unlock size={14} />
                        {actionBusy === 'disarm' ? 'Disarming…' : 'Disarm'}
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                      <input
                        type="text"
                        placeholder="committed balance in ETH"
                        value={armAmount}
                        onChange={(e) => setArmAmount(e.target.value)}
                        style={{
                          width: '220px',
                          background: 'var(--bg-secondary)',
                          border: '1px solid var(--glass-border)',
                          borderRadius: 'var(--radius-md)',
                          padding: 'var(--space-3)',
                          color: 'var(--text-primary)',
                          fontSize: '0.85rem',
                        }}
                      />
                      <button
                        onClick={handleArm}
                        disabled={actionBusy !== null}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 'var(--space-2)',
                          background: 'var(--bg-secondary)',
                          border: '1px solid var(--glass-border)',
                          borderRadius: 'var(--radius-md)',
                          padding: 'var(--space-3) var(--space-4)',
                          color: 'var(--text-primary)',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          cursor: actionBusy ? 'default' : 'pointer',
                          opacity: actionBusy ? 0.6 : 1,
                        }}
                      >
                        <Lock size={14} />
                        {actionBusy === 'arm' ? 'Arming…' : 'Arm'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {actionError && (
              <div style={{ color: 'var(--danger, #e5484d)', fontSize: '0.8rem', marginTop: 'var(--space-3)' }}>{actionError}</div>
            )}
            {actionSuccess && (
              <div style={{ color: 'var(--success, #30a46c)', fontSize: '0.8rem', marginTop: 'var(--space-3)', wordBreak: 'break-all' }}>
                {actionSuccess}
              </div>
            )}
          </Panel>

          <Panel title="ATCP/IP signed-intent path" icon={<ShieldAlert size={16} />}>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: 'var(--space-2) 0' }}>
              Session-key authorization and <code>consumeWithIntent</code> (see
              docs/plans/2026-08-24-phase2-atcpip-intent-format-proposal.md) are proposed, not yet
              authorized or wired into this page -- this viewer only reads the base tracer-bullet
              slice's state.
            </div>
          </Panel>
        </>
      )}
    </motion.div>
  );
}
