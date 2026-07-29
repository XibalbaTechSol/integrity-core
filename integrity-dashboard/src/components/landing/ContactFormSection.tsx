import React, { useState } from 'react';
import { Send, CheckCircle } from 'lucide-react';

export const ContactFormSection = () => {
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success'>('idle');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('submitting');
    setTimeout(() => {
      setStatus('success');
    }, 1500);
  };

  return (
    <div style={{ padding: '80px 20px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto', background: 'var(--navy-dark)', padding: '40px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h2 style={{ fontSize: '2rem', fontWeight: 700, color: 'white', marginBottom: '8px' }}>Get in Touch</h2>
          <p style={{ color: 'rgba(255,255,255,0.6)' }}>Ready to integrate verifiable agents? Contact our team.</p>
        </div>

        {status === 'success' ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <CheckCircle size={48} color="var(--gold-primary)" style={{ margin: '0 auto 16px' }} />
            <h3 style={{ color: 'white', fontSize: '1.25rem', marginBottom: '8px' }}>Message Received</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)' }}>We'll be in touch with you shortly.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', gap: '20px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem', marginBottom: '8px' }}>First Name</label>
                <input 
                  type="text" 
                  required
                  style={{ width: '100%', padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white' }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem', marginBottom: '8px' }}>Last Name</label>
                <input 
                  type="text" 
                  required
                  style={{ width: '100%', padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white' }}
                />
              </div>
            </div>
            
            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem', marginBottom: '8px' }}>Work Email</label>
              <input 
                type="email" 
                required
                style={{ width: '100%', padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem', marginBottom: '8px' }}>Company</label>
              <input 
                type="text" 
                required
                style={{ width: '100%', padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.8)', fontSize: '0.9rem', marginBottom: '8px' }}>How can we help?</label>
              <textarea 
                required
                rows={4}
                style={{ width: '100%', padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'white', resize: 'vertical' }}
              ></textarea>
            </div>

            <button 
              type="submit"
              disabled={status === 'submitting'}
              style={{
                width: '100%',
                padding: '14px',
                background: 'var(--gold-primary)',
                color: 'var(--navy-deep)',
                border: 'none',
                borderRadius: '6px',
                fontSize: '1rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: status === 'submitting' ? 'not-allowed' : 'pointer',
                opacity: status === 'submitting' ? 0.7 : 1,
                marginTop: '10px'
              }}
            >
              {status === 'submitting' ? 'Sending...' : 'Send Message'}
              {!status && <Send size={18} />}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
