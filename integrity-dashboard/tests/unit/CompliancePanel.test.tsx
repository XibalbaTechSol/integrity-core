import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { CompliancePanel } from '../../src/components/tabs/CompliancePanel';
import { useDashboard } from '../../src/context/useDashboard';
import { oracle } from '../../src/services/oracle';
import { mockDashboardContext } from './test-utils';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getCompliance: vi.fn(),
    getAuditLog: vi.fn(),
  },
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
    (oracle.getCompliance as any).mockResolvedValue({ is_compliant: true, vertical: 'finance' });
    (oracle.getAuditLog as any).mockResolvedValue([]);
  });

  it('renders "Select an agent" when no agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<CompliancePanel />);
    expect(screen.getAllByText(/Select an agent/i)[0]).toBeInTheDocument();
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

  it('renders audit trail events from oracle', async () => {
    (oracle.getAuditLog as any).mockResolvedValue([
      {
        id: 'evt-1',
        event_type: 'bcc_check',
        decision: 'allow',
        reason_code: 'COMPLIANT',
        detail: 'Automated KYC refresh completed',
        created_at: '2025-01-01T00:00:00Z',
      },
      {
        id: 'evt-2',
        event_type: 'sla_audit',
        decision: 'deny',
        reason_code: 'SLA_VIOLATION',
        detail: 'SLA Contract audited',
        created_at: '2025-01-02T00:00:00Z',
      },
    ]);

    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CompliancePanel />);

    await waitFor(() => {
      expect(screen.getAllByText(/Automated KYC refresh completed/i)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/SLA Contract audited/i)[0]).toBeInTheDocument();
    });
  });
});
