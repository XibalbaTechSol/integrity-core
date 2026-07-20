import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { APIKeyPanel } from '../../src/components/tabs/APIKeyPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    getApiKeys: vi.fn(),
    generateApiKey: vi.fn(),
    deleteApiKey: vi.fn(),
  },
}));

describe('APIKeyPanel', () => {
  const mockKeys = [
    { api_key: 'sk-existing-123', created_at: new Date().toISOString(), expires_at: new Date().toISOString() }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getApiKeys as unknown).mockResolvedValue(mockKeys);
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
      expect(screen.getByText(/sk-existing/i)).toBeInTheDocument();
      expect(screen.getByText(/Generate Key/i)).toBeInTheDocument();
    });
  });

  it('generates a key successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    (api.generateApiKey as unknown).mockResolvedValue({ 
      api_key: 'sk-123456789', 
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString() 
    });

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByText(/Generate Key/i));
    const genBtn = screen.getByRole('button', { name: /Generate Key/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(api.generateApiKey).toHaveBeenCalled();
      expect(screen.getByDisplayValue('sk-123456789')).toBeInTheDocument();
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('generated'));
    });
  });

  it('copies key to clipboard', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);
    (api.generateApiKey as unknown).mockResolvedValue({ 
      api_key: 'sk-123456789',
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString()
    });

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByRole('button', { name: /Generate Key/i }));
    fireEvent.click(screen.getByRole('button', { name: /Generate Key/i }));
    
    await waitFor(() => screen.getByDisplayValue('sk-123456789'));

    const copyBtn = screen.getAllByRole('button').find(b => b.textContent?.includes('Copy'));
    if (copyBtn) fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('sk-123456789');
  });

  it('deletes a key successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });
    
    window.confirm = vi.fn().mockReturnValue(true);
    (api.deleteApiKey as unknown).mockResolvedValue({ status: 'deleted' });

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Delete Key'));
    const deleteBtn = screen.getByTitle('Delete Key');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(api.deleteApiKey).toHaveBeenCalledWith('sk-existing-123');
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('deleted'));
    });
  });
  it('handles error fetching keys', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    (api.getApiKeys as unknown).mockRejectedValue(new Error('Fetch failed'));

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

    (api.generateApiKey as unknown).mockRejectedValue(new Error('Generate failed'));

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByRole('button', { name: /Generate Key/i }));
    
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: '90' } });

    const genBtn = screen.getByRole('button', { name: /Generate Key/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(api.generateApiKey).toHaveBeenCalledWith(90);
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
    (api.deleteApiKey as unknown).mockRejectedValue(new Error('Delete failed'));

    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Delete Key'));
    const deleteBtn = screen.getByTitle('Delete Key');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', 'Failed to delete API Key: Delete failed');
    });
  });

  it('copies existing key from the list', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);
    
    render(<APIKeyPanel />);
    
    await waitFor(() => screen.getByTitle('Copy Key'));
    const copyBtn = screen.getByTitle('Copy Key');
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('sk-existing-123');
  });
});
