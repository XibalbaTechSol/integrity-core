import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { XNSSearchService } from '../../src/components/ui/XNSSearchService';
import axios from 'axios';
import { API_BASE } from '../../src/constants';

vi.mock('axios');

describe('XNSSearchService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders search input and initial state', () => {
    render(<XNSSearchService />);
    expect(screen.getByPlaceholderText(/Search handle/i)).toBeInTheDocument();
    expect(screen.getByText(/Lookup any agent across the Integrity Network/i)).toBeInTheDocument();
  });

  it('handles did:intg: prefix search', async () => {
    (axios.get as any).mockResolvedValueOnce({
      data: {
        alias: 'Test Agent',
        eth_address: '0x1234567890123456789012345678901234567890',
        current_ais: 850,
        verification_tier: 2,
        trust_level: 'HIGH',
      }
    });

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: 'did:intg:agent123 ' } }); // Note trailing space to test trim
    
    // Press enter
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith(`${API_BASE}/v1/identity/resolve`, {
        params: { did: 'did:intg:agent123' }
      });
      expect(screen.getByText('Test Agent')).toBeInTheDocument();
      expect(screen.getByText('850')).toBeInTheDocument();
    });
  });

  it('handles .intg suffix search', async () => {
    (axios.get as any).mockResolvedValueOnce({
      data: {
        alias: 'XNS Agent',
        current_ais: 900,
        xns_handle: 'test.intg',
      }
    });

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: 'test.intg' } });
    
    // Click button
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[0]); // The search button

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith(`${API_BASE}/v1/identity/resolve`, {
        params: { xns: 'test.intg' }
      });
      expect(screen.getByText('XNS Agent')).toBeInTheDocument();
      expect(screen.getByText('test.intg')).toBeInTheDocument();
    });
  });

  it('handles 0x prefix search', async () => {
    (axios.get as any).mockResolvedValueOnce({
      data: {
        alias: 'Eth Agent',
        current_ais: 700,
      }
    });

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: '0xabc123' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith(`${API_BASE}/v1/identity/agent/0xabc123`);
      expect(screen.getByText('Eth Agent')).toBeInTheDocument();
    });
  });

  it('handles default search as xns resolve', async () => {
    (axios.get as any).mockResolvedValueOnce({
      data: {
        alias: 'Default Agent',
        current_ais: 800,
      }
    });

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: 'some_handle' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith(`${API_BASE}/v1/identity/resolve`, {
        params: { xns: 'some_handle' }
      });
      expect(screen.getByText('Default Agent')).toBeInTheDocument();
    });
  });

  it('displays 404 error when agent is not found', async () => {
    const mockError = { response: { status: 404 } };
    (axios.get as any).mockRejectedValueOnce(mockError);

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: 'missing.intg' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('Agent not found in the XNS Registry.')).toBeInTheDocument();
    });
  });

  it('displays generic error on network failure', async () => {
    const mockError = new Error('Network Error');
    (axios.get as any).mockRejectedValueOnce(mockError);

    render(<XNSSearchService />);
    const input = screen.getByPlaceholderText(/Search handle/i);
    fireEvent.change(input, { target: { value: 'error.intg' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('Unable to connect to the XNS Resolver.')).toBeInTheDocument();
    });
  });
});
