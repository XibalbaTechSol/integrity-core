import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClaimAgentModal } from '../../src/components/tabs/ClaimAgentModal';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { ethers } from 'ethers';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

// Mock ethers — the component uses ethers.isAddress, BrowserProvider, Contract
vi.mock('ethers', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as any),
    ethers: {
      ...(actual as any).ethers,
      isAddress: vi.fn(),
      BrowserProvider: vi.fn(),
      Contract: vi.fn(),
    },
  };
});

vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getAgent: vi.fn(),
    register: vi.fn(),
  },
}));

describe('ClaimAgentModal', () => {
  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();
  const mockAddToast = vi.fn();
  const mockConnectWallet = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useDashboard as any).mockReturnValue({
      ...mockDashboardContext,
      addToast: mockAddToast,
      walletAddress: '0xowner123',
      connectWallet: mockConnectWallet,
    });
    // Mock window.ethereum
    (window as any).ethereum = {
      request: vi.fn(),
    };
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ClaimAgentModal isOpen={false} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal content when isOpen is true', () => {
    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    expect(screen.getByText('Claim Existing Agent')).toBeInTheDocument();
    expect(screen.getByText('SovereignAgent Address')).toBeInTheDocument();
  });

  it('validates ethereum address format', async () => {
    (ethers.isAddress as any).mockReturnValue(false);

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: 'invalid-address' } });
    
    const button = screen.getByText('Verify Control On-Chain');
    fireEvent.click(button);

    expect(mockAddToast).toHaveBeenCalledWith('error', 'Please enter a valid Ethereum address');
  });

  it('verifies on-chain control and moves to step 2', async () => {
    (ethers.isAddress as any).mockReturnValue(true);

    const mockContract = {
      agentDID: vi.fn().mockResolvedValue('did:integrity:test123'),
      DEFAULT_ADMIN_ROLE: vi.fn().mockResolvedValue('0x00'),
      hasRole: vi.fn().mockResolvedValue(true),
    };
    (ethers.BrowserProvider as any).mockImplementation(function() { return {}; });
    (ethers.Contract as any).mockImplementation(function() { return mockContract; });

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    
    const button = screen.getByText('Verify Control On-Chain');
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('AGENT DID')).toBeInTheDocument();
      expect(screen.getByText('did:integrity:test123')).toBeInTheDocument();
      expect(screen.getByText(/Your wallet holds this agent's controller role/i)).toBeInTheDocument();
    });
  });

  it('shows not-controller message when wallet lacks admin role', async () => {
    (ethers.isAddress as any).mockReturnValue(true);

    const mockContract = {
      agentDID: vi.fn().mockResolvedValue('did:integrity:test123'),
      DEFAULT_ADMIN_ROLE: vi.fn().mockResolvedValue('0x00'),
      hasRole: vi.fn().mockResolvedValue(false),
    };
    (ethers.BrowserProvider as any).mockImplementation(function() { return {}; });
    (ethers.Contract as any).mockImplementation(function() { return mockContract; });

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    
    fireEvent.click(screen.getByText('Verify Control On-Chain'));

    await waitFor(() => {
      expect(screen.getByText(/Connected wallet is not the controller/i)).toBeInTheDocument();
    });
  });

  it('handles errors during verification', async () => {
    (ethers.isAddress as any).mockReturnValue(true);

    const mockContract = {
      agentDID: vi.fn().mockRejectedValue(new Error('execution reverted')),
      DEFAULT_ADMIN_ROLE: vi.fn(),
      hasRole: vi.fn(),
    };
    (ethers.BrowserProvider as any).mockImplementation(function() { return {}; });
    (ethers.Contract as any).mockImplementation(function() { return mockContract; });

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    
    fireEvent.click(screen.getByText('Verify Control On-Chain'));

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('error', expect.stringContaining('Not a resolvable SovereignAgent'));
    });
  });
});
