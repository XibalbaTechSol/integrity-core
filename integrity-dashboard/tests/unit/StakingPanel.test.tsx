import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StakingPanel } from '../../src/components/tabs/StakingPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.stubEnv('VITE_IS_PRODUCTION', 'true');

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    stake: vi.fn(),
  },
}));

const mockAgent = {
  eth_address: '0x123',
  alias: 'Test Staker',
  staked_itk: 10000,
};

const mockWait = vi.fn();
const mockApprove = vi.fn().mockResolvedValue({ wait: mockWait });
const mockAllowance = vi.fn().mockImplementation(() => { console.log('MOCK ALLOWANCE CALLED'); return BigInt(0); });

vi.mock('ethers', () => {
  return {
    ethers: {
      BrowserProvider: vi.fn().mockImplementation(function() { return {
        getSigner: vi.fn().mockResolvedValue({}),
      }}),
      Contract: vi.fn().mockImplementation(function() { return {
        allowance: mockAllowance,
        approve: mockApprove,
      }}),
      parseEther: vi.fn().mockImplementation((val) => BigInt(val) * 10n**18n),
    }
  };
});

describe('StakingPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).IS_TEST_ENV = true;
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
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: vi.fn(),
      walletAddress: '0xWallet'
    });

    mockAllowance.mockResolvedValue(BigInt(0)); // less than amount
    (api.stake as unknown).mockResolvedValue({ status: 'success' });

    render(<StakingPanel />);
    
    const input = screen.getByLabelText(/Amount to Stake/i);
    fireEvent.change(input, { target: { value: '500' } });
    
    const stakeBtn = screen.getByRole('button', { name: /Commit Bond/i });
    fireEvent.click(stakeBtn);

    await waitFor(() => {
      expect(mockAllowance).toHaveBeenCalled();
      expect(mockApprove).toHaveBeenCalled();
      expect(mockWait).toHaveBeenCalled();
      expect(api.stake).toHaveBeenCalledWith(mockAgent.eth_address, 500);
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Successfully staked'));
    });
  });

  it('handles staking errors', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: vi.fn(),
      walletAddress: '0xWallet'
    });

    mockAllowance.mockRejectedValue(new Error('Contract Error'));

    render(<StakingPanel />);
    
    const input = screen.getByLabelText(/Amount to Stake/i);
    fireEvent.change(input, { target: { value: '500' } });
    
    const stakeBtn = screen.getByRole('button', { name: /Commit Bond/i });
    fireEvent.click(stakeBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', expect.stringContaining('Staking failed'));
    });
  });
});

  it('stakes successfully without window.ethereum', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: vi.fn(),
      walletAddress: '0xWallet'
    });

    (window as any).ethereum = undefined;
    (api.stake as unknown).mockResolvedValue({ status: 'success' });

    render(<StakingPanel />);
    
    const input = screen.getByLabelText(/Amount to Stake/i);
    fireEvent.change(input, { target: { value: '500' } });
    
    const stakeBtn = screen.getByRole('button', { name: /Commit Bond/i });
    fireEvent.click(stakeBtn);

    await waitFor(() => {
      expect(api.stake).toHaveBeenCalledWith(mockAgent.eth_address, 500);
    });
  });
