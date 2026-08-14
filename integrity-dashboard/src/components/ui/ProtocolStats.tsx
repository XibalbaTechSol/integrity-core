// @ts-nocheck
import React from 'react';
import { ShieldCheck, Activity, BarChart3, Database, Layers } from 'lucide-react';
import { useIsMobile } from '../../utils/useIsMobile';
import { useDashboard } from '../../context/DashboardContext';

export const ProtocolStats: React.FC = () => {
    const isMobile = useIsMobile();
    // Real protocol-wide values from the context (DashboardProvider derives these from live
    // oracle reads across the agent set) — not the legacy /v1/protocol/stats mock. Network
    // "integrity" is the aggregate AIS as a fraction of the 1000-point scale.
    const { stats } = useDashboard();
    const loading = !stats;
    const s = {
        totalNodes: stats?.active_nodes ?? 0,
        networkIntegrity: stats ? Math.min((stats.aggregate_ais || 0) / 1000, 1) : 0,
        aggregateAis: stats?.aggregate_ais ?? 0,
        protocolStakedItk: stats?.protocol_staked_itk ?? 0,
    };

    return (
        <div style={{ marginBottom: 'var(--space-8)' }}>
            <div className="dash-grid-4" style={{ gap: 'var(--space-4)' }}>
                <StatCard 
                    label="Network AIS" 
                    value={s.aggregateAis.toFixed(1)} 
                    icon={BarChart3} 
                    color="var(--theme-accent)" 
                    trend="+4.2% WK"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Staked ITK" 
                    value={`${(s.protocolStakedItk / 1000).toFixed(1)}k`} 
                    icon={Layers} 
                    color="white" 
                    subLabel="ON-CHAIN RESERVE"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Integrity" 
                    value={`${(s.networkIntegrity * 100).toFixed(1)}%`} 
                    icon={ShieldCheck} 
                    color="var(--emerald)" 
                    subLabel="CONSENSUS"
                    loading={loading}
                    isMobile={isMobile}
                />
                <StatCard 
                    label="Active Nodes" 
                    value={s.totalNodes} 
                    icon={Database} 
                    color="var(--theme-accent)" 
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
                <h3 className="mono" style={{ fontSize: isMobile ? '1.8rem' : '2.2rem', fontWeight: 700, color: color === 'var(--theme-accent)' ? 'var(--theme-accent)' : 'white', margin: 0 }}>
                    {value}
                </h3>
                <p style={{ fontSize: '0.65rem', color: trend?.startsWith('+') || trend?.includes('↑') ? 'var(--emerald)' : 'var(--text-muted)', fontWeight: 700, marginTop: '8px', display: 'flex', alignItems: 'center', gap: '4px', margin: '6px 0 0' }}>
                    {trend && <Activity size={10} />} {trend || subLabel}
                </p>
            </div>
        )}
    </div>
);

