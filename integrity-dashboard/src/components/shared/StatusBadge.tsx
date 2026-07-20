import { getTier } from '../../types';

interface StatusBadgeProps {
  status?: string;
  ais?: number;
  type?: 'success' | 'warning' | 'danger' | 'info' | 'tier';
}

export function StatusBadge({ status, ais }: StatusBadgeProps) {
  if (ais !== undefined) {
    const tier = getTier(ais);
    return <span className={`badge badge-${tier.toLowerCase()}`}>Tier {tier}</span>;
  }
  
  if (status) {
    const s = status.toLowerCase();
    let badgeClass = 'badge-b'; // default gray-ish
    
    if (['active', 'passed', 'verified', 'deployed'].includes(s)) badgeClass = 'badge-aa'; // green
    if (['failed', 'rejected', 'defaulted', 'liquidated', 'terminated'].includes(s)) badgeClass = 'badge-c'; // red
    if (['pending', 'paused'].includes(s)) badgeClass = 'badge-a'; // yellow
    
    return <span className={`badge ${badgeClass}`}>{status}</span>;
  }
  
  return null;
}
