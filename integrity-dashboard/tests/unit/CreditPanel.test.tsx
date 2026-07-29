import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreditPanel } from '../../src/components/tabs/CreditPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { oracle } from '../../src/services/oracle';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getCredit: vi.fn(),
    resolveSovereignAgent: vi.fn(),
  },
}));

const mockAgent = {
  agent_id: 'agent-123',
  eth_address: 'did:integrity:0x123',
  alias: 'Test Agent',
};

const mockCredit = {
  total_allocated: '10000000000000000000000', // 10,000 ITK
  active_allocations_count: 2,
};

const mockWait = vi.fn();
const mockApprove = vi.fn().mockResolvedValue({ wait: mockWait });
const mockAllowance = vi.fn();
const mockAllocate = vi.fn().mockResolvedValue({ wait: mockWait });

vi.mock('ethers', () => {
  return {
    ethers: {
      BrowserProvider: vi.fn().mockImplementation(function() { return {
        getSigner: vi.fn().mockResolvedValue({}),
        queryFilter: vi.fn().mockResolvedValue([]),
      }}),
      Contract: vi.fn().mockImplementation(function() {
        // Return all methods to satisfy both ITK token and A2ACapitalPool contracts
        return {
          allowance: mockAllowance,
          approve: mockApprove,
          allocate: mockAllocate,
          queryFilter: vi.fn().mockResolvedValue([]),
          allocations: vi.fn().mockResolvedValue({
            amount: 0n,
            minAisToMaintain: 0n,
            status: 0,
            createdAt: 0n,
          }),
          filters: {
            Allocated: vi.fn(),
          }
        };
      }),
      parseEther: vi.fn().mockImplementation((val) => BigInt(val) * 10n**18n),
      formatEther: vi.fn().mockImplementation((val) => (Number(val) / 1e18).toString()),
    }
  };
});

describe('CreditPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).ethereum = {};
  });

  it('renders select agent message when no agent selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<CreditPanel />);
    expect(screen.getAllByText(/Select an agent/i)[0]).toBeInTheDocument();
  });

  it('renders capital allocation layout when agent selected', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      walletAddress: '0xallocator',
    });

    (oracle.getCredit as unknown).mockResolvedValue(mockCredit);
    (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');

    render(<CreditPanel />);

    expect(screen.getByText('Allocate Capital')).toBeInTheDocument();
    expect(screen.getByLabelText(/Amount to Escrow/i)).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('10,000')).toBeInTheDocument();
    });
  });

  it('allocates successfully with window.ethereum and low allowance', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      walletAddress: '0xallocator',
    });

    (oracle.getCredit as unknown).mockResolvedValue(mockCredit);
    (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');
    mockAllowance.mockResolvedValue(BigInt(0));

    render(<CreditPanel />);

    // Wait for the asynchronous resolveSovereignAgent state to update
    await waitFor(() => {
      expect(oracle.resolveSovereignAgent).toHaveBeenCalled();
    });

    const allocBtn = screen.getByRole('button', { name: /Escrow Capital/i });
    fireEvent.click(allocBtn);

    await waitFor(() => {
      expect(mockAllowance).toHaveBeenCalled();
      expect(mockApprove).toHaveBeenCalled();
      expect(mockAllocate).toHaveBeenCalled();
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Allocated'));
    });
  });
});
