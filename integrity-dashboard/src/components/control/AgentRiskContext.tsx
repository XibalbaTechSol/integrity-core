import { useEffect, useState } from 'react';
import { Activity, BadgeCheck, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useDashboard } from '../../context/DashboardContext';
import { oracle, type AisResponse } from '../../services/oracle';

export function AgentRiskContext({ purpose }: { purpose: 'funds' | 'security' }) {
  const { selectedAgent } = useDashboard();
  const [ais, setAis] = useState<AisResponse | null>(null);

  useEffect(() => {
    if (!selectedAgent) { setAis(null); return; }
    let active = true;
    oracle.getAis(selectedAgent.id).then((value) => { if (active) setAis(value); }).catch(() => { if (active) setAis(null); });
    return () => { active = false; };
  }, [selectedAgent?.id]);

  const title = purpose === 'funds' ? 'Capital gate context' : 'Policy risk context';
  const Icon = purpose === 'funds' ? BadgeCheck : ShieldCheck;
  return (
    <section className="agent-risk-context" aria-label={title}>
      <div className="risk-context-title"><Icon size={16} /><div><strong>{title}</strong><small>{selectedAgent?.alias || selectedAgent?.name || 'No agent selected'}</small></div></div>
      <div><span><Activity size={12} /> AIS</span><strong>{ais?.ais.toFixed(1) ?? '—'}</strong></div>
      <div><span>Grounding</span><strong>{ais?.components.grounding.toFixed(0) ?? '—'}</strong></div>
      <div><span>Compliance</span><strong>{ais?.components.compliance.toFixed(0) ?? '—'}</strong></div>
      <div><span>ZK proof</span><strong className={ais?.zk_proof_verified ? 'good' : undefined}>{ais?.zk_proof_verified ? 'Verified' : 'None'}</strong></div>
      <div className="risk-context-note"><TriangleAlert size={13} /><span>{purpose === 'funds' ? 'Credit, markets, staking, and allowances remain subject to live AIS and contract policy.' : 'Use this live intelligence alongside Shield and Kernel evidence; AIS does not automatically authorize an action.'}</span></div>
    </section>
  );
}
