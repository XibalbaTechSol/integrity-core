import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ActuarialHub } from '../../src/components/tabs/ActuarialHub';
const MarketsPanel = () => <ActuarialHub mode="markets" />;
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    getMarketTasks: vi.fn(),
    createMarketTask: vi.fn(),
    fundTaskWithLoan: vi.fn(),
    bidOnTask: vi.fn(),
  },
}));

const mockTasks = [
  {
    task_id: 'task-1234567890',
    title: 'Data Inference SLA',
    reward_itk: 100,
    min_ais_required: 600,
    status: 'open',
  }
];

const mockAgent = {
  eth_address: '0x123',
  alias: 'Test Agent',
  current_ais: 800,
  equity: [
    {
      agent_address: '0x999888777666',
      shares: 100,
      total_shares: 1000,
      percentage: 10,
      dividends_earned: 50
    }
  ]
};

describe('MarketsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getMarketTasks as unknown).mockResolvedValue(mockTasks);
  });

  it('renders open marketplace tasks', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<MarketsPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('Data Inference SLA')).toBeInTheDocument();
      expect(screen.getByText('100 ITK')).toBeInTheDocument();
    });
  });

  it('creates a task successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    (api.createMarketTask as unknown).mockResolvedValue({ task_id: 'new-task-id' });

    render(<MarketsPanel />);
    
    fireEvent.change(screen.getByLabelText(/Task Title/i), { target: { value: 'New Test Task' } });
    fireEvent.change(screen.getByLabelText(/Reward \(ITK\)/i), { target: { value: '200' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Create A2A Task/i }));

    await waitFor(() => {
      expect(api.createMarketTask).toHaveBeenCalled();
      expect(addToastMock).toHaveBeenCalledWith('success', 'Task created successfully');
      expect(screen.getByTestId('protocol-logs')).toHaveTextContent(/SUCCESS: Task created/);
    });
  });

  it('creates a task with credit leverage', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    (api.fundTaskWithLoan as unknown).mockResolvedValue({ task_id: 'leveraged-task-id' });

    render(<MarketsPanel />);
    
    fireEvent.change(screen.getByLabelText(/Task Title/i), { target: { value: 'Leveraged Task' } });
    fireEvent.click(screen.getByLabelText(/Fund via Institutional Credit/i));
    
    fireEvent.click(screen.getByRole('button', { name: /Create A2A Task/i }));

    await waitFor(() => {
      expect(api.fundTaskWithLoan).toHaveBeenCalled();
      expect(screen.getByTestId('protocol-logs')).toHaveTextContent(/leveraged/);
    });
  });

  it('places a bid on a task', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<MarketsPanel />);
    
    await waitFor(() => screen.getByText('Data Inference SLA'));
    
    const bidBtn = screen.getByRole('button', { name: /Place Bid/i });
    fireEvent.click(bidBtn);

    await waitFor(() => {
      expect(api.bidOnTask).toHaveBeenCalled();
      expect(screen.getByTestId('protocol-logs')).toHaveTextContent(/SUCCESS: Bid placed/);
    });
  });

  it('renders agent equity holdings', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<MarketsPanel />);
    expect(await screen.findByText(/0x99988877/)).toBeInTheDocument();
    expect(screen.getByText('10%')).toBeInTheDocument();
  });
});
