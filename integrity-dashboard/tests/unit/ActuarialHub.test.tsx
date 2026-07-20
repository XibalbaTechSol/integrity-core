import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ActuarialHub } from '../../src/components/tabs/ActuarialHub';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    getMarketTasks: vi.fn(),
    getBenchmarks: vi.fn(),
    createMarketTask: vi.fn(),
    fundTaskWithLoan: vi.fn(),
    bidOnTask: vi.fn(),
    requestAudit: vi.fn(),
  },
}));

const mockAgent = {
  agent_id: 'agent-123',
  eth_address: '0x123',
  alias: 'Test Agent',
  current_ais: 800,
  equity: [
    {
      agent_address: '0x999',
      shares: 100,
      total_shares: 1000,
      percentage: 10,
      dividends_earned: 50
    }
  ]
};

const mockTasks = [
  { task_id: 'task-1', title: 'Data Task', reward_itk: 100, min_ais_required: 500, status: 'open', creator_agent_id: 'agent-999', description: 'Desc' }
];

const mockBenchmarks = [
  { model_name: 'Model A', provider_name: 'Provider A', simulated_ais: 900, stability_metric: 0.96, grounding_metric: 0.96 }
];

const mockAgents = [
  { agent_id: 'agent-456', alias: 'Agent 456', eth_address: '0x456', current_ais: 950, description: 'Specialist' }
];

