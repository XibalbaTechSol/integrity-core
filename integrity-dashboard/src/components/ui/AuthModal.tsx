import React from 'react';
import { X, LogIn, UserPlus, Loader2 } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';

// Real userapi email/password auth (replaces the old firebase Google popup). On
// success the provider's auth-change effect loads /me and the modal closes; on
// failure the form stays open with the error so the user can correct it.
export function AuthModal({ onClose }: { onClose: () => void }) {
  const { signIn, signUp } = useDashboard();
  const [mode, setMode] = React.useState<'login' | 'register'>('login');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') await signIn(email, password);
      else await signUp(email, password);
      onClose();
    } catch (err: any) {
      // userapi returns 401 on bad credentials, 409 on a duplicate registration.
      const status = err?.status;
      setError(
        status === 401 ? 'Incorrect email or password.'
          : status === 409 ? 'An account with that email already exists.'
          : (err?.message || 'Authentication failed. Try again.'),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={mode === 'login' ? 'Sign in' : 'Create account'}
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-6)', width: 'min(400px, 92vw)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex' }}>
            <X size={18} />
          </button>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" autoComplete="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={8} className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        {error && (
          <div role="alert" style={{ fontSize: '0.75rem', color: 'var(--danger)', background: 'var(--danger-dim)', padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
            {error}
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={busy} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : mode === 'login' ? <LogIn size={16} /> : <UserPlus size={16} />}
          {busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>

        <button
          type="button"
          onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); }}
          style={{ background: 'transparent', border: 'none', color: 'var(--gold)', cursor: 'pointer', fontSize: '0.75rem' }}
        >
          {mode === 'login' ? "Don't have an account? Create one" : 'Already have an account? Sign in'}
        </button>
      </form>
    </div>
  );
}
