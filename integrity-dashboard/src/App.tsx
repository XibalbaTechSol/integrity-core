/* eslint-disable @typescript-eslint/no-unused-vars */
import { lazy, Suspense } from 'react';
import { Navigate, Routes, Route } from 'react-router-dom';
import 'katex/dist/katex.min.css';
import './index.css';
import LandingPage from './LandingPage';
import SystemControlPage from './pages/SystemControlPage';
import AuthPage from './pages/AuthPage';
import DocsPage from './pages/DocsPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';


import { DashboardProvider } from './context/DashboardContext';
import { SettingsProvider } from './context/SettingsContext';
import MainAppLayout from './layouts/MainAppLayout';
import PublicLayout from './layouts/PublicLayout';
import { IntelligencePage } from './pages/IntelligencePage';
import TreasuryControlPage from './pages/TreasuryControlPage';
import ProtocolDashboardPage from './pages/ProtocolDashboardPage';
import CorrelationPage from './pages/CorrelationPage';
import HealthPage from './pages/HealthPage';
import SettingsPage from './pages/SettingsPage';

const WikiPage = lazy(() => import('./pages/WikiPage'));

function App() {
  return (
    <SettingsProvider>
      <DashboardProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route element={<PublicLayout />}>
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
          </Route>
          <Route element={<MainAppLayout />}>
            <Route path="/dashboard" element={<ProtocolDashboardPage />} />
            <Route path="/agents" element={<IntelligencePage />} />
            <Route path="/evidence" element={<CorrelationPage />} />
            <Route path="/treasury" element={<TreasuryControlPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/system" element={<SystemControlPage />} />
            <Route path="/settings" element={<SettingsPage />} />
                        <Route path="/wiki" element={<Suspense fallback={<div style={{ minHeight: '100vh', background: '#07111d' }} />}><WikiPage /></Suspense>} />

            {/* Legacy deep links converge on one canonical page each. */}
            <Route path="/identity" element={<Navigate to="/agents" replace />} />
            <Route path="/intelligence" element={<Navigate to="/agents" replace />} />
            <Route path="/knowledge" element={<Navigate to="/agents" replace />} />
            <Route path="/memory" element={<Navigate to="/agents" replace />} />
            <Route path="/records" element={<Navigate to="/evidence" replace />} />
            <Route path="/proofs" element={<Navigate to="/evidence" replace />} />
            <Route path="/contracts" element={<Navigate to="/evidence" replace />} />
            <Route path="/activity" element={<Navigate to="/evidence" replace />} />
            <Route path="/correlation" element={<Navigate to="/evidence" replace />} />
            <Route path="/wallets" element={<Navigate to="/treasury" replace />} />
            <Route path="/transactions" element={<Navigate to="/treasury" replace />} />
            <Route path="/financials" element={<Navigate to="/treasury" replace />} />
            <Route path="/prediction-markets" element={<Navigate to="/treasury" replace />} />
            <Route path="/quant" element={<Navigate to="/treasury" replace />} />
            {/* Protection was a boundary-only handoff, not a dashboard surface. */}
            <Route path="/security" element={<Navigate to="/dashboard" replace />} />
            <Route path="/shield" element={<Navigate to="/dashboard" replace />} />
            <Route path="/fleet" element={<Navigate to="/agents" replace />} />
            <Route path="/kernel" element={<Navigate to="/system" replace />} />
            <Route path="/kernel-intent" element={<Navigate to="/system" replace />} />
            <Route path="/licence" element={<Navigate to="/system" replace />} />
            <Route path="/developer" element={<Navigate to="/system" replace />} />
          </Route>
        </Routes>
      </DashboardProvider>
    </SettingsProvider>
  );
}

export default App;
