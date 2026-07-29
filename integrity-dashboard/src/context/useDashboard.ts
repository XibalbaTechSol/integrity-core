import { createContext, useContext } from 'react';
import type { Agent, ProtocolStats, TabId } from '../types';
import type { UserResponse } from '../services/userapi';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

export interface DashboardContextType {
  agents: Agent[];
  selectedAgent: Agent | null;
  stats: ProtocolStats | null;
  walletAddress: string | null;
  walletBalance: number;
  activeTab: TabId;
  isLoading: boolean;
  isBackendOffline: boolean;
  toasts: ToastMessage[];
  // The real authenticated userapi account (JWT-backed), or null when signed out.
  user: UserResponse | null;

  selectAgent: (address: string) => void;
  setActiveTab: (tab: TabId) => void;
  connectWallet: () => Promise<void>;
  // Real userapi email/password auth (replaces the old firebase Google popup).
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  fetchData: () => Promise<void>;
  addToast: (type: 'success' | 'error' | 'info', message: string) => void;
  removeToast: (id: string) => void;
}

export const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (context === undefined) {
    throw new Error('useDashboard must be used within a DashboardProvider');
  }
  return context;
}
