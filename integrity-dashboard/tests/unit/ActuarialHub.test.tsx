import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ActuarialHub } from '../../src/components/tabs/ActuarialHub';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { oracle } from '../../src/services/oracle';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    listMarkets: vi.fn(),
    resolveSovereignAgent: vi.fn(),
    // Stability mode loads real provider benchmarks from GET /v1/benchmarks on mount;
    // omitting this from the mock made the component throw before rendering anything.
    getBenchmarks: vi.fn().mockResolvedValue([]),
  },
}));

const mockAgent = {
  agent_id: 'agent-123',
  eth_address: 'did:integrity:0x123',
  alias: 'Test Agent',
};

const mockMarkets = [
  {
    address: '0xmarketAddress',
    creator: '0xcreatorAddress',
    question: 'Will this test run successfully?',
    outcome_count: 2,
    min_ais_to_enter: 500,
    resolve_deadline: Math.floor(Date.now() / 1000) + 3600,
    resolved: false,
    winning_outcome: 0,
    total_staked: '1000000000000000000000', // 1000 ITK
    outcome_staked: ['600000000000000000000', '400000000000000000000'],
  }
];

describe('ActuarialHub', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Stability Mode', () => {
    it('renders stability pending message', () => {
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: null,
      });

      render(<ActuarialHub mode="stability" />);
      expect(screen.getByText('Model Stability Leaderboard')).toBeInTheDocument();
      expect(screen.getByText('No benchmark telemetry yet.')).toBeInTheDocument();
    });
  });

  describe('Markets Mode', () => {
    it('renders markets and active market list', async () => {
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
      });

      (oracle.listMarkets as unknown).mockResolvedValue(mockMarkets);
      (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');

      render(<ActuarialHub mode="markets" />);

      expect(screen.getByText('Deploy a Market')).toBeInTheDocument();
      expect(screen.getByText('Live Markets')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText('Will this test run successfully?')).toBeInTheDocument();
        expect(screen.getByText('1,000 ITK')).toBeInTheDocument();
      });
    });
  });
});
