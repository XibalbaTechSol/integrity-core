import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { GovernancePanel } from '../../src/components/tabs/GovernancePanel';
import { oracle } from '../../src/services/oracle';

// `deployed` starts as null (unknown) and is only resolved once
// `oracle.getGovernanceProposals()` settles, so neither branch is on screen during the
// first render — the old version of this test asserted the not-live copy synchronously
// against an unmocked real fetch, and could only ever fail.
vi.mock('../../src/services/oracle', () => ({
  oracle: { getGovernanceProposals: vi.fn() },
}));

describe('GovernancePanel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows the honest not-live state when no Governance contract is deployed', async () => {
    // The oracle reports a missing singleton as a 400 (see PRODUCTION_GAPS/wiki: it is a
    // deployment-shape fact, not a transient failure); the panel degrades to not-live.
    (oracle.getGovernanceProposals as any).mockRejectedValue(
      Object.assign(new Error('Oracle request failed: 400 /v1/governance/proposals'), { status: 400 }),
    );

    render(<GovernancePanel />);

    await waitFor(() => {
      expect(screen.getByText('On-Chain Governance — Not Yet Live')).toBeInTheDocument();
    });
    expect(screen.getByText('No Governance contract is deployed yet.')).toBeInTheDocument();
  });

  it('renders live proposals when the contract is deployed', async () => {
    (oracle.getGovernanceProposals as any).mockResolvedValue([
      {
        id: 1,
        proposer: '0x0000000000000000000000000000000000000001',
        target: '0x0000000000000000000000000000000000000002',
        value: '0',
        description: 'Raise the minimum bonded stake',
        state: 'Active',
        for_votes: '1000000000000000000',
        against_votes: '0',
        start_time: 0,
        end_time: 0,
      },
    ]);

    render(<GovernancePanel />);

    await waitFor(() => {
      expect(screen.getByText('Raise the minimum bonded stake')).toBeInTheDocument();
    });
    expect(screen.getByText('Active')).toBeInTheDocument();
    // The not-live panel must not also be showing.
    expect(screen.queryByText('On-Chain Governance — Not Yet Live')).not.toBeInTheDocument();
  });
});
