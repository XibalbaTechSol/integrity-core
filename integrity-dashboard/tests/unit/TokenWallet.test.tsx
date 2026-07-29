import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TokenWallet } from '../../src/components/ui/TokenWallet';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { userapi } from '../../src/services/userapi';
import { ethers } from 'ethers';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

// TokenWallet reads the custodial balance through `services/userapi` (a fetch client),
// not axios — mocking axios asserted against a call the component never makes.
vi.mock('../../src/services/userapi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/services/userapi')>()),
  // `fetchProfileData` short-circuits on `!getToken()` — the custodial app-wallet is only
  // read when there is a real userapi session, so these tests must simulate one or the
  // getWallet assertion below is asserting signed-out behavior.
  getToken: vi.fn(() => 'test-jwt'),
  userapi: { getWallet: vi.fn(), walletTransfer: vi.fn() },
}));

vi.mock('ethers', () => {
  return {
    ethers: {
      BrowserProvider: vi.fn().mockImplementation(function() {
        return {
          listAccounts: vi.fn().mockResolvedValue([{ address: '0xmockBrowserAddress' }]),
          getSigner: vi.fn().mockResolvedValue({}),
        };
      }),
      JsonRpcProvider: vi.fn().mockImplementation(function() {
        return {};
      }),
      Contract: vi.fn().mockImplementation(function() {
        return {
          balanceOf: vi.fn().mockResolvedValue(1000n),
          filters: { Transfer: vi.fn() },
          queryFilter: vi.fn().mockResolvedValue([]),
          transfer: vi.fn().mockResolvedValue({ wait: vi.fn().mockResolvedValue(true) }),
        };
      }),
      formatEther: vi.fn().mockReturnValue('1.0'),
      parseEther: vi.fn().mockReturnValue(1000n),
    },
  };
});

vi.mock('../../src/firebase', () => ({
  auth: {
    currentUser: {
      getIdToken: vi.fn().mockResolvedValue('mock-token'),
    },
  },
}));

describe('TokenWallet', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useDashboard as any).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: { eth_address: '0xagent123', alias: 'Agent 1' },
    });
    
    (userapi.getWallet as any).mockResolvedValue({
      balance: 50,
      app_wallet_address: '0xappwallet',
    });

    (window as any).ethereum = undefined;
  });

  it('renders token wallet basic components', async () => {
    render(<TokenWallet />);
    
    // Check main title rendering via "Total Balance" or "Protocol_L2_Vault"
    // Since balance is loaded async, it might first show Total Balance and 0.00
    expect(screen.getByText(/Total Balance|Protocol_L2_Vault/i)).toBeInTheDocument();
    
    // It should load the agent address from context
    expect(screen.getByText(/Agent Agent 1: 0xagent123\.\.\./i)).toBeInTheDocument();

    await waitFor(() => {
      expect(userapi.getWallet).toHaveBeenCalled();
    });
  });

  it('switches between assets and activity tabs', async () => {
    render(<TokenWallet />);
    
    // Initially on assets tab
    expect(screen.getByText('Integrity Token')).toBeInTheDocument();
    
    const activityTab = screen.getByRole('button', { name: /activity/i });
    fireEvent.click(activityTab);
    
    // Wait for the tab to switch
    await waitFor(() => {
      expect(screen.getByText('No transaction history found.')).toBeInTheDocument();
    });
  });

  it('opens and closes transaction modals', async () => {
    render(<TokenWallet />);
    
    // Wait for initial render to finish fetching
    await waitFor(() => {
      expect(userapi.getWallet).toHaveBeenCalled();
    });

    const sendButton = screen.getByText('Send');
    fireEvent.click(sendButton);
    
    expect(screen.getByText('Initiate Transfer')).toBeInTheDocument();
    
    // Find the close button which is the first button in the modal
    const initiateHeader = screen.getByText('Initiate Transfer');
    const modalContainer = initiateHeader.closest('.enterprise-card');
    const closeButton = modalContainer?.querySelector('button');
    
    if (closeButton) {
      fireEvent.click(closeButton);
    }
    
    await waitFor(() => {
      expect(screen.queryByText('Initiate Transfer')).not.toBeInTheDocument();
    });
  });
});
