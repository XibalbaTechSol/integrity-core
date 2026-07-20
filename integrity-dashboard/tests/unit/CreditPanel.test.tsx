import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreditPanel } from '../../src/components/tabs/CreditPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    borrow: vi.fn(),
    repay: vi.fn(),
  },
}));

const mockAgent = {
  eth_address: '0x123',
  alias: 'Test Agent',
  current_ais: 800,
  credit_profile: {
    credit_score: 750,
    max_borrow_limit: 10000,
    total_borrowed: 2000,
    default_count: 0,
    active_loans: [
      {
        loan_id: 'loan-1',
        principal: 2000,
        interest_rate: 0.05,
        due_date: '2026-12-31T00:00:00Z',
        status: 'active',
        repaid_amount: 500,
      }
    ]
  }
};

describe('CreditPanel', () => {
  it('renders "Select an agent" message when no agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<CreditPanel />);
    // Check for the one in Credit Profile
    expect(screen.getAllByText(/Select an agent/i)[0]).toBeInTheDocument();
  });

  it('renders credit profile metrics when an agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CreditPanel />);
    expect(screen.getByText('750')).toBeInTheDocument();
    expect(screen.getByText('10,000 ITK')).toBeInTheDocument();
    // Use getAllByText for '2,000 ITK' as it appears in profile and table
    expect(screen.getAllByText('2,000 ITK').length).toBeGreaterThan(0);
  });

  it('shows error message when borrow amount exceeds limit', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CreditPanel />);
    const input = screen.getByLabelText(/Principal Amount/i);
    fireEvent.change(input, { target: { value: '15000' } });

    expect(screen.getByText(/Exceeds maximum borrow limit/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Submit Loan Application/i })).toBeDisabled();
  });

  it('submits loan application successfully', async () => {
    const fetchDataMock = vi.fn();
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      fetchData: fetchDataMock,
      addToast: addToastMock,
    });

    (api.borrow as unknown).mockResolvedValue({ status: 'success' });

    render(<CreditPanel />);
    const input = screen.getByLabelText(/Principal Amount/i);
    fireEvent.change(input, { target: { value: '5000' } });

    const submitBtn = screen.getByRole('button', { name: /Submit Loan Application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.borrow).toHaveBeenCalledWith(mockAgent.eth_address, {
        amount: 5000,
        collateral_contracts: [],
        term_days: 30,
      });
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Loan approved'));
      expect(fetchDataMock).toHaveBeenCalled();
    });
  });

  it('handles loan application failure', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    (api.borrow as unknown).mockRejectedValue(new Error('Network Error'));

    render(<CreditPanel />);
    const input = screen.getByLabelText(/Principal Amount/i);
    fireEvent.change(input, { target: { value: '5000' } });

    const submitBtn = screen.getByRole('button', { name: /Submit Loan Application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', expect.stringContaining('Loan failed: Network Error'));
    });
  });

  it('handles full repayment', async () => {
    const addToastMock = vi.fn();
    const fetchDataMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: fetchDataMock,
    });
    (api.repay as unknown).mockResolvedValue({ status: 'success' });

    render(<CreditPanel />);
    const fullPayBtn = screen.getByRole('button', { name: /Pay Full/i });
    fireEvent.click(fullPayBtn);

    await waitFor(() => {
      // remaining due is 2100 - 500 = 1600.
      expect(api.repay).toHaveBeenCalledWith(mockAgent.eth_address, {
        loan_id: 'loan-1',
        amount: 1600
      });
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Repayment of 1,600 ITK processed'));
      expect(fetchDataMock).toHaveBeenCalled();
    });
  });

  it('handles custom repayment flow', async () => {
    const addToastMock = vi.fn();
    const fetchDataMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
      fetchData: fetchDataMock,
    });
    (api.repay as unknown).mockResolvedValue({ status: 'success' });

    render(<CreditPanel />);
    const customPayBtn = screen.getByRole('button', { name: /Repay Custom/i });
    fireEvent.click(customPayBtn);

    // After clicking, input should appear
    const input = screen.getByPlaceholderText('Amount');
    fireEvent.change(input, { target: { value: '100' } });

    const okBtn = screen.getByRole('button', { name: /Ok/i });
    fireEvent.click(okBtn);

    await waitFor(() => {
      expect(api.repay).toHaveBeenCalledWith(mockAgent.eth_address, {
        loan_id: 'loan-1',
        amount: 100
      });
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('100 ITK processed successfully'));
      expect(fetchDataMock).toHaveBeenCalled();
    });
  });

  it('cancels custom repayment flow', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<CreditPanel />);
    const customPayBtn = screen.getByRole('button', { name: /Repay Custom/i });
    fireEvent.click(customPayBtn);

    const input = screen.getByPlaceholderText('Amount');
    expect(input).toBeInTheDocument();

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    expect(screen.queryByPlaceholderText('Amount')).not.toBeInTheDocument();
  });

  it('handles loan rollover', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    render(<CreditPanel />);
    const rolloverBtn = screen.getByRole('button', { name: /Rollover/i });
    fireEvent.click(rolloverBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('Term rollover requested'));
    });
  });

  it('shows empty state when no active loans', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: {
        ...mockAgent,
        credit_profile: {
          ...mockAgent.credit_profile,
          active_loans: []
        }
      },
    });

    render(<CreditPanel />);
    expect(screen.getByText('No active loans found.')).toBeInTheDocument();
  });
});
