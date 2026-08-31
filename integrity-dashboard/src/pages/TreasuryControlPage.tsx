import { Landmark } from 'lucide-react';
import { ControlHeader } from '../components/control/ControlHeader';
import { AgentRiskContext } from '../components/control/AgentRiskContext';
import FinancialsPage from './FinancialsPage';

export default function TreasuryControlPage() {
  return (
    <div className="control-page">
      <ControlHeader eyebrow="Economic control" title="Funds & Access" description="Manage agent ITK balances, stake, capital allocations, market positions, and contract allowances from one governed workspace." actions={<span className="control-state online"><Landmark size={12} /> Base Sepolia</span>} />
      <div className="control-page-body">
        <AgentRiskContext purpose="funds" />
        <FinancialsPage />
      </div>
    </div>
  );
}
