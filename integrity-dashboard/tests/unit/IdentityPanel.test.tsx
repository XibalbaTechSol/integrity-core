import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IdentityPanel } from '../../src/components/tabs/IdentityPanel';
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

vi.mock('../../src/components/ui/DIDExplorer', () => ({
  DIDExplorer: () => <div data-testid="did-explorer" />
}));

vi.mock('../../src/components/ui/AgentOnboarding', () => ({
  AgentOnboarding: ({ isOpen, onClose, onSuccess }: any) => {
    if (!isOpen) return null;
    return (
      <div data-testid="agent-onboarding">
        <button onClick={onClose}>Close Onboarding</button>
        <button onClick={() => onSuccess('0x123')}>Success Onboarding</button>
      </div>
    );
  }
}));

vi.mock('../../src/components/tabs/ClaimAgentModal', () => ({
  ClaimAgentModal: ({ isOpen, onClose, onSuccess }: any) => {
    if (!isOpen) return null;
    return (
      <div data-testid="claim-modal">
        <button onClick={onClose}>Close Claim</button>
        <button onClick={() => onSuccess()}>Success Claim</button>
      </div>
    );
  }
}));

describe('IdentityPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "Select an agent" message when no agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<IdentityPanel />);
    expect(screen.getByText(/Select an agent from the sidebar/i)).toBeInTheDocument();
  });

  it('renders DIDExplorer when an agent is selected', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: { eth_address: '0x123', alias: 'Test Agent' },
    });

    render(<IdentityPanel />);
    expect(screen.getByTestId('did-explorer')).toBeInTheDocument();
  });

  it('opens and closes registration modal, handles success', () => {
    const fetchDataMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      fetchData: fetchDataMock
    });

    render(<IdentityPanel />);
    
    // Open modal
    fireEvent.click(screen.getByText(/Register New/i));
    expect(screen.getByTestId('agent-onboarding')).toBeInTheDocument();
    
    // Close modal
    fireEvent.click(screen.getByText('Close Onboarding'));
    expect(screen.queryByTestId('agent-onboarding')).not.toBeInTheDocument();

    // Open again, trigger success
    fireEvent.click(screen.getByText(/Register New/i));
    fireEvent.click(screen.getByText('Success Onboarding'));
    expect(screen.queryByTestId('agent-onboarding')).not.toBeInTheDocument();
    expect(fetchDataMock).toHaveBeenCalled();
  });

  it('opens and closes claim modal, handles success', () => {
    const fetchDataMock = vi.fn();
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      fetchData: fetchDataMock
    });

    render(<IdentityPanel />);
    
    // Open modal
    fireEvent.click(screen.getByText(/Claim Existing/i));
    expect(screen.getByTestId('claim-modal')).toBeInTheDocument();
    
    // Close modal
    fireEvent.click(screen.getByText('Close Claim'));
    expect(screen.queryByTestId('claim-modal')).not.toBeInTheDocument();

    // Open again, trigger success
    fireEvent.click(screen.getByText(/Claim Existing/i));
    fireEvent.click(screen.getByText('Success Claim'));
    expect(screen.queryByTestId('claim-modal')).not.toBeInTheDocument();
    expect(fetchDataMock).toHaveBeenCalled();
  });
});
