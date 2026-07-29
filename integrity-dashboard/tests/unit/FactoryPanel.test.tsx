import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FactoryPanel } from '../../src/components/tabs/FactoryPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { oracle } from '../../src/services/oracle';
import { executeAsAgent } from '../../src/chain/markets';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    resolveSovereignAgent: vi.fn(),
    listMarkets: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../src/chain/markets', () => ({
  executeAsAgent: vi.fn(),
  MARKET_FACTORY_ABI: [],
}));

const mockAgent = {
  eth_address: '0x1234567890abcdef',
  alias: 'Test Factory',
};

const mockSigner = {};

vi.mock('ethers', () => {
  return {
    ethers: {
      BrowserProvider: vi.fn().mockImplementation(function() { return {
        getSigner: vi.fn().mockResolvedValue(mockSigner),
      }}),
      Interface: vi.fn().mockImplementation(function() { return {
        encodeFunctionData: vi.fn().mockReturnValue('0xencoded'),
        parseLog: vi.fn().mockReturnValue({ name: 'MarketDeployed', args: { market: '0xnewmarket' } }),
      }}),
    }
  };
});

describe('FactoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).ethereum = {};
    (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');
  });

  it('renders initial state', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<FactoryPanel />);
    expect(screen.getByText(/Contract Logic Template/i)).toBeInTheDocument();
  });

  it('changes contract template when type is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const select = screen.getByLabelText(/Contract Type/i);
    fireEvent.change(select, { target: { value: 'Escrow' } });

    expect(screen.getAllByText(/AutonomousEscrow/i)[0]).toBeInTheDocument();
  });

  it('deploys a market contract successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      walletAddress: '0xwallet',
    });

    (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');
    (executeAsAgent as unknown).mockResolvedValue({
      logs: [{}],
      hash: '0xtxhash',
      blockNumber: 12345,
      gasUsed: 50000n,
    });

    render(<FactoryPanel />);

    // Wait for the asynchronous resolveSovereignAgent state to update
    await waitFor(() => {
      expect(oracle.resolveSovereignAgent).toHaveBeenCalled();
    });
    
    // Fill in the required question
    const input = screen.getByLabelText(/Question/i);
    fireEvent.change(input, { target: { value: 'Will this test succeed?' } });

    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    await waitFor(() => {
      expect(executeAsAgent).toHaveBeenCalled();
      expect(addToastMock).toHaveBeenCalledWith('success', 'Market deployed and owned by your agent.');
    }, { timeout: 3000 });
  });

  it('handles deployment failure', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      walletAddress: '0xwallet',
    });

    (oracle.resolveSovereignAgent as unknown).mockResolvedValue('0xsovereignAgentAddress');
    (executeAsAgent as unknown).mockRejectedValue(new Error('Out of gas'));

    render(<FactoryPanel />);

    // Wait for the asynchronous resolveSovereignAgent state to update
    await waitFor(() => {
      expect(oracle.resolveSovereignAgent).toHaveBeenCalled();
    });
    
    // Fill in the required question
    const input = screen.getByLabelText(/Question/i);
    fireEvent.change(input, { target: { value: 'Will this fail?' } });

    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', expect.stringContaining('Out of gas'));
    }, { timeout: 3000 });
  });

  it('fails deploy if no agent selected', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
      addToast: addToastMock,
      walletAddress: '0xwallet',
    });

    render(<FactoryPanel />);
    
    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    expect(addToastMock).toHaveBeenCalledWith('error', 'Select an agent first');
    expect(executeAsAgent).not.toHaveBeenCalled();
  });
});
