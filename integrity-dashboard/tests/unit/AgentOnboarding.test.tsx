import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AgentOnboarding } from '../../src/components/ui/AgentOnboarding';
import axios from 'axios';
import { ethers } from 'ethers';
import { getToken } from '../../src/services/userapi';

vi.mock('axios');
vi.mock('../../src/services/userapi', () => ({
  getToken: vi.fn(() => 'mock_jwt_token'),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  userapi: { listApiKeys: vi.fn().mockResolvedValue([]), createApiKey: vi.fn(), revokeApiKey: vi.fn() },
}));
vi.mock('ethers', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as any),
    ethers: {
      Wallet: {
        createRandom: vi.fn(() => ({
          address: '0xMockWalletAddress123',
          privateKey: '0xMockPrivateKey123'
        }))
      }
    }
  };
});

// Mock browser ethereum for connect wallet
const mockEthereum = {
  request: vi.fn(),
};

Object.defineProperty(window, 'ethereum', {
  value: mockEthereum,
});

describe('AgentOnboarding', () => {
  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();
    (getToken as any).mockReturnValue('mock_jwt_token');
    window.alert = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <AgentOnboarding isOpen={false} onClose={mockOnClose} onSuccess={mockOnSuccess} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders Step 1 initially and handles input', async () => {
    render(<AgentOnboarding isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />);
    
    expect(screen.getByText(/Agent Onboarding/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 1 of 4/i)).toBeInTheDocument();

    const aliasInput = screen.getByPlaceholderText(/e.g. Neon Centurion/i);
    fireEvent.change(aliasInput, { target: { value: 'My Test Agent' } });
    expect(aliasInput).toHaveValue('My Test Agent');

    const handleInput = screen.getByPlaceholderText(/e.g. xibalba/i);
    fireEvent.change(handleInput, { target: { value: 'testhandle' } });
    expect(handleInput).toHaveValue('testhandle');
  });

  it('can auto-fill demo data', () => {
    render(<AgentOnboarding isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />);
    
    fireEvent.click(screen.getByText(/Demo Auto-fill/i));
    
    const aliasInput = screen.getByPlaceholderText(/e.g. Neon Centurion/i);
    expect((aliasInput as HTMLInputElement).value).toContain('Demo Sentinel');
  });

  it('can generate sovereign wallet', () => {
    render(<AgentOnboarding isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />);
    
    fireEvent.click(screen.getByText(/Generate New/i));
    
    expect(screen.getByText(/New Sovereign Wallet Generated/i)).toBeInTheDocument();
    const controllerInput = screen.getByPlaceholderText(/0x\.\.\./i);
    expect((controllerInput as HTMLInputElement).value).toBe('0xMockWalletAddress123');
  });

  it('can connect metamask wallet', async () => {
    mockEthereum.request.mockResolvedValueOnce(['0x1234567890abcdef1234567890abcdef12345678']);
    
    render(<AgentOnboarding isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />);
    
    fireEvent.click(screen.getByText(/Connect Wallet/i));
    
    await waitFor(() => {
      const controllerInput = screen.getByPlaceholderText(/0x\.\.\./i);
      expect((controllerInput as HTMLInputElement).value).toBe('0x1234567890abcdef1234567890abcdef12345678');
    });
  });

  it('navigates through steps and deploys successfully', async () => {
    (axios.post as any).mockResolvedValueOnce({ data: { success: true } });
    
    render(<AgentOnboarding isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />);
    
    // Fill required data to continue
    fireEvent.click(screen.getByText(/Demo Auto-fill/i));

    // Next step (to step 2)
    const continueBtn = screen.getByRole('button', { name: /Continue/i });
    
    await waitFor(() => {
      expect(continueBtn).not.toBeDisabled();
    });
    
    fireEvent.click(continueBtn);
    
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Initialize Sovereign Contract/i })).toBeInTheDocument();
    });

    // Deploy (Step 2 -> Step 3)
    fireEvent.click(screen.getByRole('button', { name: /Initialize Sovereign Contract/i }));
    expect(screen.getByText(/Anchoring to Base Sepolia\.\.\./i)).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText(/SDK Orchestration/i)).toBeInTheDocument();
    }, { timeout: 4000 });

    // Next step (to step 4)
    const continueBtnStep3 = screen.getByRole('button', { name: /Continue/i });
    fireEvent.click(continueBtnStep3);
    
    await waitFor(() => {
      expect(screen.getByText(/Agent Sovereign\./i)).toBeInTheDocument();
    });

    // Finalize
    fireEvent.click(screen.getByRole('button', { name: /Enter Command Center/i }));
    
    expect(mockOnSuccess).toHaveBeenCalled();
    expect(mockOnClose).toHaveBeenCalled();
  }, 15000);
});
