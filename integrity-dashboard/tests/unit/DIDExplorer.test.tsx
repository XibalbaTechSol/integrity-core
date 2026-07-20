import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DIDExplorer } from '../../src/components/ui/DIDExplorer';
import axios from 'axios';

vi.mock('axios');

describe('DIDExplorer', () => {
  const mockAgent = {
    eth_address: '0x123',
    alias: 'Test Agent',
    current_ais: 90,
    verification_tier: 2,
    xns_handle: 'test-agent'
  };

  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders nothing if agent is null', () => {
    const { container } = render(<DIDExplorer agent={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('fetches identity and renders DID view by default', async () => {
    (axios.get as any).mockResolvedValueOnce({ data: { id: 'did:xibalba:0x123', verificationMethod: [] } }) // did
                     .mockResolvedValueOnce({ data: { id: 'vc:123', credentialSubject: {} } }); // vc

    render(<DIDExplorer agent={mockAgent} />);
    
    // initially loading
    // expect(document.querySelector('.skeleton')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });

    expect(screen.getByText('did:xibalba:0x123')).toBeInTheDocument();
  });

  it('uses fallback if API fails', async () => {
    (axios.get as any).mockRejectedValue(new Error('Network error'));

    render(<DIDExplorer agent={mockAgent} />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });

    // fallback DID
    expect(screen.getByText('did:xibalba:0x123')).toBeInTheDocument();
  });

  it('can switch tabs', async () => {
    (axios.get as any).mockRejectedValue(new Error('Network error'));

    render(<DIDExplorer agent={mockAgent} />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });

    // switch to vc
    fireEvent.click(screen.getByRole('button', { name: /vc/i }));
    await waitFor(() => {
      expect(screen.getByText(/Verifiable Reputation Credential/i)).toBeInTheDocument();
    });

    // switch to raw
    fireEvent.click(screen.getByRole('button', { name: /raw/i }));
    await waitFor(() => {
      expect(screen.getByText(/"id": "did:xibalba:0x123"/)).toBeInTheDocument();
    });
  });
});
