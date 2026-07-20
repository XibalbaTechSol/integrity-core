import { createContext, useContext } from 'react';
import type { Agent, ProtocolStats, TabId } from '../types';

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
  user: any;
  
  selectAgent: (address: string) => void;
  setActiveTab: (tab: TabId) => void;
  connectWallet: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
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
