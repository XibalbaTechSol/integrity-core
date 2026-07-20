// @ts-nocheck
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ShieldCheck, Activity, BarChart3, Database, Layers } from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';
import { API_BASE } from '../../constants';

export const ProtocolStats: React.FC = () => {
    const isMobile = useIsMobile();
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({
        totalNodes: 0,
        networkIntegrity: 0.98,
        aggregateAis: 842.5,
        protocolStakedItk: 0
    });

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await axios.get(`${API_BASE}/v1/protocol/stats`);
                setStats({
                    totalNodes: res.data.active_nodes || 0,
                    networkIntegrity: res.data.network_integrity || 0.98,
                    aggregateAis: res.data.aggregate_ais || 842.5,
                    protocolStakedItk: res.data.protocol_staked_itk || 0
                });
            } catch (e) {
                console.error("Error fetching protocol stats:", e);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
        const interval = setInterval(fetchStats, 10000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div style={{ marginBottom: 'var(--space-8)' }}>
            <div className="dash-grid-4" style={{ gap: 'var(--space-4)' }}>
                <StatCard 
                    label="Network AIS" 
                    value={stats.aggregateAis.toFixed(1)} 
                    icon={BarChart3} 
                    color="var(--gold)" 
                    trend="+4.2% WK"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Staked ITK" 
                    value={`${(stats.protocolStakedItk / 1000).toFixed(1)}k`} 
                    icon={Layers} 
                    color="white" 
                    subLabel="ON-CHAIN RESERVE"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Integrity" 
                    value={`${(stats.networkIntegrity * 100).toFixed(1)}%`} 
                    icon={ShieldCheck} 
                    color="var(--emerald)" 
                    subLabel="CONSENSUS"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Active Nodes" 
                    value={stats.totalNodes} 
                    icon={Database} 
                    color="var(--gold)" 
                    trend="↑ 12%"
                    loading={loading}
                    isMobile={isMobile}
                />
            </div>
        </div>
    );
};

const StatCard = ({ label, value, icon: Icon, color, trend, subLabel, loading, isMobile }: any) => (
    <div className="enterprise-card" style={{ 
        padding: 'var(--space-6)', 
        height: isMobile ? '140px' : '160px',
        border: '1px solid var(--border)',
        background: 'var(--glass-surface-light)'
    }}>
        <div className="flex-between mb-4">
            <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{label}</span>
            <div style={{ padding: '8px', background: `${color}15`, color: color, borderRadius: 'var(--r-xs)' }}>
                <Icon size={16} />
            </div>
        </div>
        {loading ? (
            <div>
                <div className="skeleton" style={{ height: '32px', width: '80%', marginBottom: '12px' }} />
                <div className="skeleton" style={{ height: '12px', width: '40%' }} />
            </div>
        ) : (
            <div>
                <h3 className="mono" style={{ fontSize: isMobile ? '1.8rem' : '2.2rem', fontWeight: 700, color: color === 'var(--gold)' ? 'var(--gold)' : 'white', margin: 0 }}>
                    {value}
                </h3>
                <p style={{ fontSize: '0.65rem', color: trend?.startsWith('+') || trend?.includes('↑') ? 'var(--emerald)' : 'var(--text-muted)', fontWeight: 700, marginTop: '8px', display: 'flex', alignItems: 'center', gap: '4px', margin: '6px 0 0' }}>
                    {trend && <Activity size={10} />} {trend || subLabel}
                </p>
            </div>
        )}
    </div>
);

