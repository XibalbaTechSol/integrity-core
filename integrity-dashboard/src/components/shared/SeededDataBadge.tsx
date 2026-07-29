import { FlaskConical } from 'lucide-react';

/**
 * Marks a section/page as showing seeded/simulated content rather than
 * real oracle/chain data — e.g. because it would need backend infra this
 * Dashboard pass deliberately doesn't build yet (WSS streaming, OTLP ingestion,
 * a TSDB — see PRODUCTION_GAPS.md). Exists so "still mock" and "now real"
 * are visually distinguishable, instead of silently mixed the way this
 * app's data used to be before this pass.
 */
export const SeededDataBadge = ({ label = 'Seeded demo data' }: { label?: string }) => (
    <span
        style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '3px 10px', background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid var(--warning)', borderRadius: '999px',
            fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.08em',
            color: 'var(--warning)', textTransform: 'uppercase',
        }}
        title="This panel shows simulated content, not live oracle/chain data."
    >
        <FlaskConical size={11} />
        {label}
    </span>
);
