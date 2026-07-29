import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActuarialHub } from '../../src/components/tabs/ActuarialHub';
const StabilityPanel = () => <ActuarialHub mode="stability" />;
import { useDashboard } from '../../src/context/useDashboard';
import { mockDashboardContext } from './test-utils';

// ActuarialHub calls `oracle.getBenchmarks()` on mount. Unmocked, that is a real fetch
// that happens to be caught into an empty list — the assertions below would then be
// passing for the wrong reason (network failure, not an empty benchmark set).
vi.mock('../../src/services/oracle', () => ({
  oracle: { getBenchmarks: vi.fn().mockResolvedValue([]), getMarkets: vi.fn().mockResolvedValue([]) },
}));

vi.mock('../../src/context/useDashboard', () => ({
  useDashboard: vi.fn(),
}));

describe('StabilityPanel', () => {
  it('renders benchmark pending state', () => {
    (useDashboard as unknown).mockReturnValue({
      ...mockDashboardContext,
      selectedAgent: null,
    });

    render(<StabilityPanel />);
    expect(screen.getByText('Model Stability Leaderboard')).toBeInTheDocument();
    expect(screen.getByText('No benchmark telemetry yet.')).toBeInTheDocument();
  });
});
