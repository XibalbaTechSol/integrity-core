import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { Sidebar } from '../components/Sidebar';
import { AppHeader } from '../components/AppHeader';
import { useDashboard } from '../context/DashboardContext';
import { useIsMobile } from '../utils/useIsMobile';

export default function MainAppLayout() {
  const { layoutMode } = useDashboard();
  const location = useLocation();
  const appScrollRef = useRef<HTMLDivElement>(null);
  const contentScrollRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile(768);
  const isCortex = location.pathname === '/cortex';
  const isWiki = location.pathname === '/wiki';
  const isDeveloper = location.pathname === '/developer';
  const isFullWidth = ['/developer', '/security', '/knowledge'].includes(location.pathname) || isCortex || isWiki;

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    appScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    contentScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    const frame = window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: 'auto' }));
    return () => window.cancelAnimationFrame(frame);
  }, [location.pathname]);

  return (
    <div ref={appScrollRef} className={isCortex || isWiki ? 'main-app-layout memory-route' : 'main-app-layout'} style={{ display: 'flex', flexDirection: layoutMode === 'header' ? 'column' : 'row', minHeight: '100vh', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
      {layoutMode === 'sidebar' && <div className="memory-sidebar-shell"><Sidebar /></div>}
      {layoutMode === 'header' && <AppHeader />}
      
      <div ref={contentScrollRef} style={{ flex: 1, height: isDeveloper ? (layoutMode === 'header' ? 'calc(100vh - 70px)' : '100vh') : undefined, overflowY: isDeveloper ? 'hidden' : 'auto', display: 'flex', flexDirection: 'column', minHeight: isDeveloper ? 0 : layoutMode === 'header' ? 'calc(100vh - 70px)' : '100vh' }}>
        <div style={{ 
          padding: isFullWidth ? '0' : isMobile ? '1rem' : '2rem 3rem',
          maxWidth: isFullWidth ? 'none' : '1400px', 
          margin: '0 auto',
          width: '100%',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          height: isDeveloper ? '100%' : undefined
        }}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
