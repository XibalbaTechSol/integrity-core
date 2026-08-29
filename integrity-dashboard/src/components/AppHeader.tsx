import { useState, useRef, useEffect } from 'react';
import { NavLink, Link } from 'react-router-dom';
import { LayoutDashboard, Key, DollarSign, Activity, ShieldCheck, Code, BrainCircuit, User, Settings, LogIn, LogOut } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { BCC_MIDDLEWARE_URL, GRAPH_MEMORY_URL, ORACLE_URL, SHIELD_BACKEND_URL } from '../config';

type ServiceState = 'checking' | 'online' | 'offline';

const serviceChecks = [
  { key: 'oracle', label: 'Oracle', url: `${ORACLE_URL}/healthz` },
  { key: 'bcc', label: 'BCC', url: `${BCC_MIDDLEWARE_URL}/health` },
  { key: 'memory', label: 'Memory', url: `${GRAPH_MEMORY_URL}/api/status` },
  { key: 'shield', label: 'Shield', url: `${SHIELD_BACKEND_URL}/api/shield/health` },
] as const;

export function AppHeader() {
  const { selectedAgent, setSelectedAgent, agents, user } = useDashboard();
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [serviceStates, setServiceStates] = useState<Record<string, ServiceState>>(
    Object.fromEntries(serviceChecks.map((service) => [service.key, 'checking'])) as Record<string, ServiceState>,
  );
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

  useEffect(() => {
    let cancelled = false;
    const checkServices = async () => {
      const results = await Promise.all(
        serviceChecks.map(async (service) => {
          try {
            const response = await fetch(service.url, { signal: AbortSignal.timeout(2500) });
            return [service.key, response.ok ? 'online' : 'offline'] as const;
          } catch {
            return [service.key, 'offline'] as const;
          }
        }),
      );
      if (!cancelled) setServiceStates(Object.fromEntries(results));
    };
    void checkServices();
    const interval = window.setInterval(checkServices, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);
  
  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
    { to: '/identity', label: 'Identity', icon: <Key size={18} /> },
    { to: '/financials', label: 'Financials', icon: <DollarSign size={18} /> },
    { to: '/health', label: 'Health', icon: <Activity size={18} /> },
    { to: '/shield', label: 'Shield', icon: <ShieldCheck size={18} /> },
    { to: '/intelligence', label: 'Intelligence', icon: <BrainCircuit size={18} /> },
    { to: '/prediction-markets', label: 'Prediction Markets', icon: <DollarSign size={18} /> },
    { to: '/developer', label: 'Developer', icon: <Code size={18} /> },
  ];

  return (
    <header style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'space-between', 
      padding: '0 2rem', 
      height: '70px',
      background: 'var(--surface-color)', 
      borderBottom: '1px solid var(--border-color)',
      position: 'sticky',
      top: 0,
      zIndex: 50
    }}>
      
      {/* Left: Logo */}
      <Link to="/" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none' }}>
        <img src="/logo.png" alt="Logo" style={{ height: '32px' }} />
      </Link>

      {/* Center: Navigation Links */}
      <nav style={{ display: 'flex', gap: '0.5rem', height: '100%' }}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0 1rem',
              height: '100%',
              background: 'transparent',
              color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              borderBottom: isActive ? '2px solid var(--text-primary)' : '2px solid transparent',
              textDecoration: 'none',
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.2s',
              boxSizing: 'border-box'
            })}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Right: Agent Selector and User */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
        <div className="app-service-status" aria-label="Service connectivity">
          {serviceChecks.map((service) => (
            <span
              key={service.key}
              className={`app-service-indicator ${serviceStates[service.key]}`}
              title={`${service.label}: ${serviceStates[service.key]}`}
            >
              <span aria-hidden="true" />
              {service.label}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Agent</span>
          <select
            value={selectedAgent?.id || ''}
            onChange={(e) => {
              const agent = agents.find(a => a.id === e.target.value);
              if (agent) setSelectedAgent(agent);
            }}
            disabled={agents.length === 0}
            style={{
              padding: '0.5rem 1rem', borderRadius: '4px', border: '1px solid var(--border-color)',
              background: 'var(--bg-color)', color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'Raleway'
            }}
          >
            {agents.length === 0 && <option value="">No agents registered</option>}
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.alias || a.name || a.id}</option>
            ))}
          </select>
        </div>

        <div style={{ position: 'relative' }} ref={profileRef}>
          <div
            onClick={() => setProfileMenuOpen(!profileMenuOpen)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', borderLeft: '1px solid var(--border-color)', paddingLeft: '1.5rem', cursor: 'pointer' }}
          >
            <img src={user?.avatarUrl || 'https://api.dicebear.com/7.x/identicon/svg?seed=guest'} alt="Avatar" style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'var(--bg-color)' }} />
          </div>
          {profileMenuOpen && (
            <div style={{ 
              position: 'absolute', top: '100%', right: 0, marginTop: '0.5rem', width: '200px', 
              background: 'var(--surface-color)', border: '1px solid var(--border-color)', borderRadius: '4px',
              display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
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
    </header>
  );
}
