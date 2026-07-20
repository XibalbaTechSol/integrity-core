import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ClaimAgentModal } from '../../src/components/tabs/ClaimAgentModal';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    generateClaimChallenge: vi.fn(),
    claimOwnership: vi.fn(),
  }
}));

describe('ClaimAgentModal', () => {
  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();
  const mockAddToast = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useDashboard as any).mockReturnValue({
      ...mockDashboardContext,
      addToast: mockAddToast,
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
    expect(screen.getByText('Agent Ethereum Address')).toBeInTheDocument();
  });

  it('validates ethereum address format', async () => {
    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: 'invalid-address' } });
    
    const button = screen.getByText('Generate Ownership Challenge');
    fireEvent.click(button);

    expect(mockAddToast).toHaveBeenCalledWith('error', 'Please enter a valid Ethereum address');
    expect(api.generateClaimChallenge).not.toHaveBeenCalled();
  });

  it('generates challenge and moves to step 2 on valid address', async () => {
    const mockChallenge = 'challenge-12345';
    (api.generateClaimChallenge as any).mockResolvedValueOnce(mockChallenge);

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    
    const button = screen.getByText('Generate Ownership Challenge');
    fireEvent.click(button);

    expect(screen.getByText(/Generating/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(api.generateClaimChallenge).toHaveBeenCalledWith('0x1234567890123456789012345678901234567890', '');
      expect(screen.getByText('OWNERSHIP CHALLENGE')).toBeInTheDocument();
      expect(screen.getByText(mockChallenge)).toBeInTheDocument();
    });
  });

  it('handles signature process via MetaMask', async () => {
    const mockChallenge = 'challenge-12345';
    const mockAccount = '0xowner';
    const mockSignature = '0xsig';

    (api.generateClaimChallenge as any).mockResolvedValueOnce(mockChallenge);
    ((window as any).ethereum.request as any).mockImplementation(({ method }: any) => {
      if (method === 'eth_requestAccounts') return Promise.resolve([mockAccount]);
      if (method === 'personal_sign') return Promise.resolve(mockSignature);
      if (method === 'eth_accounts') return Promise.resolve([mockAccount]);
      return Promise.resolve();
    });

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    // Step 1
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    fireEvent.click(screen.getByText('Generate Ownership Challenge'));

    // Wait for step 2
    await waitFor(() => {
      expect(screen.getByText('OWNERSHIP CHALLENGE')).toBeInTheDocument();
    });

    // Step 2 - Sign
    fireEvent.click(screen.getByText('Sign Challenge with MetaMask'));

    await waitFor(() => {
      expect(screen.getByText('Message Signed Successfully')).toBeInTheDocument();
    });

    // Step 2 - Claim
    (api.claimOwnership as any).mockResolvedValueOnce({});
    fireEvent.click(screen.getByText('Claim Agent Ownership'));

    await waitFor(() => {
      expect(api.claimOwnership).toHaveBeenCalledWith('0x1234567890123456789012345678901234567890', expect.objectContaining({
        challenge: mockChallenge,
        signature: mockSignature,
      }));
      expect(mockAddToast).toHaveBeenCalledWith('success', 'Agent successfully claimed and synchronized!');
      expect(mockOnSuccess).toHaveBeenCalled();
    });
  });

  it('handles errors during generation', async () => {
    (api.generateClaimChallenge as any).mockRejectedValueOnce(new Error('API Error'));

    render(
      <ClaimAgentModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    
    const input = screen.getByPlaceholderText('0x...');
    fireEvent.change(input, { target: { value: '0x1234567890123456789012345678901234567890' } });
    
    fireEvent.click(screen.getByText('Generate Ownership Challenge'));

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('error', 'Failed to generate challenge: API Error');
    });
  });
});
