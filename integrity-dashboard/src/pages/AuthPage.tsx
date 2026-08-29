import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Key } from 'lucide-react';
import { userapi, UserApiError } from '../services/userapi';
import { useDashboard } from '../context/DashboardContext';

const AuthPage: React.FC = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { connectWallet } = useDashboard();

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isLogin) await userapi.login(email, password);
      else await userapi.register(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof UserApiError ? err.message : 'Authentication failed — check the userapi service is reachable.');
    } finally {
      setLoading(false);
    }
  };

  const handleWalletAuth = async () => {
    const connected = await connectWallet();
    if (connected) navigate('/dashboard');
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-color)', color: 'var(--text-primary)' }}>
      {/* Left side: Brand/Visual */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '4rem', background: 'var(--surface-color)', borderRight: '1px solid var(--border-color)' }}>
        <img src="/logo.png" alt="Xibalba Solutions" style={{ height: '48px', alignSelf: 'flex-start', marginBottom: 'auto' }} />
        <div style={{ marginTop: 'auto', marginBottom: 'auto' }}>
          <h1 style={{ fontSize: '3rem', marginBottom: '1rem', fontFamily: 'Raleway, sans-serif' }}>Access the Agentic Economy.</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.25rem', maxWidth: '500px', lineHeight: 1.6 }}>
            Sign in to manage your sovereign hardware endpoints, view protocol telemetry, and direct capital flow.
          </p>
        </div>
      </div>

      {/* Right side: Auth Form */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '4rem' }}>
        <div style={{ width: '100%', maxWidth: '400px' }}>
          <h2 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{isLogin ? 'Welcome Back' : 'Create Account'}</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
            {isLogin ? 'Enter your credentials to access the platform.' : 'Register to get started with Integrity Protocol.'}
          </p>

          <button onClick={handleWalletAuth} className="button" style={{ width: '100%', padding: '1rem', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.75rem', marginBottom: '2rem', background: '#333', color: 'white', border: '1px solid #555' }}>
            <Key size={18} />
            <span style={{ fontWeight: 600 }}>Continue with Web3 Wallet</span>
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
            <div style={{ flex: 1, height: '1px', background: 'var(--border-color)' }}></div>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>OR</span>
            <div style={{ flex: 1, height: '1px', background: 'var(--border-color)' }}></div>
          </div>

          <form onSubmit={handleAuth} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Email</label>
              <input type="email" required value={email} onChange={e => setEmail(e.target.value)} style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }} placeholder="john@example.com" />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Password</label>
              <input type="password" required value={password} onChange={e => setPassword(e.target.value)} style={{ width: '100%', padding: '0.75rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }} placeholder="••••••••" />
            </div>
            {error && <div style={{ color: 'var(--danger, #f44336)', fontSize: '0.85rem' }}>{error}</div>}
            <button type="submit" disabled={loading} className="button primary" style={{ width: '100%', padding: '1rem', marginTop: '0.5rem', display: 'flex', justifyContent: 'center', gap: '0.5rem' }}>
              {loading ? 'Working…' : isLogin ? 'Sign In' : 'Sign Up'} <ArrowRight size={18} />
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: '2rem', color: 'var(--text-secondary)' }}>
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <button onClick={() => { setIsLogin(!isLogin); setError(null); }} style={{ background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>
              {isLogin ? 'Sign Up' : 'Sign In'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthPage;
