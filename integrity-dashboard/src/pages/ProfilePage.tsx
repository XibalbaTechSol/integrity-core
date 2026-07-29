import { useDashboard } from '../context/useDashboard';
import { useState, useEffect } from 'react';
import { userapi } from '../services/userapi';
import { User } from 'lucide-react';

export function ProfilePage() {
  const { user, addToast, fetchData } = useDashboard();
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(user?.name || '');
  
  const handleSave = async () => {
    if (!user) return;
    try {
      await userapi.updateProfile({ name });
      addToast('success', 'Profile updated successfully');
      setIsEditing(false);
      window.dispatchEvent(new Event('integrity-auth-changed'));
    } catch (err: any) {
      addToast('error', `Update failed: ${err.message}`);
    }
  };

  return (
    <div className="dash-section" style={{ padding: '40px' }}>


      <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', maxWidth: '800px' }}>
        <div className="enterprise-card p-6" style={{ padding: '32px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
            <div>
              <h3 className="heading-md text-gold">Personal Information</h3>
              {user && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '24px' }}>
                  <div style={{ width: '64px', height: '64px', background: 'linear-gradient(135deg, var(--gold) 0%, #a48130 100%)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--navy-deep)', fontWeight: 'bold', fontSize: '24px', boxShadow: '0 4px 12px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
                    {user.photoURL ? (
                      <img src={user.photoURL} alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <User size={32} style={{ color: 'var(--navy-deep)' }} />
                    )}
                  </div>
                  <div>
                    <h4 style={{ fontSize: '1.2rem', margin: 0, color: 'var(--text-primary)' }}>{user.name || 'Unnamed User'}</h4>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{user.email}</div>
                  </div>
                </div>
              )}
            </div>
            {!isEditing ? (
              <button className="btn btn-outline" onClick={() => setIsEditing(true)}>Edit Profile</button>
            ) : (
              <div style={{ display: 'flex', gap: '12px' }}>
                <button className="btn btn-outline" onClick={() => { setIsEditing(false); setName(user?.name || ''); }}>Cancel</button>
                <button className="btn btn-primary" onClick={handleSave}>Save</button>
              </div>
            )}
          </div>

          {user ? (
            <div style={{ display: 'grid', gap: '24px' }}>
              <div>
                <label className="text-sm font-bold text-slate mb-2" style={{ display: 'block' }}>Email Address</label>
                <input 
                  type="email" 
                  value={user.email} 
                  disabled 
                  style={{ 
                    width: '100%', padding: '12px 16px', background: 'var(--glass-surface)', 
                    border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', color: 'var(--text-muted)'
                  }} 
                />
              </div>
              <div>
                <label className="text-sm font-bold text-slate mb-2" style={{ display: 'block' }}>Display Name</label>
                <input 
                  type="text" 
                  value={name} 
                  onChange={(e) => setName(e.target.value)}
                  disabled={!isEditing}
                  placeholder="Enter your name"
                  style={{ 
                    width: '100%', padding: '12px 16px', background: isEditing ? 'rgba(255,255,255,0.05)' : 'var(--glass-surface)', 
                    border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)',
                    transition: 'all 0.2s'
                  }} 
                />
              </div>
            </div>
          ) : (
            <div className="text-muted">You are not signed in.</div>
          )}
        </div>


      </div>
    </div>
  );
}
