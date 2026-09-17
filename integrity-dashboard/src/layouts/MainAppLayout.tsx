import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { Sidebar } from '../components/Sidebar';
import { AppHeader } from '../components/AppHeader';
import { useDashboard } from '../context/DashboardContext';
import '../pages/ProtocolDashboardPage.css';

export default function MainAppLayout() {
  const { layoutMode } = useDashboard();
  const location = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [location.pathname]);

  return (
    <div className="protocol-app" style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
      {layoutMode === 'sidebar' && <Sidebar />}
      <main className="protocol-main" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <AppHeader />
        <div className="protocol-content" style={{ flex: 1 }}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
