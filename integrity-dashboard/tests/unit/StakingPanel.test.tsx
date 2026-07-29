import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StakingPanel } from '../../src/components/tabs/StakingPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { oracle } from '../../src/services/oracle';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getAgent: vi.fn(),
  },
}));

const mockAgent = {
  eth_address: '0x123',
  alias: 'Test Staker',
  staked_itk: 10000,
};

const mockWait = vi.fn();
const mockApprove = vi.fn().mockResolvedValue({ wait: mockWait });
const mockAllowance = vi.fn();
const mockStake = vi.fn().mockResolvedValue({ wait: mockWait });

vi.mock('ethers', () => {
  return {
    ethers: {
      BrowserProvider: vi.fn().mockImplementation(function() { return {
        getSigner: vi.fn().mockResolvedValue({}),
      }}),
      Contract: vi.fn().mockImplementation(function(address) {
        if (address === '0xSlasherAddress') {
          return {
            stake: mockStake,
          };
        }
        return {
          allowance: mockAllowance,
          approve: mockApprove,
        };
      }),
      parseEther: vi.fn().mockImplementation((val) => BigInt(val) * 10n**18n),
      formatEther: vi.fn().mockImplementation((val) => (Number(val) / 1e18).toString()),
    }
  };
});

describe('StakingPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).ethereum = {};
  });

  it('renders initial state', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<StakingPanel />);
    expect(screen.getByText(/Total ITK Staked/i)).toBeInTheDocument();
    expect(screen.getByText(/Please select an agent to manage bonds/i)).toBeInTheDocument();
  });

  it('renders agent stake when selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<StakingPanel />);
    expect(screen.getByText('10,000')).toBeInTheDocument();
    expect(screen.getByLabelText(/Amount to Stake/i)).toBeInTheDocument();
  });

  it('stakes successfully with window.ethereum and low allowance', async () => {
    const addToastMock = vi.fn();
    const fetchDataMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: fetchDataMock,
      walletAddress: '0xWallet'
    });

    (oracle.getAgent as unknown).mockResolvedValue({
      primitives: {
        slasher: '0xSlasherAddress',
      }
    });

    mockAllowance.mockResolvedValue(BigInt(0)); // less than amount (e.g. 500 * 10^18)

    render(<StakingPanel />);
    
    const input = screen.getByLabelText(/Amount to Stake/i);
    fireEvent.change(input, { target: { value: '500' } });
    
    const stakeBtn = screen.getByRole('button', { name: /Commit Bond/i });
    fireEvent.click(stakeBtn);

    await waitFor(() => {
      expect(mockAllowance).toHaveBeenCalled();
      expect(mockApprove).toHaveBeenCalled();
      expect(mockStake).toHaveBeenCalled();
      expect(mockWait).toHaveBeenCalledTimes(2); // one for approve, one for stake
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Bonded 500 $ITK'));
      expect(fetchDataMock).toHaveBeenCalled();
    });
  });

  it('handles staking errors during primitive resolution', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      walletAddress: '0xWallet'
    });

    (oracle.getAgent as unknown).mockResolvedValue({
      primitives: null // no Slasher clone
    });

    render(<StakingPanel />);
    
    const input = screen.getByLabelText(/Amount to Stake/i);
    fireEvent.change(input, { target: { value: '500' } });
    
    const stakeBtn = screen.getByRole('button', { name: /Commit Bond/i });
    fireEvent.click(stakeBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', expect.stringContaining('This agent has no deployed Slasher clone yet'));
    });
  });
});
