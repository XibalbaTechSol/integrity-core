import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Code, ArrowRight, FileText, ExternalLink, Shield, Eye, Lock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '../../utils/useIsMobile';

export const HeroSection = ({ setContactType, setIsContactOpen, setIsRegistryOpen }) => {
    const isMobile = useIsMobile();
    const navigate = useNavigate();

    return (
        <section style={{ padding: '160px 0 60px', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', inset: 0, opacity: 0.1, pointerEvents: 'none' }}>
                <div style={{ position: 'absolute', top: '20%', left: '50%', transform: 'translateX(-50%)', width: '600px', height: '600px', background: 'var(--gold)', filter: 'blur(150px)', borderRadius: '50%' }}></div>
            </div>
            
            <div className="container" style={{ position: 'relative', zIndex: 10 }}>
                <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <img 
                        src="/integrity/XibalbaSolutionsLogo.png" 
                        alt="Xibalba Logo" 
                        style={{ height: '220px', marginBottom: '40px', opacity: 1 }} 
                    />
                    <span style={{ color: 'var(--gold)', fontSize: isMobile ? '0.65rem' : '0.85rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.25em', marginBottom: '12px', display: 'block' }}>The Engine of Trust for the Agentic Economy</span>

                    <h1 style={{ fontSize: isMobile ? '1.8rem' : 'clamp(2rem, 5vw, 4rem)', marginBottom: '24px', fontFamily: 'Playfair Display, serif', lineHeight: 1.1, letterSpacing: '-0.02em', padding: isMobile ? '0 10px' : '0' }}>
                        Keep your autonomous agents <br /><span style={{ color: 'var(--gold)' }}>honest, reliable, and accountable.</span>
                    </h1>
                    <p style={{ fontSize: isMobile ? '0.95rem' : '1.15rem', color: 'rgba(255,255,255,0.85)', maxWidth: '900px', margin: '0 auto 32px', lineHeight: 1.7, fontWeight: 500, padding: isMobile ? '0 10px' : '0' }}>
                        The Integrity Protocol gives developers a rock-solid foundation for building <strong>AI agents they can actually trust</strong>.
                    </p>
                    <p style={{ fontSize: isMobile ? '0.85rem' : '1rem', color: 'rgba(255,255,255,0.4)', maxWidth: '850px', margin: '0 auto 48px', lineHeight: 1.8, padding: isMobile ? '0 10px' : '0' }}>
                        {isMobile ? 
                            "We capture exactly what your agents are doing to ensure complete visibility into their decisions." :
                            "We continuously monitor your agents in real-time, giving them a reliability score based on how strictly they follow your rules. We cryptographically prove they did the right thing without exposing your data, anchoring every action to the blockchain for an unchangeable public record of truth."
                        }
                    </p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center' }}>
                        <button 
                            onClick={() => { 
                                alert("Google Sign-In flow initiated. 1,000,000 ITK reward pending.");
                                navigate('/integrity');
                            }} 
                            className="btn" 
                            style={{ 
                                padding: isMobile ? '16px 24px' : '18px 40px', 
                                fontSize: '1rem', 
                                background: 'white', 
                                color: 'black', 
                                border: 'none', 
                                borderRadius: '12px',
                                display: 'flex', 
                                alignItems: 'center', 
                                gap: '12px',
                                cursor: 'pointer',
                                fontWeight: 600,
                                boxShadow: '0 4px 15px rgba(255, 255, 255, 0.2)'
                            }}
                        >
                            <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" style={{ width: '24px', height: '24px' }} />
                            Sign in with Google 
                            <span style={{ 
                                background: 'rgba(212, 175, 55, 0.1)', 
                                color: '#b8860b', 
                                padding: '4px 10px', 
                                borderRadius: '6px', 
                                fontSize: '0.85rem',
                                fontWeight: 800
                            }}>+1,000,000 ITK</span>
                        </button>
                        <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', flexDirection: isMobile ? 'column' : 'row', padding: isMobile ? '0 20px' : '0' }}>
                            <button 
                                onClick={() => { setContactType('investor'); setIsContactOpen(true); }} 
                                className="btn btn-primary" 
                                style={{ padding: isMobile ? '12px 20px' : '16px 32px', fontSize: '0.9rem' }}
                            >
                                <Mail size={18} /> Institutional Inquiries
                            </button>
                            <button 
                                onClick={() => { setContactType('developer'); setIsContactOpen(true); }} 
                                className="btn btn-outline" 
                                style={{ border: '1.5px solid rgba(255,255,255,0.2)', color: 'white', padding: isMobile ? '12px 20px' : '16px 32px', fontSize: '0.9rem', background: 'transparent', cursor: 'pointer', borderRadius: '12px' }}
                            >
                                <Code size={18} /> Developer Integration
                            </button>
                        </div>
                    </div>
                </motion.div>
            </div>
        </section>
    );
};
