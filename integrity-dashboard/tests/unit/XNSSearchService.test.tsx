import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { XNSSearchService } from '../../src/components/ui/XNSSearchService';
import { oracle } from '../../src/services/oracle';

// These tests previously mocked axios and asserted calls to `/v1/identity/resolve` on the
// deleted `services/api.ts`. That surface no longer exists: the component resolves handles
// through the real on-chain XibalbaNameService via `oracle.resolveXns`, and loads agents
// via `oracle.getAgent` (a fetch client). Rewritten against the real surface.
vi.mock('../../src/services/oracle', () => ({
  oracle: { getAgent: vi.fn(), resolveXns: vi.fn() },
}));

const did = 'did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861';
const sovereignAgent = '0x360e2a56eb23e383b81e5bb42ee5c3966688558a';

function search(value: string) {
  const input = screen.getByPlaceholderText(/Search handle/i);
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
}

describe('XNSSearchService', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders search input and initial state', () => {
    render(<XNSSearchService />);
    expect(screen.getByPlaceholderText(/Search handle/i)).toBeInTheDocument();
    expect(screen.getByText(/Lookup any agent across the Integrity Network/i)).toBeInTheDocument();
  });

  it('looks a did: identifier up directly, without touching the name service', async () => {
    (oracle.getAgent as any).mockResolvedValue({ alias: 'Test Agent', eth_address: did, current_ais: 850 });

    render(<XNSSearchService />);
    search(`${did} `); // trailing space — the component must trim before querying

    await waitFor(() => {
      expect(screen.getByText('Test Agent')).toBeInTheDocument();
    });
    expect(oracle.getAgent).toHaveBeenCalledWith(did);
    expect(oracle.resolveXns).not.toHaveBeenCalled();
  });

  it('looks a 0x address up directly', async () => {
    (oracle.getAgent as any).mockResolvedValue({ alias: 'Eth Agent', eth_address: sovereignAgent });

    render(<XNSSearchService />);
    search(sovereignAgent);

    await waitFor(() => {
      expect(screen.getByText('Eth Agent')).toBeInTheDocument();
    });
    expect(oracle.getAgent).toHaveBeenCalledWith(sovereignAgent);
  });

  it('resolves a handle through XNS, then loads the agent behind it', async () => {
    (oracle.resolveXns as any).mockResolvedValue({
      handle: 'xibalba.integrity',
      sovereign_agent: sovereignAgent,
      did,
    });
    (oracle.getAgent as any).mockResolvedValue({ alias: 'xibalba.integrity', eth_address: did });

    render(<XNSSearchService />);
    search('xibalba.integrity');

    await waitFor(() => {
      // Rendered twice by design — as the agent's alias heading and as the handle badge.
      expect(screen.getByRole('heading', { name: 'xibalba.integrity' })).toBeInTheDocument();
    });
    expect(oracle.resolveXns).toHaveBeenCalledWith('xibalba.integrity');
    expect(oracle.getAgent).toHaveBeenCalledWith(did);
  });

  it('surfaces the raw on-chain resolution when the oracle has no DID for the handle', async () => {
    (oracle.resolveXns as any).mockResolvedValue({
      handle: 'newagent',
      sovereign_agent: sovereignAgent,
      did: null,
    });

    render(<XNSSearchService />);
    search('newagent');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'newagent.intg' })).toBeInTheDocument();
    });
    expect(oracle.getAgent).not.toHaveBeenCalled();
  });

  it('reports an unregistered handle as unregistered, not as an error', async () => {
    // An unclaimed handle resolves to the zero address — it is not an exception.
    (oracle.resolveXns as any).mockResolvedValue({ handle: 'nobody', sovereign_agent: null, did: null });

    render(<XNSSearchService />);
    search('nobody');

    await waitFor(() => {
      expect(
        screen.getByText('Handle "nobody" is not registered in the XibalbaNameService.'),
      ).toBeInTheDocument();
    });
  });

  it('distinguishes "XNS not deployed" (400) from "agent not found"', async () => {
    (oracle.resolveXns as any).mockRejectedValue(
      Object.assign(new Error('Oracle request failed: 400 /v1/xns/resolve'), { status: 400 }),
    );

    render(<XNSSearchService />);
    search('anyhandle');

    await waitFor(() => {
      expect(screen.getByText(/XNS name service is not deployed on this network yet/i)).toBeInTheDocument();
    });
  });

  it('falls back to the generic not-found message for a failed direct DID lookup', async () => {
    (oracle.getAgent as any).mockRejectedValue(
      Object.assign(new Error('Oracle request failed: 404'), { status: 404 }),
    );

    render(<XNSSearchService />);
    search('did:integrity:doesnotexist');

    await waitFor(() => {
      expect(screen.getByText(/Agent not found\. Try its full did:integrity/i)).toBeInTheDocument();
    });
  });
});
