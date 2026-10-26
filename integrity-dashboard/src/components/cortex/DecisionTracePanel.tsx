import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, GitBranch, LockKeyhole } from 'lucide-react';
import type { DecisionTraceProjection } from '../../services/graphMemory';

function short(value: string | null | undefined) { return value ? `${value.slice(0, 14)}…` : 'none'; }

export default function DecisionTracePanel({ trace, loading, error, sessionId, onRetry }: {
    trace: DecisionTraceProjection | null;
    loading: boolean;
    error: string | null;
    sessionId: string;
    onRetry: () => void;
}) {
    const [selected, setSelected] = useState(0);
    const event = trace?.events[selected] ?? trace?.events[0];
    const maxProbability = useMemo(() => Math.max(1, ...((event?.advisory?.transition_probabilities && Object.values(event.advisory.transition_probabilities)) || [])), [event]);
    return <section className="memory-tab-panel decision-trace-panel" aria-labelledby="decision-trace-title">
        <div className="memory-panel-header">
            <div><span className="memory-eyebrow">Jev advisory · Integrity evidence</span><h2 id="decision-trace-title">DecisionTrace</h2><p className="memory-muted">A redacted, hash-linked view of observed transitions across Hermes, Cortex, and Shield.</p></div>
            <div className="memory-header-actions"><span className={`decision-trace-status ${trace?.valid ? 'good' : 'warn'}`}>{trace?.valid ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />} {trace?.valid ? 'Locally verified' : 'Verification pending'}</span><span className="memory-badge">{trace?.events.length ?? 0} events</span></div>
        </div>
        {loading && <div className="memory-empty-state"><GitBranch size={22} /><strong>Loading DecisionTrace</strong><span>Reading the profile-local trace projection.</span></div>}
        {!loading && error && <div className="memory-empty-state"><AlertTriangle size={22} /><strong>Trace unavailable</strong><span>{error}</span><button className="memory-small-button" onClick={onRetry} type="button">Retry</button></div>}
        {!loading && !error && trace && trace.events.length === 0 && <div className="memory-empty-state"><GitBranch size={22} /><strong>No DecisionTrace recorded</strong><span>Cortex has no redacted trace for session <code>{sessionId}</code>. This is an evidence gap, not a zero-risk result.</span></div>}
        {!loading && !error && trace && trace.events.length > 0 && <>
            <div className="decision-trace-summary"><div><span>Trace</span><code>{short(trace.trace_id)}</code></div><div><span>Merkle root</span><code>{short(trace.root)}</code></div><div><span>Session</span><code>{short(trace.session_id)}</code></div><div><span>Authority</span><b>Shield policy path</b></div></div>
            <div className="decision-trace-layout">
                <div className="decision-trace-timeline" aria-label="DecisionTrace event timeline">{trace.events.map((item, index) => <button type="button" className={`decision-trace-event ${index === selected ? 'selected' : ''}`} key={item.event_id} onClick={() => setSelected(index)}><span className="decision-trace-marker">{index + 1}</span><span><b>{item.envelope.event_type}</b><small>{item.envelope.policy_decision || 'observed'} · {item.advisory?.risk_category || 'unclassified'}</small><code>{short(item.event_hash)}</code></span></button>)}</div>
                <article className="decision-trace-detail"><div className="memory-block-header"><div><span className="memory-eyebrow">Selected event</span><h3>{event?.envelope.event_type}</h3></div><span className="memory-badge">{event?.advisory?.status || 'no advisory'}</span></div><dl className="decision-trace-fields"><dt>Policy decision</dt><dd>{event?.envelope.policy_decision || 'not reported'}</dd><dt>Policy reference</dt><dd><code>{event?.envelope.policy_ref || 'none'}</code></dd><dt>Parent link</dt><dd><code>{short(event?.parent_event_hash)}</code></dd><dt>Redaction</dt><dd>{event?.envelope.redaction_status || 'unverified'}</dd></dl><div className="decision-trace-advisory"><div className="memory-block-header"><h4>Jev advisory</h4><span className={`memory-badge ${event?.advisory?.recommended_escalation ? 'warn' : 'good'}`}>{event?.advisory?.recommended_escalation ? 'Escalation suggested' : 'Continue suggested'}</span></div>{Object.entries(event?.advisory?.transition_probabilities || {}).map(([label, value]) => <div className="decision-probability" key={label}><span>{label}</span><b>{Math.round(value * 100)}%</b><i><em style={{ width: `${(value / maxProbability) * 100}%` }} /></i></div>)}<p className="memory-warning"><LockKeyhole size={14} /> Observational estimate only. Causal claim: false. Jev cannot authorize or override Shield enforcement.</p></div></article>
            </div>
            <p className="decision-trace-disclaimer">{trace.disclaimer || 'Observational correlation only; probabilities do not prove causality or execution.'}</p>
        </>}
    </section>;
}
