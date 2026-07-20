import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ZKProverPanel } from '../../src/components/tabs/ZKProverPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    generateZKProof: vi.fn(),
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

  it('renders initial state', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<ZKProverPanel />);
    expect(screen.getByText('Select an agent')).toBeInTheDocument();
    expect(screen.getByText('Generate a proof to view verification stats.')).toBeInTheDocument();
  });

  it('generates a ZK proof successfully', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: vi.fn(),
    });

    (api.generateZKProof as unknown).mockResolvedValue({
      proof_hash: '0xproof123',
      proof_data: '{"data": "mock"}'
    });

    render(<ZKProverPanel />);
    
    const generateBtn = screen.getByRole('button', { name: /Generate Proof/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText('Cryptographic Proof Verified')).toBeInTheDocument();
      expect(screen.getByText('0xproof123')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('handles fallback when api fails', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: vi.fn(),
    });

    (api.generateZKProof as unknown).mockRejectedValue(new Error('Offline'));

    render(<ZKProverPanel />);
    
    const generateBtn = screen.getByRole('button', { name: /Generate Proof/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText('Cryptographic Proof Verified')).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
