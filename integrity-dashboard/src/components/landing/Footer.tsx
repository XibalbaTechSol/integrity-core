import React from 'react';
import { Shield } from 'lucide-react';

export const Footer = () => {
  return (
    <footer style={{
      background: 'var(--navy-deep)',
      borderTop: '1px solid rgba(255,255,255,0.05)',
      padding: '60px 20px 30px',
      color: 'rgba(255,255,255,0.7)'
    }}>
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '40px',
        marginBottom: '40px'
      }}>
        {/* Brand Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'white' }}>
            <Shield size={24} color="var(--gold-primary)" />
            <span style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.05em' }}>XIBALBA</span>
          </div>
          <p style={{ fontSize: '0.95rem', lineHeight: '1.6' }}>
            Building the trust layer for the autonomous agent economy. 
            Execute, verify, and transact on-chain with cryptographic certainty.
          </p>
          <div style={{ display: 'flex', gap: '16px', marginTop: '8px' }}>
            <a href="https://x.com/JacobSVickers" target="_blank" rel="noreferrer" style={{ color: 'rgba(255,255,255,0.5)', transition: 'color 0.2s' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
            </a>
            <a href="https://linkedin.com/in/jacobvickers" target="_blank" rel="noreferrer" style={{ color: 'rgba(255,255,255,0.5)', transition: 'color 0.2s' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path><rect x="2" y="9" width="4" height="12"></rect><circle cx="4" cy="4" r="2"></circle></svg>
            </a>
            <a href="https://github.com/XibalbaTechSol" target="_blank" rel="noreferrer" style={{ color: 'rgba(255,255,255,0.5)', transition: 'color 0.2s' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path></svg>
            </a>
          </div>
        </div>

        {/* Links Column 1 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h4 style={{ color: 'white', fontWeight: 600, fontSize: '1.05rem', marginBottom: '8px' }}>Protocol</h4>
          <a href="#features" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>Platform</a>
          <a href="#validation" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>Validation Loop</a>
          <a href="#architecture" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>Architecture</a>
          <a href="#faq" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>FAQ</a>
        </div>

        {/* Links Column 2 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h4 style={{ color: 'white', fontWeight: 600, fontSize: '1.05rem', marginBottom: '8px' }}>Company</h4>
          <a href="https://xibalbatechsol.github.io" target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>About Founder</a>
          <a href="#contact" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>Request Pilot</a>
          <a href="https://xibalbatechsol.github.io/docs/xibalba_shield_proposal.pdf" target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none', transition: 'color 0.2s', fontSize: '0.95rem' }}>Whitepaper</a>
        </div>
      </div>

      {/* Bottom Bar */}
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        paddingTop: '24px',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px',
        fontSize: '0.85rem',
        color: 'rgba(255,255,255,0.4)'
      }}>
        <span>&copy; {new Date().getFullYear()} Xibalba Solutions LLC. All rights reserved.</span>
        <div style={{ display: 'flex', gap: '24px' }}>
          <span style={{ cursor: 'pointer' }}>Privacy Policy</span>
          <span style={{ cursor: 'pointer' }}>Terms of Service</span>
        </div>
      </div>
    </footer>
  );
};
