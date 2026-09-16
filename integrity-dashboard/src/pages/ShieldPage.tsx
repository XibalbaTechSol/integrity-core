import { SystemSummaryCard } from '../components/shared/SystemSummaryCard';

export default function ShieldPage() {
  return (
    <div style={{ padding: 'var(--space-4)' }}>
      <h1 style={{ margin: '0 0 var(--space-4)' }}>Shield control</h1>
      <SystemSummaryCard system="shield" />
    </div>
  );
}
