import { Suspense, lazy } from 'react';
import { DashboardProvider } from './context/DashboardProvider';
import { SettingsProvider } from './context/SettingsProvider';
import { Sidebar } from './components/layout/Sidebar';
import { GlobalNav } from './components/layout/GlobalNav';
import { SubNav } from './components/layout/SubNav';
import { ToastManager } from './components/shared/Toast';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LandingPage } from './pages/LandingPage';

// Lazy-load the 5 consolidated pages
const IntelligencePage = lazy(() =>
  import('./pages/IntelligencePage').then(m => ({ default: m.IntelligencePage }))
);
const CognitionPage = lazy(() =>
  import('./pages/CognitionPage').then(m => ({ default: m.CognitionPage }))
);
const FinancePage = lazy(() =>
  import('./pages/FinancePage').then(m => ({ default: m.FinancePage }))
);
const ContractsPage = lazy(() =>
  import('./pages/ContractsPage').then(m => ({ default: m.ContractsPage }))
);
const ShieldPage = lazy(() =>
  import('./pages/ShieldPage').then(m => ({ default: m.ShieldPage }))
);
const IdentityPage = lazy(() =>
  import('./pages/IdentityPage').then(m => ({ default: m.IdentityPage }))
);
const ProfilePage = lazy(() =>
  import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage }))
);
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage }))
);

const LoadingFallback = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    flexDirection: 'column',
    gap: '16px',
    color: 'var(--text-muted)',
  }}>
    <div style={{
      width: '36px',
      height: '36px',
      border: '2px solid var(--glass-border)',
      borderTop: '2px solid var(--primary)',
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
    }} />
    <span style={{ fontSize: '0.75rem', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
      Loading
    </span>
  </div>
);

import { useDashboard } from './context/useDashboard';

import { CommandPalette } from './components/shared/CommandPalette';

function DashboardShell() {
  const { activeTab } = useDashboard();

  const isIntelligence = ['telemetry'].includes(activeTab);
  const isCognition = ['cognition', 'reasoning', 'diagnostics'].includes(activeTab);
  const isFinance = ['wallet', 'staking', 'credit', 'markets', 'stability'].includes(activeTab);
  const isContracts = ['factory', 'zk', 'oracle', 'ledger'].includes(activeTab);
  const isShield = ['governance', 'compliance', 'shield'].includes(activeTab);
  const isIdentity = ['identity', 'apikeys'].includes(activeTab);
  const isProfile = activeTab === 'profile';
  const isSettings = activeTab === 'settings';

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">
        <GlobalNav />
        <SubNav />
        <main className="content-area" style={activeTab === 'factory' ? { padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' } : undefined}>
          <Suspense fallback={<LoadingFallback />}>
            {isIntelligence && <IntelligencePage />}
            {isCognition && <CognitionPage />}
            {isFinance && <FinancePage />}
            {isContracts && <ContractsPage />}
            {isShield && <ShieldPage />}
            {isIdentity && <IdentityPage />}
            {isProfile && <ProfilePage />}
            {isSettings && <SettingsPage />}
          </Suspense>
        </main>
      </div>
      <ToastManager />
      <CommandPalette />
    </div>
  );
}

import AuthPage from './pages/AuthPage';

export default function App() {
  return (
    <SettingsProvider>
      <DashboardProvider>
        <HashRouter>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/landing" element={<LandingPage />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route
              path="/integrity/*"
              element={<DashboardShell />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </HashRouter>
      </DashboardProvider>
    </SettingsProvider>
  );
}
