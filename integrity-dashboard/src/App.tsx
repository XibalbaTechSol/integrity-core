/* eslint-disable @typescript-eslint/no-unused-vars */
import { lazy, Suspense } from 'react';
import { Navigate, Routes, Route } from 'react-router-dom';
import 'katex/dist/katex.min.css';
import './index.css';
import LandingPage from './LandingPage';
import Dashboard from './Dashboard';
import SystemControlPage from './pages/SystemControlPage';

import KernelIntentPage from './pages/KernelIntentPage';
import AuthPage from './pages/AuthPage';
import { DeveloperPage } from './pages/DeveloperPage';
import DocsPage from './pages/DocsPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';


import { ActuarialHub } from './components/tabs/ActuarialHub';
import { DashboardProvider } from './context/DashboardContext';
import { SettingsProvider } from './context/SettingsContext';
import MainAppLayout from './layouts/MainAppLayout';
import PublicLayout from './layouts/PublicLayout';
import SecurityControlPage from './pages/SecurityControlPage';
import IntelligenceControlPage from './pages/IntelligenceControlPage';
import TreasuryControlPage from './pages/TreasuryControlPage';
import ProtocolDashboardPage from './pages/ProtocolDashboardPage';
import CorrelationPage from './pages/CorrelationPage';
import HealthPage from './pages/HealthPage';
import KernelPage from './pages/KernelPage';
import LicencePage from './pages/LicencePage';
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
            {/* Legacy deep links remain reviewable in the unified protocol surface. */}
            <Route path="/agents" element={<ProtocolDashboardPage />} />
            <Route path="/identity" element={<ProtocolDashboardPage />} />
            <Route path="/records" element={<ProtocolDashboardPage />} />
            <Route path="/proofs" element={<ProtocolDashboardPage />} />
            <Route path="/wallets" element={<TreasuryControlPage />} />
            <Route path="/transactions" element={<TreasuryControlPage />} />
            <Route path="/contracts" element={<ProtocolDashboardPage />} />
            <Route path="/evidence" element={<ProtocolDashboardPage />} />
            <Route path="/activity" element={<ProtocolDashboardPage />} />
            <Route path="/treasury" element={<TreasuryControlPage />} />
            <Route path="/financials" element={<TreasuryControlPage />} />
            <Route path="/system" element={<SystemControlPage />} />
            <Route path="/intelligence" element={<IntelligenceControlPage />} />
            <Route path="/knowledge" element={<IntelligenceControlPage />} />
            <Route path="/memory" element={<IntelligenceControlPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/security" element={<SecurityControlPage />} />
            <Route path="/shield" element={<SecurityControlPage />} />
            <Route path="/fleet" element={<SecurityControlPage />} />
            <Route path="/correlation" element={<CorrelationPage />} />
            <Route path="/prediction-markets" element={<ActuarialHub mode="markets" />} />
            <Route path="/quant" element={<ActuarialHub mode="markets" />} />
            <Route path="/kernel" element={<KernelPage />} />
            <Route path="/licence" element={<LicencePage />} />
                        {/* Cross-platform identity aliases: keep the established pages while
                exposing the plan's explicit fleet and memory entry points. */}
                                    <Route path="/kernel-intent" element={<KernelIntentPage />} />
            <Route path="/developer" element={<DeveloperPage />} />
            <Route path="/settings" element={<SettingsPage />} />
                        <Route path="/wiki" element={<Suspense fallback={<div style={{ minHeight: '100vh', background: '#07111d' }} />}><WikiPage /></Suspense>} />
          </Route>
        </Routes>
      </DashboardProvider>
    </SettingsProvider>
  );
}

export default App;
