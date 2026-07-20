import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GovernancePanel } from '../../src/components/tabs/GovernancePanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    getProposals: vi.fn(),
    voteProposal: vi.fn(),
    createProposal: vi.fn(),
  },
}));

const mockProposals = [
  {
    proposal_id: 'prop-1',
    title: 'Test Proposal',
    category: 'protocol',
    description: 'A test proposal description',
    status: 'active',
    votes_for: 1000,
    votes_against: 500,
    created_at: new Date().toISOString(),
  },
  {
    proposal_id: 'prop-2',
    title: 'Passed Proposal',
    category: 'economic',
    description: 'A passed proposal description',
    status: 'passed',
    votes_for: 5000,
    votes_against: 100,
    created_at: new Date().toISOString(),
  }
];

describe('GovernancePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    (api.getProposals as unknown).mockResolvedValue(mockProposals);
  });

  it('renders proposals from API', async () => {
    (useDashboard as unknown).mockReturnValue(mockDashboardContext);

    render(<GovernancePanel />);
    
    await waitFor(() => {
      expect(screen.getByText('Test Proposal')).toBeInTheDocument();
      expect(screen.getByText('Passed Proposal')).toBeInTheDocument();
    });
  });

  it('casts a vote successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    render(<GovernancePanel />);
    
    await waitFor(() => screen.getByText('Test Proposal'));
    
    const voteBtn = screen.getByRole('button', { name: /Vote For/i });
    fireEvent.click(voteBtn);

    await waitFor(() => {
      expect(api.voteProposal).toHaveBeenCalledWith('prop-1', 'for');
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Vote cast'));
    });
  });

  it('creates a new proposal', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    render(<GovernancePanel />);
    
    fireEvent.change(screen.getByLabelText(/Title/i), { target: { value: 'New Prop' } });
    fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: 'New Desc' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Submit Proposal/i }));

    await waitFor(() => {
      expect(api.createProposal).toHaveBeenCalled();
      expect(screen.getByText('New Prop')).toBeInTheDocument();
    });
  });
  it('handles error fetching proposals and loads mock proposals', async () => {
    (api.getProposals as unknown).mockRejectedValue(new Error('Fetch failed'));

    render(<GovernancePanel />);
    
    await waitFor(() => {
      // MOCK_PROPOSALS has one with title 'Increase Minimum ITK Stake for Validator Nodes'
      expect(screen.getByText('Increase Minimum ITK Stake for Validator Nodes')).toBeInTheDocument();
    });
  });

  it('casts a vote against successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });

    render(<GovernancePanel />);
    
    await waitFor(() => screen.getByText('Test Proposal'));
    
    const voteBtn = screen.getByRole('button', { name: /Vote Against/i });
    fireEvent.click(voteBtn);

    await waitFor(() => {
      expect(api.voteProposal).toHaveBeenCalledWith('prop-1', 'against');
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Vote cast'));
    });
  });

  it('handles error when casting a vote (offline mode)', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });
    
    (api.voteProposal as unknown).mockRejectedValue(new Error('Network error'));

    render(<GovernancePanel />);
    
    await waitFor(() => screen.getByText('Test Proposal'));
    
    const voteBtn = screen.getByRole('button', { name: /Vote For/i });
    fireEvent.click(voteBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Vote cast locally'));
    });
  });

  it('handles error when creating a proposal (offline mode) and changes category', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      addToast: addToastMock,
    });
    
    (api.createProposal as unknown).mockRejectedValue(new Error('Network error'));

    render(<GovernancePanel />);
    
    fireEvent.change(screen.getByLabelText(/Title/i), { target: { value: 'New Offline Prop' } });
    fireEvent.change(screen.getByLabelText(/Category/i), { target: { value: 'economic' } });
    fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: 'New Desc' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Submit Proposal/i }));

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Proposal submitted locally'));
      expect(screen.getByText('New Offline Prop')).toBeInTheDocument();
    });
  });
});
