import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { LockKeyhole, LogOut, Settings, User } from 'lucide-react';
import { userapi } from '../services/userapi';


import { NAVIGATION_ITEMS } from '../navigation';
import '../pages/ProtocolDashboardPage.css';

export function Sidebar() {
  const [profileOpen, setProfileOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await userapi.logout();
    } catch(e) {}
    navigate('/auth');
  };

  const location = useLocation();
  const routeTab = location.pathname.slice(1);
  const nav = NAVIGATION_ITEMS;

  return (
    <aside className="protocol-sidebar" >
      <Link className="protocol-brand" to="/dashboard"><img src="/logo.png" alt="Integrity" /><span>PROTOCOL CORE</span></Link>
      <div className="protocol-network"><span>Network</span><strong><i />Base Sepolia</strong></div>
      <nav aria-label="Protocol navigation" tabIndex={0}>
        {nav.map(item => {
          const Icon = item.icon;
          return <Link key={item.to} aria-label={item.label} className={routeTab === item.to.slice(1) || (routeTab === 'overview' && item.to === '/dashboard') || (routeTab === '' && item.to === '/dashboard') ? 'active' : ''} to={item.to}><Icon size={17} /><span>{item.label}</span></Link>;
        })}
      </nav>
            <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div className="protocol-sidebar-foot"><LockKeyhole size={15} /><span>Key material never rendered</span><small>Protocol surface v1</small></div>

        <div className={`sidebar-profile ${profileOpen ? 'open' : ''}`} onClick={() => setProfileOpen(!profileOpen)}>
          <div className="profile-avatar"><User size={15} /></div>
          <div className="profile-info">
            <span>Operator</span>
            <small>Authenticated</small>
          </div>

          {profileOpen && (
            <div className="profile-dropdown">
              <Link to="/system" onClick={(e) => e.stopPropagation()}><Settings size={14} /> System settings</Link>
              <button onClick={(e) => { e.stopPropagation(); handleLogout(); }}><LogOut size={14} /> Disconnect</button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
