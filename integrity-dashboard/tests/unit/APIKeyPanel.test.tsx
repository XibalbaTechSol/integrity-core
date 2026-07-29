import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { APIKeyPanel } from '../../src/components/tabs/APIKeyPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { userapi, getToken } from '../../src/services/userapi';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/userapi', () => ({
  getToken: vi.fn(),
  userapi: {
    listApiKeys: vi.fn(),
    createApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
  },
}));

describe('APIKeyPanel', () => {
  const mockKeys = [
    { id: 'key-id-123456789012', created_at: new Date().toISOString(), ais_trust_ceiling: 300, revoked_at: null }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock as authenticated
    (getToken as any).mockReturnValue('mock-jwt-token');
    (userapi.listApiKeys as any).mockResolvedValue(mockKeys);
    // Mock clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(),
      },
    });
  });

  it('renders initial state with existing keys', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);

    render(<APIKeyPanel />);
    
    await waitFor(() => {
      expect(screen.getByText(/key-id-12345/i)).toBeInTheDocument();
      expect(screen.getByText(/Generate Key/i)).toBeInTheDocument();
    });
  });

  it('generates a key successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    (userapi.createApiKey as any).mockResolvedValue({ 
      id: 'new-key-id',
      raw_key: 'itk_sk_123456789', 
      created_at: new Date().toISOString(),
      ais_trust_ceiling: 300,
      revoked_at: null,
    });

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByText(/Generate Key/i));
    const genBtn = screen.getByRole('button', { name: /Generate Key/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(userapi.createApiKey).toHaveBeenCalled();
      expect(screen.getByDisplayValue('itk_sk_123456789')).toBeInTheDocument();
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('generated'));
    });
  });

  it('copies key to clipboard', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);
    (userapi.createApiKey as any).mockResolvedValue({ 
      id: 'new-key-id',
      raw_key: 'itk_sk_123456789',
      created_at: new Date().toISOString(),
      ais_trust_ceiling: 300,
      revoked_at: null,
    });

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByRole('button', { name: /Generate Key/i }));
    fireEvent.click(screen.getByRole('button', { name: /Generate Key/i }));
    
    await waitFor(() => screen.getByDisplayValue('itk_sk_123456789'));

    const copyBtn = screen.getAllByRole('button').find(b => b.textContent?.includes('Copy'));
    if (copyBtn) fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('itk_sk_123456789');
  });

  it('deletes a key successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });
    
    window.confirm = vi.fn().mockReturnValue(true);
    (userapi.revokeApiKey as any).mockResolvedValue({});

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Revoke Key'));
    const deleteBtn = screen.getByTitle('Revoke Key');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(userapi.revokeApiKey).toHaveBeenCalledWith('key-id-123456789012');
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('revoked'));
    });
  });

  it('handles error fetching keys', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    (userapi.listApiKeys as any).mockRejectedValue(new Error('Fetch failed'));

    render(<APIKeyPanel />);
    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', 'Failed to fetch API Keys: Fetch failed');
    });
  });

  it('handles error generating key', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    (userapi.createApiKey as any).mockRejectedValue(new Error('Generate failed'));

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByRole('button', { name: /Generate Key/i }));

    const genBtn = screen.getByRole('button', { name: /Generate Key/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(userapi.createApiKey).toHaveBeenCalled();
      expect(addToastMock).toHaveBeenCalledWith('error', 'Failed to generate API Key: Generate failed');
    });
  });

  it('handles error deleting key', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });
    
    window.confirm = vi.fn().mockReturnValue(true);
    (userapi.revokeApiKey as any).mockRejectedValue(new Error('Revoke failed'));

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Revoke Key'));
    const deleteBtn = screen.getByTitle('Revoke Key');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', 'Failed to revoke API Key: Revoke failed');
    });
  });

  it('copies existing key ID from the list', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);
    
    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Copy key ID'));
    const copyBtn = screen.getByTitle('Copy key ID');
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('key-id-123456789012');
  });
});
