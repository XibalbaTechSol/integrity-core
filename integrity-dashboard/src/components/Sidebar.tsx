import { useState, useRef, useEffect } from 'react';
import { NavLink, Link } from 'react-router-dom';
import { LayoutDashboard, Key, DollarSign, Activity, ShieldCheck, Code, BrainCircuit, BookOpen, ChevronLeft, ChevronRight, User, Settings, LogIn, LogOut, Database } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { selectedAgent, setSelectedAgent, agents, user } = useDashboard();
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { to: '/identity', label: 'Identity', icon: <Key size={20} /> },
    { to: '/financials', label: 'Financials', icon: <DollarSign size={20} /> },
    { to: '/health', label: 'Health', icon: <Activity size={20} /> },
    { to: '/shield', label: 'Shield', icon: <ShieldCheck size={20} /> },
    { to: '/memory', label: 'Memory', icon: <Database size={20} /> },
    { to: '/intelligence', label: 'Intelligence', icon: <BrainCircuit size={20} /> },
    { to: '/prediction-markets', label: 'Prediction Markets', icon: <DollarSign size={20} /> },
    { to: '/developer', label: 'Developer', icon: <Code size={20} /> },
    { to: '/wiki', label: 'Wiki', icon: <BookOpen size={20} /> },
  ];

  return (
    <div style={{
      width: collapsed ? '80px' : '260px',
      background: 'var(--surface-color)',
      borderRight: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.3s ease',
      height: '100vh',
      position: 'sticky',
      top: 0
    }}>
      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', alignItems: 'center', borderBottom: '1px solid var(--border-color)', position: 'relative' }}>
        <Link to="/" style={{ display: 'block', textDecoration: 'none' }}>
          {!collapsed && <img src="/logo.png" alt="Logo" style={{ height: '32px', marginBottom: '0.5rem' }} />}
          {collapsed && <img src="/logo.png" alt="Logo" style={{ height: '24px', objectFit: 'contain' }} />}
        </Link>
        <button onClick={() => setCollapsed(!collapsed)} style={{ background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '50%', color: 'var(--text-secondary)', cursor: 'pointer', padding: '0.25rem', display: 'flex', alignItems: 'center', position: 'absolute', right: '-12px', top: '2rem' }}>
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {!collapsed && (
        <div style={{ padding: '1.5rem 1.5rem 0.5rem 1.5rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>Active Agent</div>
          <select
            value={selectedAgent?.id || ''}
            onChange={(e) => {
              const agent = agents.find(a => a.id === e.target.value);
              if (agent) setSelectedAgent(agent);
            }}
            disabled={agents.length === 0}
            style={{
              width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)',
              background: 'var(--bg-color)', color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'Raleway'
            }}
          >
            {agents.length === 0 && <option value="">No agents registered</option>}
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.alias || a.name || a.id}</option>
            ))}
          </select>
        </div>
      )}

      <nav style={{ flex: 1, padding: '1.5rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '1rem 0' : '1rem 1.25rem',
              background: isActive ? 'var(--theme-accent-muted)' : 'transparent',
              color: isActive ? 'var(--theme-accent)' : 'var(--text-secondary)',
              border: 'none',
              borderLeft: isActive ? '4px solid var(--theme-accent)' : '4px solid transparent',
              borderRadius: collapsed ? '4px' : '0 4px 4px 0',
              textDecoration: 'none',
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.2s'
            })}
            title={collapsed ? item.label : undefined}
          >
            {item.icon}
            {!collapsed && <span style={{ marginLeft: '1rem' }}>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* User Profile Block */}
      <div style={{ position: 'relative' }} ref={profileRef}>
        <div 
          onClick={() => setProfileMenuOpen(!profileMenuOpen)} 
          style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', cursor: 'pointer' }}
        >
          <img src={user?.avatarUrl || 'https://api.dicebear.com/7.x/identicon/svg?seed=guest'} alt="Avatar" style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'var(--bg-color)' }} />
          {!collapsed && (
            <div style={{ marginLeft: '1rem', overflow: 'hidden' }}>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{user?.name || 'Not signed in'}</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{user?.email || ''}</div>
            </div>
          )}
        </div>
        
        {profileMenuOpen && (
          <div style={{ 
            position: 'absolute', bottom: '100%', left: collapsed ? '1rem' : '1.5rem', marginBottom: '0.5rem', width: '200px', 
            background: 'var(--surface-color)', border: '1px solid var(--border-color)', borderRadius: '4px',
            display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 -4px 12px rgba(0,0,0,0.5)',
            zIndex: 100
          }}>
            <Link to="/settings" onClick={() => setProfileMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', textDecoration: 'none', color: 'var(--text-primary)', borderBottom: '1px solid var(--border-color)' }}>
              <User size={16} /> Profile
            </Link>
            <Link to="/settings" onClick={() => setProfileMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', textDecoration: 'none', color: 'var(--text-primary)', borderBottom: '1px solid var(--border-color)' }}>
              <Settings size={16} /> Settings
            </Link>
            <Link to="/auth" onClick={() => setProfileMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', textDecoration: 'none', color: 'var(--text-primary)', borderBottom: '1px solid var(--border-color)' }}>
              <LogIn size={16} /> Sign In / Up
            </Link>
            <Link to="/" onClick={() => setProfileMenuOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', textDecoration: 'none', color: 'var(--text-primary)' }}>
              <LogOut size={16} /> Sign Out
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
