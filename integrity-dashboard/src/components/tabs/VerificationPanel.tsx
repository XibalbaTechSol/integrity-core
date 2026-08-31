import { useState, useEffect, useCallback } from 'react';
import { useDashboard } from '../../context/DashboardContext';
import { Panel } from '../shared/Panel';
import { StatusBadge } from '../shared/StatusBadge';
import { SeededDataBadge } from '../shared/SeededDataBadge';
import { ShieldCheck, RefreshCw, Send } from 'lucide-react';
import { oracle, type VerificationListResponse, type KycChallengeResponse } from '../../services/oracle';

const METHOD_LABEL: Record<string, string> = {
    dns: 'DNS (Tier 2)',
    github: 'GitHub (Tier 2)',
    tee: 'AWS Nitro TEE (Tier 3)',
    kyc: 'KYC (Tier 3)',
};

export function VerificationPanel() {
    const { selectedAgent, addToast } = useDashboard();
    const agentDid = selectedAgent?.eth_address;

    const [data, setData] = useState<VerificationListResponse | null>(null);
    const [loading, setLoading] = useState(false);

    const [provider, setProvider] = useState('');
    const [requestingChallenge, setRequestingChallenge] = useState(false);
    const [challenge, setChallenge] = useState<KycChallengeResponse | null>(null);

    const [receiptJson, setReceiptJson] = useState('');
    const [submittingReceipt, setSubmittingReceipt] = useState(false);

    const refresh = useCallback(() => {
        if (!agentDid) { setData(null); return; }
        setLoading(true);
        oracle.getVerifications(agentDid)
            .then(setData)
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, [agentDid]);

    useEffect(() => { refresh(); }, [refresh]);

    const handleRequestChallenge = async () => {
        if (!agentDid) return;
        const trimmed = provider.trim().toLowerCase();
        if (!trimmed) { addToast('error', 'Enter a KYC provider id first.'); return; }
        setRequestingChallenge(true);
        setChallenge(null);
        try {
            const res = await oracle.requestKycChallenge(agentDid, trimmed);
            setChallenge(res);
            addToast('info', 'Challenge issued — sign the message below with your KYC provider tooling, then paste the resulting receipt.');
        } catch (err: any) {
            addToast('error', `Challenge request failed: ${err.message}`);
        } finally {
            setRequestingChallenge(false);
        }
    };

    const handleSubmitReceipt = async () => {
        if (!agentDid) return;
        let receipt;
        try {
            receipt = JSON.parse(receiptJson);
        } catch {
            addToast('error', 'Receipt is not valid JSON.');
            return;
        }
        setSubmittingReceipt(true);
        try {
            await oracle.submitKycReceipt(agentDid, receipt);
            addToast('success', 'KYC receipt verified — Tier 3 evidence recorded.');
            setReceiptJson('');
            setChallenge(null);
            refresh();
        } catch (err: any) {
            addToast('error', `Receipt rejected: ${err.message}`);
        } finally {
            setSubmittingReceipt(false);
        }
    };

    if (!selectedAgent) {
        return (
            <Panel title="Verification Ladder" icon={<ShieldCheck size={18} />}>
                <div className="text-muted" style={{ padding: 'var(--space-4)', textAlign: 'center' }}>
                    Select an agent to view its verification tier and evidence.
                </div>
            </Panel>
        );
    }

    return (
        <div className="flex-col gap-6">
            <Panel
                title="Verification Ladder"
                icon={<ShieldCheck size={18} />}
                action={
                    <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={refresh} disabled={loading}>
                        <RefreshCw size={14} className={loading ? 'spin' : ''} />
                    </button>
                }
            >
                {!data ? (
                    <div className="text-muted" style={{ textAlign: 'center', padding: 'var(--space-4)' }}>
                        {loading ? 'Loading…' : 'No verification data.'}
                    </div>
                ) : (
                    <div className="flex-col gap-4">
                        <div className="flex gap-4" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
                            <div>
                                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Effective Tier</div>
                                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--primary)' }}>{data.effective_tier}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Registration Floor</div>
                                <div className="mono">{data.registration_tier}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>AIS Ceiling</div>
                                <div className="mono">{data.ais_ceiling}</div>
                            </div>
                            {data.tier_source === 'dev_override' && (
                                <SeededDataBadge label="Tier asserted by dev override — not proven" />
                            )}
                        </div>

                        <div className="table-container">
                            <table className="table">
                                <thead>
                                    <tr><th>Method</th><th>Subject</th><th>Tier Granted</th><th>Verified</th><th>Expires</th><th>Status</th></tr>
                                </thead>
                                <tbody>
                                    {data.verifications.map(v => (
                                        <tr key={v.id}>
                                            <td>{METHOD_LABEL[v.method] || v.method}</td>
                                            <td className="mono" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.subject}</td>
                                            <td className="mono">{v.tier_granted}</td>
                                            <td>{new Date(v.verified_at).toLocaleDateString()}</td>
                                            <td>{v.expires_at ? new Date(v.expires_at).toLocaleDateString() : 'Never'}</td>
                                            <td>
                                                {v.revoked_at
                                                    ? <StatusBadge status="revoked" />
                                                    : <StatusBadge status="verified" />}
                                            </td>
                                        </tr>
                                    ))}
                                    {data.verifications.length === 0 && (
                                        <tr><td colSpan={6} className="text-muted" style={{ textAlign: 'center', padding: '2rem' }}>
                                            No verification evidence on record yet.
                                        </td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </Panel>

            <Panel title="KYC Verification" icon={<ShieldCheck size={18} />}>
                <div className="flex-col gap-4">
                    <p className="text-muted" style={{ fontSize: '0.8rem' }}>
                        The oracle never receives documents, selfies, or identifiers — a self-hosted or commercial
                        KYC provider performs those checks in its own trust domain and signs a narrow receipt with
                        a key the oracle operator configured in <code>KYC_PROVIDER_KEYS</code>. This panel requests
                        the nonce and submits the resulting receipt; it never signs anything itself, since that
                        requires the agent's own DID key, which this browser does not hold.
                    </p>

                    <div className="form-group">
                        <label className="form-label" htmlFor="kyc-provider">Provider ID</label>
                        <div className="flex gap-3">
                            <input
                                id="kyc-provider"
                                type="text"
                                className="input"
                                placeholder="e.g. open-kyc"
                                value={provider}
                                onChange={e => setProvider(e.target.value)}
                                style={{ flex: 1 }}
                            />
                            <button className="btn btn-outline" onClick={handleRequestChallenge} disabled={requestingChallenge}>
                                {requestingChallenge ? <RefreshCw className="spin" size={16} /> : 'Request Challenge'}
                            </button>
                        </div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                            Must match a provider id the oracle operator has configured a trust key for.
                        </div>
                    </div>

                    {challenge && (
                        <div style={{ background: 'var(--bg-primary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '6px' }}>Nonce</div>
                            <div className="mono" style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>{challenge.nonce}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '10px 0 6px' }}>Signed message format</div>
                            <div className="mono" style={{ fontSize: '0.7rem', wordBreak: 'break-all' }}>{challenge.message_format}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '10px 0 6px' }}>Expires</div>
                            <div className="mono" style={{ fontSize: '0.8rem' }}>{new Date(challenge.expires_at).toLocaleString()}</div>
                        </div>
                    )}

                    <div className="form-group">
                        <label className="form-label" htmlFor="kyc-receipt">Signed Receipt (JSON)</label>
                        <textarea
                            id="kyc-receipt"
                            className="input"
                            rows={8}
                            style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.75rem' }}
                            placeholder='{"provider": "...", "opaque_subject_reference": "...", "assurance_profile": "open_source_kyc_v1", "checks": {...}, "verified_at": "...", "expires_at": "...", "nonce": "...", "signature": "..."}'
                            value={receiptJson}
                            onChange={e => setReceiptJson(e.target.value)}
                        />
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                            Produced and signed by your provider's own tooling (SDK/CLI), not by this browser.
                        </div>
                    </div>

                    <button
                        className="btn btn-primary"
                        onClick={handleSubmitReceipt}
                        disabled={submittingReceipt || !receiptJson.trim()}
                    >
                        {submittingReceipt ? <RefreshCw className="spin" size={16} /> : <><Send size={15} style={{ marginRight: 6 }} /> Submit Receipt</>}
                    </button>
                </div>
            </Panel>
        </div>
    );
}
