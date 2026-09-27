import re

# 1. Update MainAppLayout to always show Sidebar and Topbar by removing isProtocol check
with open("src/layouts/MainAppLayout.tsx", "r") as f:
    layout = f.read()

layout = layout.replace("{layoutMode === 'sidebar' && !isProtocol && <div className=\"memory-sidebar-shell\"><Sidebar /></div>}", "{layoutMode === 'sidebar' && <div className=\"memory-sidebar-shell\"><Sidebar /></div>}")
# Wait, I'll just rewrite Sidebar.tsx instead.

with open("src/components/Sidebar.tsx", "w") as f:
    f.write("""import { Link, useLocation } from 'react-router-dom';
import { LockKeyhole } from 'lucide-react';
import { NAVIGATION_ITEMS } from '../navigation';
import '../pages/ProtocolDashboardPage.css';

export function Sidebar() {
  const location = useLocation();
  const routeTab = location.pathname.slice(1);
  const nav = NAVIGATION_ITEMS;

  return (
    <aside className="protocol-sidebar" style={{ position: 'fixed', left: 0, top: 0, height: '100vh', zIndex: 100 }}>
      <Link className="protocol-brand" to="/dashboard"><img src="/logo.png" alt="Integrity" /><span>PROTOCOL CORE</span></Link>
      <div className="protocol-network"><span>Network</span><strong><i />Base Sepolia</strong></div>
      <nav aria-label="Protocol navigation" tabIndex={0}>
        {nav.map(item => { 
          const Icon = item.icon; 
          return <Link key={item.to} aria-label={item.label} className={routeTab === item.to.slice(1) || (routeTab === 'overview' && item.to === '/dashboard') || (routeTab === '' && item.to === '/dashboard') ? 'active' : ''} to={item.to}><Icon size={17} /><span>{item.label}</span></Link>; 
        })}
      </nav>
      <div className="protocol-sidebar-foot"><LockKeyhole size={15} /><span>Key material never rendered</span><small>Protocol surface v1</small></div>
    </aside>
  );
}
""")

print("Rewrote Sidebar.tsx")
