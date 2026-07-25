// @ts-nocheck
import React, { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { motion } from 'framer-motion';
import { useIsMobile } from '../../utils/useIsMobile';
import { oracle } from '../../services/oracle';

interface HistoryData {
    timestamp: string;
    ais_score: number;
    entropy_score: number;
    grounding_score: number;
    sacrifice_score: number;
}

export const ReputationHistoryChart: React.FC<{ agentAddress?: string }> = ({ agentAddress }) => {
    const isMobile = useIsMobile();
    const [data, setData] = useState<HistoryData[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            if (!agentAddress) return;
            setIsLoading(true);
            try {
                // Real AIS history from the oracle (per-bucket component scores). agentAddress
                // is the DID (the roster key). Map bucket points onto the chart's shape.
                const points = await oracle.getAisHistory(agentAddress);
                setData(points.map((p) => ({
                    timestamp: new Date(p.bucket_start).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                    ais_score: p.ais,
                    entropy_score: p.entropy,
                    grounding_score: p.grounding,
                    sacrifice_score: p.sacrifice,
                })));
            } catch (error) {
                console.error("Failed to fetch history:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchData();
    }, [agentAddress]);

    if (isLoading && data.length === 0) return <div className="flex-center" style={{ height: '400px', opacity: 0.5 }}>Analyzing historical vectors...</div>;

    return (
        <div className="enterprise-card" style={{ padding: isMobile ? '20px' : '32px', height: isMobile ? '350px' : '400px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div className={`flex-${isMobile ? 'column' : 'between'} mb-8`} style={{ alignItems: isMobile ? 'flex-start' : 'center', gap: isMobile ? '12px' : 0 }}>
                <div>
                    <h4 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Reputation Trajectory</h4>
                    <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)' }}>Multi-vector historical analysis of agent trust metrics.</p>
                </div>
                <div className="badge badge-gold">7-DAY OVERVIEW</div>
            </div>

            <div style={{ width: '100%', height: '280px' }}>
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorAIS" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="var(--gold)" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="var(--gold)" stopOpacity={0}/>
                            </linearGradient>
                            <linearGradient id="colorEntropy" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#60a5fa" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <XAxis 
                            dataKey="timestamp" 
                            stroke="rgba(255,255,255,0.2)" 
                            fontSize={10} 
                            tickLine={false} 
                            axisLine={false}
                        />
                        <YAxis 
                            stroke="rgba(255,255,255,0.2)" 
                            fontSize={10} 
                            tickLine={false} 
                            axisLine={false}
                            domain={[0, 1000]}
                        />
                        <Tooltip 
                            contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                            itemStyle={{ fontWeight: 700 }}
                        />
                        <Legend iconType="circle" />
                        <Area 
                            type="monotone" 
                            dataKey="ais_score" 
                            name="Aggregate AIS"
                            stroke="var(--gold)" 
                            fillOpacity={1} 
                            fill="url(#colorAIS)" 
                            strokeWidth={3}
                        />
                        <Area 
                            type="monotone" 
                            dataKey="entropy_score" 
                            name="Entropy"
                            stroke="#60a5fa" 
                            fillOpacity={1} 
                            fill="url(#colorEntropy)" 
                            strokeWidth={2}
                        />
                        <Area 
                            type="monotone" 
                            dataKey="grounding_score" 
                            name="Grounding"
                            stroke="#10b981" 
                            fillOpacity={0} 
                            strokeWidth={2}
                        />
                        <Area 
                            type="monotone" 
                            dataKey="sacrifice_score" 
                            name="Sacrifice"
                            stroke="#f43f5e" 
                            fillOpacity={0} 
                            strokeWidth={2}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
