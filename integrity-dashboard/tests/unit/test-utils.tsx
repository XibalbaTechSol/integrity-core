import { ReactElement } from 'react';
import { render } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { vi } from 'vitest';

// Mock context values
export const mockDashboardContext = {
  agents: [],
  selectedAgent: null,
  stats: null,
  walletAddress: null,
  walletBalance: 0,
  activeTab: 'telemetry',
  isLoading: false,
  isBackendOffline: false,
  toasts: [],
  selectAgent: vi.fn(),
  setActiveTab: vi.fn(),
  connectWallet: vi.fn(),
  fetchData: vi.fn(),
  addToast: vi.fn(),
  removeToast: vi.fn(),
};

// We will mock the useDashboard hook directly in tests where needed
// or provide a custom wrapper.
