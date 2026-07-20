// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { Terminal, Database, Activity, Cpu } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';

// Xibalba Solutions: API Request Stream Visualizer (v1.0)
// High-fidelity terminal-style scrolling feed for monitoring protocol API interactions.

export const RequestStream = () => {
    const [requests, setRequests] = useState<any[]>([]);
    const [load, setLoad] = useState(12);
    const [reqs, setReqs] = useState("2.4");
    const isMobile = useIsMobile();

    useEffect(() => {
        const endpoints = [
            { path: '/v1/agent/stats', method: 'GET', status: 200 },
            { path: '/v1/insurance/quote', method: 'POST', status: 201 },
            { path: '/v1/identity/upgrade', method: 'POST', status: 401 }, 
            { path: '/v1/reputation/proof', method: 'GET', status: 200 },
            { path: '/v1/blockchain/sync', method: 'PUT', status: 202 },
            { path: '/v1/auth/verify', method: 'POST', status: 200 }
        ];

        const generateRequest = () => {
            const ep = endpoints[Math.floor(Math.random() * endpoints.length)];
            const latency = Math.floor(Math.random() * 450) + 12;
            const bytes = Math.floor(Math.random() * 5000) + 120;
            
            return {
                id: Math.random().toString(36).substring(7),
                ...ep,
                latency,
                bytes,
                timestamp: new Date().toISOString()
            };
        };

        const updateMetrics = () => {
            setLoad(Math.floor(Math.random() * 15) + 5);
            setReqs((Math.random() * 4).toFixed(1));
        };

        // Initial seed
        setRequests(Array.from({ length: 8 }, generateRequest));
        updateMetrics();

        const interval = setInterval(() => {
            setRequests(prev => [generateRequest(), ...prev].slice(0, 50)); // Larger buffer for scrolling
            updateMetrics();
        }, 1800);

        return () => clearInterval(interval);
    }, []);

    return (
        <div className="enterprise-card" style={{ height: '100%', background: 'linear-gradient(180deg, #050d18 0%, #0a0b0d 100%)', border: '1px solid rgba(212, 175, 55, 0.15)', display: 'flex', flexDirection: 'column' }}>

            <div className="card-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', padding: '20px 24px', background: 'transparent' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(212, 175, 55, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gold)' }}>
                        <Terminal size={18} />
                    </div>
                    <div>
                        <h2 style={{ fontSize: '0.7rem', fontWeight: 800, color: 'white', textTransform: 'uppercase', letterSpacing: '0.2em', margin: 0 }}>API Request Stream</h2>
                        <span style={{ fontSize: '0.6rem', color: 'var(--gold)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Gateway Monitor v8.0</span>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.55rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700 }}>
                        <Cpu size={10} /> {load}% LOAD
                    </div>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981', boxShadow: '0 0 10px #10b981' }}></div>
                </div>
            </div>
            <div style={{ padding: '16px 24px', fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, borderBottom: '1px solid rgba(255,255,255,0.05)', textAlign: 'justify' }}>
                Live API gateway interactions and network traffic monitoring. Every cryptographic verification, score upgrade, and identity check passes through this secure layer.
            </div>

            {/* FIXED SIZE SCROLLING WINDOW */}
            <div className="card-body mono" style={{ flex: 1, padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                {!isMobile && (
                    <div style={{ padding: '12px 24px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', fontSize: '0.55rem', fontWeight: 900, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.1em' }}>
                        <span style={{ width: '60px' }}>STATUS</span>
                        <span style={{ width: '80px' }}>METHOD</span>
                        <span style={{ flex: 1 }}>ENDPOINT</span>
                        <span style={{ width: '70px', textAlign: 'right' }}>TIME</span>
                    </div>
                )}
                
                <div style={{ flex: 1, overflowY: 'auto', maxHeight: '420px', padding: isMobile ? '16px' : '12px 24px' }}>
                    <AnimatePresence initial={false}>
                        {requests.map((req) => (
                            <motion.div
                                key={req.id}
                                initial={{ opacity: 0, y: -20, scale: isMobile ? 0.95 : 1 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, scale: isMobile ? 0.95 : 1 }}
                                style={isMobile ? {
                                    // Mobile Pulse Card
                                    background: 'rgba(255,255,255,0.03)',
                                    borderRadius: '12px',
                                    padding: '16px',
                                    marginBottom: '12px',
                                    borderLeft: `4px solid ${req.status === 200 ? '#10b981' : req.status === 201 ? 'var(--gold)' : req.status >= 400 ? '#f43f5e' : 'white'}`,
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '8px'
                                } : {
                                    // Desktop Row
                                    display: 'flex',
                                    alignItems: 'center',
                                    padding: '8px 0',
                                    fontSize: '0.7rem',
                                    borderBottom: '1px solid rgba(255,255,255,0.02)',
                                    color: req.status >= 400 ? '#f43f5e' : 'rgba(255,255,255,0.7)'
                                }}
                            >
                                {isMobile ? (
                                    <>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                <div className="pulse" style={{ width: '8px', height: '8px', borderRadius: '50%', background: req.status === 200 ? '#10b981' : req.status === 201 ? 'var(--gold)' : req.status >= 400 ? '#f43f5e' : 'white', boxShadow: `0 0 8px ${req.status === 200 ? '#10b981' : req.status === 201 ? 'var(--gold)' : req.status >= 400 ? '#f43f5e' : 'white'}` }} />
                                                <span style={{ fontWeight: 900, color: 'white', fontSize: '0.85rem' }}>{req.method}</span>
                                            </div>
                                            <span style={{ 
                                                fontWeight: 800, 
                                                fontSize: '0.8rem',
                                                color: req.status === 200 ? '#10b981' : req.status === 201 ? 'var(--gold)' : req.status >= 400 ? '#f43f5e' : 'inherit'
                                            }}>
                                                {req.status}
                                            </span>
                                        </div>
                                        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', opacity: 0.9, color: 'white', wordBreak: 'break-all' }}>{req.path}</span>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', marginTop: '4px' }}>
                                            <span>{req.bytes} B</span>
                                            <span>{req.latency}ms</span>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <span style={{ 
                                            width: '60px', 
                                            fontWeight: 800, 
                                            color: req.status === 200 ? '#10b981' : req.status === 201 ? 'var(--gold)' : req.status >= 400 ? '#f43f5e' : 'inherit'
                                        }}>
                                            {req.status}
                                        </span>
                                        <span style={{ width: '80px', fontWeight: 900, color: 'white', fontSize: '0.65rem' }}>{req.method}</span>
                                        <span style={{ flex: 1, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', opacity: 0.9 }}>{req.path}</span>
                                        <span style={{ width: '70px', textAlign: 'right', fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)' }}>{req.latency}ms</span>
                                    </>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </div>

                <div style={{ padding: '16px 24px', background: 'rgba(212, 175, 55, 0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', gap: '20px' }}>
                        <div style={{ fontSize: '0.6rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)' }}>
                            REQ/S: <span style={{ color: 'white' }}>{reqs}</span>
                        </div>
                        <div style={{ fontSize: '0.6rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)' }}>
                            UPTIME: <span style={{ color: 'white' }}>99.99%</span>
                        </div>
                    </div>
                    <div style={{ fontSize: '0.55rem', color: 'var(--gold)', fontWeight: 800, letterSpacing: '0.1em' }}>
                        SECURE_CHANNEL_ESTABLISHED
                    </div>
                </div>
            </div>
        </div>
    );
};