describe('ActuarialHub', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  describe('Markets mode', () => {
    beforeEach(() => {
      (api.getMarketTasks as unknown).mockResolvedValue(mockTasks);
    });

    it('renders markets initial state', async () => {
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        agents: mockAgents,
      });

      render(<ActuarialHub mode="markets" />);
      
      await waitFor(() => {
        expect(screen.getByText('Data Task')).toBeInTheDocument();
      });
      expect(screen.getByText('A2A Market Operations')).toBeInTheDocument();
      expect(screen.getByText('Open Marketplace Tasks')).toBeInTheDocument();
      expect(screen.getByText('Mesh Agents Directory (Real-Time Trade & Hire)')).toBeInTheDocument();
      expect(screen.getByText('Active A2A Escrow Contracts (Parametric Escrows)')).toBeInTheDocument();
      expect(screen.getByText('Agent Equity Holdings')).toBeInTheDocument();
    });

    it('creates a task without credit', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        addToast: addToastMock,
      });
      (api.createMarketTask as unknown).mockResolvedValue({ task_id: 'new-task' });

      render(<ActuarialHub mode="markets" />);

      const titleInput = screen.getByLabelText(/Task Title/i);
      fireEvent.change(titleInput, { target: { value: 'New Task' } });

      const createBtn = screen.getByRole('button', { name: /Create A2A Task/i });
      fireEvent.click(createBtn);

      await waitFor(() => {
        expect(api.createMarketTask).toHaveBeenCalledWith(expect.objectContaining({ title: 'New Task' }));
        expect(addToastMock).toHaveBeenCalledWith('success', 'Task created successfully');
      });
    });

    it('creates a task with credit', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        addToast: addToastMock,
      });
      (api.fundTaskWithLoan as unknown).mockResolvedValue({ task_id: 'new-task' });

      render(<ActuarialHub mode="markets" />);

      const titleInput = screen.getByLabelText(/Task Title/i);
      fireEvent.change(titleInput, { target: { value: 'Credit Task' } });

      const creditCheckbox = screen.getByLabelText(/Fund via Institutional Credit/i);
      fireEvent.click(creditCheckbox);

      const createBtn = screen.getByRole('button', { name: /Create A2A Task/i });
      fireEvent.click(createBtn);

      await waitFor(() => {
        expect(api.fundTaskWithLoan).toHaveBeenCalledWith(expect.objectContaining({ title: 'Credit Task' }));
        expect(addToastMock).toHaveBeenCalledWith('success', 'Task created successfully');
      });
    });

    it('places a bid on a task', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        addToast: addToastMock,
      });
      (api.bidOnTask as unknown).mockResolvedValue({ status: 'success' });

      render(<ActuarialHub mode="markets" />);
      await waitFor(() => {
        expect(screen.getByText('Data Task')).toBeInTheDocument();
      });

      const bidBtn = screen.getByRole('button', { name: /Place Bid/i });
      fireEvent.click(bidBtn);

      await waitFor(() => {
        expect(api.bidOnTask).toHaveBeenCalledWith({
          task_id: 'task-1',
          bidder_agent_address: mockAgent.eth_address,
          bid_amount_itk: 95.0
        });
        expect(addToastMock).toHaveBeenCalledWith('success', 'Bid placed successfully');
      });
    });

    it('expands task row', async () => {
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
      });

      render(<ActuarialHub mode="markets" />);
      await waitFor(() => {
        expect(screen.getByText('Data Task')).toBeInTheDocument();
      });

      const row = screen.getByText('task-1...').closest('tr');
      fireEvent.click(row!);

      expect(screen.getByText('Creator Agent ID:')).toBeInTheDocument();
    });

    it('handles hire agent flow (escrow)', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        agents: mockAgents,
        addToast: addToastMock,
      });

      render(<ActuarialHub mode="markets" />);
      
      const hireBtn = screen.getByRole('button', { name: /Hire \(Escrow\)/i });
      fireEvent.click(hireBtn);

      // Modal appears
      expect(screen.getByText('Hire Agent 456')).toBeInTheDocument();

      const taskTitleInput = screen.getAllByRole('textbox')[1]; // first is the create task one, second is modal? Wait, let's use placeholder
      const modalTitleInput = screen.getByPlaceholderText(/Audit historical ledger/i);
      fireEvent.change(modalTitleInput, { target: { value: 'Audit Task' } });

      const deployContractBtn = screen.getByRole('button', { name: /Deploy Hire Contract & Lock Funds/i });
      fireEvent.click(deployContractBtn);

      await waitFor(() => {
        expect(addToastMock).toHaveBeenCalledWith('success', 'Agent Agent 456 hired via escrow!');
      }, { timeout: 2000 });
      
      // Modal should disappear
      expect(screen.queryByText('Hire Agent 456')).not.toBeInTheDocument();
    });

    it('releases and refunds escrow', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        addToast: addToastMock,
      });

      render(<ActuarialHub mode="markets" />);
      
      // The default state has 1 escrow in localStorage or initialized state
      const releaseBtn = screen.getByRole('button', { name: /Release/i });
      fireEvent.click(releaseBtn);
      
      expect(addToastMock).toHaveBeenCalledWith('success', 'Escrow funds released to agent!');
    });
  });

  describe('Stability mode', () => {
    beforeEach(() => {
      (api.getBenchmarks as unknown).mockResolvedValue(mockBenchmarks);
    });

    it('renders stability initial state', async () => {
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
      });

      render(<ActuarialHub mode="stability" />);
      
      await waitFor(() => {
        expect(screen.getByText('Model A')).toBeInTheDocument();
      });
      expect(screen.getByText('Stability Leaderboard')).toBeInTheDocument();
      expect(screen.getByText('Regional Performance')).toBeInTheDocument();
      expect(screen.getByText('Certification Pipeline')).toBeInTheDocument();
    });

    it('requests an audit', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: mockAgent,
        addToast: addToastMock,
      });
      (api.requestAudit as unknown).mockResolvedValue({ status: 'success' });

      render(<ActuarialHub mode="stability" />);
      await waitFor(() => {
        expect(screen.getByText('Model A')).toBeInTheDocument();
      });
      
      const auditBtn = screen.getByRole('button', { name: /Start Certification Audit/i });
      fireEvent.click(auditBtn);

      await waitFor(() => {
        expect(api.requestAudit).toHaveBeenCalledWith(mockAgent.eth_address, 'AUTOMATED');
        expect(addToastMock).toHaveBeenCalledWith('success', 'Institutional certification audit initialized');
      });
    });

    it('requires agent for audit request (disabled button)', async () => {
      const addToastMock = vi.fn();
      (useDashboard as unknown).mockReturnValue({
        ...mockDashboardContext,
        selectedAgent: null,
        addToast: addToastMock,
      });

      render(<ActuarialHub mode="stability" />);
      await waitFor(() => {
        expect(screen.getByText('Model A')).toBeInTheDocument();
      });
      
      const auditBtn = screen.getByRole('button', { name: /Start Certification Audit/i });
      expect(auditBtn).toBeDisabled();
    });
  });
});
