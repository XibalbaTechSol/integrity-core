// @ts-nocheck
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, CheckCircle, Loader2 } from 'lucide-react';
import axios from 'axios';
import { API_BASE } from '../../constants';

interface ContactModalProps {
    isOpen: boolean;
    onClose: () => void;
    initialType?: 'investor' | 'developer';
}

export const ContactModal: React.FC<ContactModalProps> = ({ isOpen, onClose, initialType = 'investor' }) => {
    const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        organization: '',
        inquiry_type: initialType === 'investor' ? 'Investment & Institutional' : 'Developer Integration',
        message: ''
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus('loading');
        
        try {
            const response = await fetch('https://integrity-protocol-backend.onrender.com/v1/contact', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    name: formData.name,
                    email: formData.email,
                    organization: formData.organization,
                    inquiry_type: formData.inquiry_type,
                    message: formData.message
                })
            });
            
            if (response.ok) {
                setStatus('success');
                setTimeout(() => {
                    onClose();
                    setStatus('idle');
                    setFormData({ ...formData, message: '' }); // reset message
                }, 3000);
            } else {
                throw new Error('Form submission failed');
            }
        } catch (error) {
            console.error("Error submitting contact form", error);
            setStatus('error');
            setTimeout(() => setStatus('idle'), 3000);
        }
    };

    if (!isOpen) return null;

    return (
        <AnimatePresence>
            <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={onClose}
                    style={{ position: 'absolute', inset: 0, background: 'rgba(5, 13, 24, 0.8)', backdropFilter: 'blur(8px)' }}
                />
                
                <motion.div 
                    initial={{ opacity: 0, y: 50, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 20, scale: 0.95 }}
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                    style={{ 
                        position: 'relative', 
                        zIndex: 10000, 
                        width: '100%', 
                        maxWidth: '600px', 
                        background: 'var(--navy-light)',
                        border: '1px solid rgba(212, 175, 55, 0.2)',
                        borderRadius: '24px',
                        padding: '40px',
                        boxShadow: '0 40px 100px rgba(0,0,0,0.6)'
                    }}
                >
                    <button 
                        onClick={onClose}
                        style={{ position: 'absolute', top: '24px', right: '24px', background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', padding: '8px' }}
                    >
                        <X size={24} />
                    </button>

                    {status === 'success' ? (
                        <div style={{ textAlign: 'center', padding: '60px 0' }}>
                            <CheckCircle size={64} style={{ color: 'var(--gold)', margin: '0 auto 24px' }} />
                            <h2 style={{ fontSize: '2rem', marginBottom: '16px', fontFamily: 'Playfair Display, serif' }}>Inquiry Received</h2>
                            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '1.1rem' }}>Thank you for reaching out to Xibalba Solutions. Our team will review your message and respond shortly.</p>
                        </div>
                    ) : (
                        <>
                            <div style={{ marginBottom: '32px' }}>
                                <span style={{ color: 'var(--gold)', fontSize: '0.6rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.2em' }}>Xibalba Solutions</span>
                                <h2 style={{ fontSize: '2rem', marginTop: '8px', fontFamily: 'Playfair Display, serif' }}>Contact Us</h2>
                                <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', marginTop: '8px' }}>Send us a message and we'll route it directly to the appropriate team.</p>
                            </div>

                            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Full Name</label>
                                        <input 
                                            required
                                            name="name"
                                            value={formData.name}
                                            onChange={handleChange}
                                            type="text" 
                                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', padding: '16px', borderRadius: '12px', color: 'white', fontSize: '1rem', outline: 'none' }} 
                                        />
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Email Address</label>
                                        <input 
                                            required
                                            name="email"
                                            value={formData.email}
                                            onChange={handleChange}
                                            type="email" 
                                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', padding: '16px', borderRadius: '12px', color: 'white', fontSize: '1rem', outline: 'none' }} 
                                        />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Organization</label>
                                        <input 
                                            name="organization"
                                            value={formData.organization}
                                            onChange={handleChange}
                                            type="text" 
                                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', padding: '16px', borderRadius: '12px', color: 'white', fontSize: '1rem', outline: 'none' }} 
                                        />
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Inquiry Type</label>
                                        <select 
                                            name="inquiry_type"
                                            value={formData.inquiry_type}
                                            onChange={handleChange}
                                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', padding: '16px', borderRadius: '12px', color: 'white', fontSize: '1rem', outline: 'none', appearance: 'none' }}
                                        >
                                            <option value="Investment & Institutional">Investment & Institutional</option>
                                            <option value="Developer Integration">Developer Integration</option>
                                            <option value="General Inquiry">General Inquiry</option>
                                        </select>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Message</label>
                                    <textarea 
                                        required
                                        name="message"
                                        value={formData.message}
                                        onChange={handleChange}
                                        rows={4} 
                                        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', padding: '16px', borderRadius: '12px', color: 'white', fontSize: '1rem', outline: 'none', resize: 'vertical' }} 
                                    />
                                </div>

                                {status === 'error' && (
                                    <div style={{ color: '#ef4444', fontSize: '0.85rem', textAlign: 'center', marginTop: '8px' }}>
                                        There was an error sending your message. Please try again.
                                    </div>
                                )}

                                <button 
                                    type="submit" 
                                    disabled={status === 'loading'}
                                    className="btn btn-primary" 
                                    style={{ width: '100%', padding: '20px', marginTop: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}
                                >
                                    {status === 'loading' ? (
                                        <><Loader2 className="animate-spin" size={20} /> Sending...</>
                                    ) : (
                                        <><Send size={20} /> Send Inquiry</>
                                    )}
                                </button>
                            </form>
                        </>
                    )}
                </motion.div>
            </div>
        </AnimatePresence>
    );
};
