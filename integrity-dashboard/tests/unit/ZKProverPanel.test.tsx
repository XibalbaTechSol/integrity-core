import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ZKProverPanel } from '../../src/components/tabs/ZKProverPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { oracle } from '../../src/services/oracle';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getAis: vi.fn(),
  },
}));

const mockAgent = {
  eth_address: '0x1234567890abcdef',
  alias: 'Test Prover',
};

describe('ZKProverPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders select agent message when no agent selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<ZKProverPanel />);
    expect(screen.getByText('Select an agent to view its live ZK boost.')).toBeInTheDocument();
  });

  it('renders loading state and then loads active boost status', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    (oracle.getAis as unknown).mockResolvedValue({
      zk_proof_verified: true,
      zk_boost: 1.15,
      onchain_zk_boost_consistent: true,
    });

    render(<ZKProverPanel />);
    
    // Check loading indicator first
    expect(screen.getByText('Reading chain state…')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Active bb-verified reputation boost')).toBeInTheDocument();
      expect(screen.getByText('1.15×')).toBeInTheDocument();
      expect(screen.getByText('Yes')).toBeInTheDocument();
      expect(screen.getByText('Consistent (oracle boost matches on-chain)')).toBeInTheDocument();
    });
  });

  it('renders no boost state when ZK proof not verified', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    (oracle.getAis as unknown).mockResolvedValue({
      zk_proof_verified: false,
      zk_boost: 1.0,
      onchain_zk_boost_consistent: false,
    });

    render(<ZKProverPanel />);

    await waitFor(() => {
      expect(screen.getByText('No active ZK boost')).toBeInTheDocument();
      expect(screen.getByText('1.00×')).toBeInTheDocument();
      expect(screen.getByText('No')).toBeInTheDocument();
      expect(screen.getByText('Mismatch — oracle boost not confirmed on-chain')).toBeInTheDocument();
    });
  });
});
