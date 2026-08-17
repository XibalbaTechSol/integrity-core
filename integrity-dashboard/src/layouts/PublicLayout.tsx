import React from 'react';
import { Link, Outlet } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

const PublicLayout: React.FC = () => {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.5rem 3rem', background: 'rgba(25, 25, 25, 0.8)', backdropFilter: 'blur(10px)', position: 'sticky', top: 0, zIndex: 100, borderBottom: '1px solid var(--border-color)' }}>
        <div>
          <Link to="/">
            <img src="https://xibalbatechsol.github.io/XibalbaSolutionsLogo.png" alt="Xibalba Solutions" style={{ height: '48px' }} />
          </Link>
        </div>
        <div>
          <Link to="/auth" className="button primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.5rem' }}>
            Launch MVP <ArrowRight size={16} />
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '4rem 2rem', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
        <Outlet />
      </main>

      {/* Footer */}
      <footer style={{ marginTop: 'auto', padding: '2rem 3rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <img src="https://xibalbatechsol.github.io/XibalbaSolutionsLogo.png" alt="Xibalba Solutions" style={{ height: '24px' }} />
          <span>&copy; {new Date().getFullYear()} Xibalba Solutions. All rights reserved.</span>
        </div>
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <Link to="/docs" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Documentation</Link>
          <Link to="/privacy" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Privacy Policy</Link>
          <Link to="/terms" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Terms of Service</Link>
          <a href="https://twitter.com/xibalba" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Twitter</a>
        </div>
      </footer>
    </div>
  );
};

export default PublicLayout;
