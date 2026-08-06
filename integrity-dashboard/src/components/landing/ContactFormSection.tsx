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
    <div style={{ padding: '100px 20px', background: 'var(--navy-deep)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{ maxWidth: '650px', margin: '0 auto', background: 'linear-gradient(145deg, rgba(15,23,42,0.8) 0%, rgba(5,13,24,0.95) 100%)', padding: '48px', borderRadius: '24px', border: '1px solid rgba(212,175,55,0.2)', boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}>
        <div style={{ textAlign: 'center', marginBottom: '36px' }}>
          <span style={{ color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', display: 'block', marginBottom: '12px' }}>Connect With Us</span>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'white', marginBottom: '12px' }}>Get in Touch</h2>
          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '1rem' }}>Ready to integrate verifiable agents into your stack? Contact our team.</p>
        </div>

        {status === 'success' ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <CheckCircle size={56} color="var(--gold)" style={{ margin: '0 auto 16px' }} />
            <h3 style={{ color: 'white', fontSize: '1.4rem', fontWeight: 800, marginBottom: '8px' }}>Message Received</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)' }}>We'll be in touch with you shortly.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', gap: '20px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px' }}>First Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="Satoshi"
                  style={{ width: '100%', padding: '14px 16px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', color: 'white', fontSize: '0.95rem' }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px' }}>Last Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="Nakamoto"
                  style={{ width: '100%', padding: '14px 16px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', color: 'white', fontSize: '0.95rem' }}
                />
              </div>
            </div>
            
            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px' }}>Work Email</label>
              <input 
                type="email" 
                required
                placeholder="satoshi@bitcoin.org"
                style={{ width: '100%', padding: '14px 16px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', color: 'white', fontSize: '0.95rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px' }}>Company / Protocol</label>
              <input 
                type="text" 
                required
                placeholder="Autonomous Systems Lab"
                style={{ width: '100%', padding: '14px 16px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', color: 'white', fontSize: '0.95rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px' }}>How can we help?</label>
              <textarea 
                required
                rows={4}
                placeholder="Describe your agent architecture or integration requirements..."
                style={{ width: '100%', padding: '14px 16px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', color: 'white', fontSize: '0.95rem', resize: 'vertical' }}
              ></textarea>
            </div>

            <button 
              type="submit"
              disabled={status === 'submitting'}
              style={{
                width: '100%',
                padding: '16px',
                background: 'linear-gradient(135deg, var(--gold) 0%, #b89628 100%)',
                color: '#050d18',
                border: 'none',
                borderRadius: '12px',
                fontSize: '1rem',
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: status === 'submitting' ? 'not-allowed' : 'pointer',
                opacity: status === 'submitting' ? 0.7 : 1,
                marginTop: '12px',
                boxShadow: '0 10px 25px rgba(212,175,55,0.25)'
              }}
            >
              {status === 'submitting' ? 'Sending...' : 'Send Message'}
              {status !== 'submitting' && <Send size={18} />}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
