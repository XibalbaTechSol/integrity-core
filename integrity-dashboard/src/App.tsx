import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import 'katex/dist/katex.min.css';
import './index.css';
import LandingPage from './LandingPage';
import Dashboard from './Dashboard';
import IdentityPage from './pages/IdentityPage';
import FinancialsPage from './pages/FinancialsPage';
import HealthPage from './pages/HealthPage';
import ShieldPage from './pages/ShieldPage';
import QuantPage from './pages/QuantPage';
import LicencePage from './pages/LicencePage';
import KernelPage from './pages/KernelPage';
import AuthPage from './pages/AuthPage';
import SettingsPage from './pages/SettingsPage';
import { DeveloperPage } from './pages/DeveloperPage';
import DocsPage from './pages/DocsPage';
import MemoryPage from './pages/MemoryPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';
import { IntelligencePage } from './pages/IntelligencePage';
import { ActuarialHub } from './components/tabs/ActuarialHub';
import { DashboardProvider } from './context/DashboardContext';
import { SettingsProvider } from './context/SettingsContext';
import MainAppLayout from './layouts/MainAppLayout';
import PublicLayout from './layouts/PublicLayout';

const WikiPage = lazy(() => import('./pages/WikiPage'));

function App() {
  return (
    <SettingsProvider>
      <DashboardProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/wiki" element={<Suspense fallback={<div style={{ minHeight: '100vh', background: '#07111d' }} />}><WikiPage /></Suspense>} />
          <Route element={<PublicLayout />}>
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
          </Route>
          <Route element={<MainAppLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/identity" element={<IdentityPage />} />
            <Route path="/financials" element={<FinancialsPage />} />
            <Route path="/intelligence" element={<IntelligencePage />} />
            <Route path="/prediction-markets" element={<ActuarialHub mode="markets" />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/shield" element={<ShieldPage />} />
            <Route path="/quant" element={<QuantPage />} />
            <Route path="/licence" element={<LicencePage />} />
            <Route path="/kernel" element={<KernelPage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/developer" element={<DeveloperPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </DashboardProvider>
    </SettingsProvider>
  );
}

export default App;
