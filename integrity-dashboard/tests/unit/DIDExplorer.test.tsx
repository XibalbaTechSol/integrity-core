import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DIDExplorer } from '../../src/components/ui/DIDExplorer';
import { oracle } from '../../src/services/oracle';

// DIDExplorer reads through `services/oracle`, which is a `fetch` client — NOT axios.
// These tests used to mock axios, which meant the mocks did nothing and the component
// issued real requests that 404'd. Mock the service the component actually calls.
vi.mock('../../src/services/oracle', () => ({
  oracle: {
    getAgent: vi.fn(),
    getAgentVc: vi.fn(),
    getAgentHandle: vi.fn(),
  },
}));

describe('DIDExplorer', () => {
  // `eth_address` carries the DID in this system (see DashboardProvider's mapOracleAgent),
  // so use a realistic DID here rather than an 0x address.
  const did = 'did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861';
  const mockAgent = {
    eth_address: did,
    alias: 'xibalba.integrity',
    current_ais: 800,
    verification_tier: 1,
  };

  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders nothing if agent is null', () => {
    const { container } = render(<DIDExplorer agent={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('fetches identity and renders the DID view by default', async () => {
    (oracle.getAgent as any).mockResolvedValue({
      id: did,
      did_document: { id: did, verificationMethod: [] },
    });
    (oracle.getAgentVc as any).mockResolvedValue({ id: 'vc:123', credentialSubject: {} });
    (oracle.getAgentHandle as any).mockResolvedValue({ did, handle: 'xibalba.integrity' });

    render(<DIDExplorer agent={mockAgent} />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });
    expect(screen.getByText(did)).toBeInTheDocument();
  });

  it('falls back to the agent DID when the oracle is unreachable', async () => {
    (oracle.getAgent as any).mockRejectedValue(new Error('Network error'));
    (oracle.getAgentVc as any).mockRejectedValue(new Error('Network error'));
    (oracle.getAgentHandle as any).mockRejectedValue(new Error('Network error'));

    render(<DIDExplorer agent={mockAgent} />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });
    // Already-qualified DIDs must never be re-wrapped into did:xibalba:did:integrity:…
    expect(screen.getByText(did)).toBeInTheDocument();
  });

  it('can switch between DID, VC and raw views', async () => {
    (oracle.getAgent as any).mockResolvedValue({ id: did, did_document: { id: did } });
    (oracle.getAgentVc as any).mockResolvedValue(null);
    (oracle.getAgentHandle as any).mockResolvedValue(null);

    render(<DIDExplorer agent={mockAgent} />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign Identity Explorer')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /vc/i }));
    await waitFor(() => {
      expect(screen.getByText(/Verifiable Reputation Credential/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /raw/i }));
    await waitFor(() => {
      expect(screen.getByText(new RegExp(`"id": "${did}"`))).toBeInTheDocument();
    });
  });
});
