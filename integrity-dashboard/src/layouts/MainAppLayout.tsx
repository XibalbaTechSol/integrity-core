import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';
import { AppHeader } from '../components/AppHeader';
import { useDashboard } from '../context/DashboardContext';
import { useIsMobile } from '../utils/useIsMobile';

export default function MainAppLayout() {
  const { layoutMode } = useDashboard();
  const location = useLocation();
  const isMobile = useIsMobile(768);
  const isCortex = location.pathname === '/cortex';
  const isFullWidth = location.pathname === '/developer' || isCortex;

  return (
    <div className={isCortex ? 'main-app-layout memory-route' : 'main-app-layout'} style={{ display: 'flex', flexDirection: layoutMode === 'header' ? 'column' : 'row', minHeight: '100vh', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
      {layoutMode === 'sidebar' && <div className="memory-sidebar-shell"><Sidebar /></div>}
      {layoutMode === 'header' && <AppHeader />}
      
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minHeight: layoutMode === 'header' ? 'calc(100vh - 70px)' : '100vh' }}>
        <div style={{ 
          padding: isFullWidth ? '0' : isMobile ? '1rem' : '2rem 3rem',
          maxWidth: isFullWidth ? 'none' : '1400px', 
          margin: '0 auto',
          width: '100%',
          flex: 1,
          display: 'flex',
          flexDirection: 'column'
        }}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
