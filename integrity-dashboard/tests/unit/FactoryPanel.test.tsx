import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FactoryPanel } from '../../src/components/tabs/FactoryPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';
import { api } from '../../src/services/api';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({
  api: {
    deployContract: vi.fn(),
  },
}));

const mockAgent = {
  eth_address: '0x1234567890abcdef',
  alias: 'Test Factory',
};

describe('FactoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial state', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<FactoryPanel />);
    expect(screen.getByText(/Contract Logic Template/i)).toBeInTheDocument();
  });

  it('changes contract template when type is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const select = screen.getByLabelText(/Contract Type/i);
    fireEvent.change(select, { target: { value: 'Escrow' } });

    expect(screen.getAllByText(/AutonomousEscrow/i)[0]).toBeInTheDocument();
  });

  it('deploys a contract successfully', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    (api.deployContract as unknown).mockResolvedValue({
      contract_address: '0xnewcontract',
      status: 'deployed'
    });

    render(<FactoryPanel />);
    
    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    await waitFor(() => {
      expect(api.deployContract).toHaveBeenCalled();
      expect(addToastMock).toHaveBeenCalledWith('success', expect.stringContaining('0xnewcontract'));
    }, { timeout: 3000 });
  });

  it('handles deployment failure', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    (api.deployContract as unknown).mockRejectedValue(new Error('Out of gas'));

    render(<FactoryPanel />);
    
    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('error', expect.stringContaining('Out of gas'));
    }, { timeout: 3000 });
  });

  it('fails deploy if no agent selected', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
      addToast: addToastMock,
    });

    render(<FactoryPanel />);
    
    const deployBtn = screen.getByRole('button', { name: /Deploy Contract/i });
    fireEvent.click(deployBtn);

    expect(addToastMock).toHaveBeenCalledWith('error', 'No agent wallet selected');
    expect(api.deployContract).not.toHaveBeenCalled();
  });

  it('builds source code', async () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const buildBtn = screen.getByRole('button', { name: /Build Source/i });
    fireEvent.click(buildBtn);

    await waitFor(() => {
      expect(screen.getByText(/SUCCESS: SLA compiled with 0 warnings/i)).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('switches terminal tabs', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const problemsTab = screen.getByText(/PROBLEMS \(0\)/i);
    fireEvent.click(problemsTab);
    expect(screen.getByText(/No compilation or execution problems detected./i)).toBeInTheDocument();

    const terminalTab = screen.getByText(/TERMINAL/i);
    fireEvent.click(terminalTab);
    expect(screen.getByText(/System: Welcome to Xibalba IDE/i)).toBeInTheDocument();
  });

  it('triggers AI copilot on enter', async () => {
    const addToastMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
      addToast: addToastMock,
    });

    render(<FactoryPanel />);
    const copilotInput = screen.getByPlaceholderText(/AI Contract Copilot/i);
    fireEvent.keyDown(copilotInput, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(addToastMock).toHaveBeenCalledWith('success', 'AI Code refactor applied based on SDK telemetry');
    }, { timeout: 2000 });
  });

  it('changes language and updates template', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const vyperBtn = screen.getByRole('button', { name: 'Vyper' });
    fireEvent.click(vyperBtn);
    
    // Vyper uses `# @version ^0.3.7`
    const codeArea = screen.getAllByRole('textbox').find(el => el.tagName.toLowerCase() === 'textarea' && el.getAttribute('id') !== 'import-data') as HTMLTextAreaElement;
    expect(codeArea.value).toContain('# @version ^0.3.7');
  });

  it('updates code when typing', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: mockAgent,
    });

    render(<FactoryPanel />);
    const codeArea = screen.getAllByRole('textbox').find(el => el.tagName.toLowerCase() === 'textarea' && el.getAttribute('id') !== 'import-data') as HTMLTextAreaElement;
    fireEvent.change(codeArea, { target: { value: 'contract NewContract {}' } });
    expect(codeArea.value).toBe('contract NewContract {}');
  });
});
