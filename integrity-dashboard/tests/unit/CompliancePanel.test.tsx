import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CompliancePanel } from '../../src/components/tabs/CompliancePanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

const mockAgent = {
  eth_address: '0x123',
  alias: 'Test Agent',
  compliance_score: 95,
  verification_tier: 2,
};

describe('CompliancePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "Select an agent" when no agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<CompliancePanel />);
    expect(screen.getByText(/Select an agent/i)).toBeInTheDocument();
  });

  it('renders compliance scorecard when agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CompliancePanel />);
    expect(screen.getByText('95')).toBeInTheDocument();
    expect(screen.getAllByText(/Verified Tier 2/i)[0]).toBeInTheDocument();
  });

  it('renders audit trail events', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CompliancePanel />);
    expect(screen.getAllByText(/Automated KYC refresh completed/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/SLA Contract audited/i)[0]).toBeInTheDocument();
  });
});
