import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { useIsMobile } from '../../utils/useIsMobile';
import { useDashboard } from '../../context/useDashboard';
import { oracle } from '../../services/oracle';
import { Activity, Filter } from 'lucide-react';

export const TelemetryGraphs = () => {
  const isMobile = useIsMobile();
  const { agents } = useDashboard();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);

  // Default to the real telemetry metrics the oracle actually reports.
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(['performance_variance', 'hgi_raw']);

  // Real telemetry time-series: aggregate each live agent's real
  // TelemetryEventDetailDto stream (getTelemetry) into per-event chart points.
  // The legacy chart's latency/accuracy/cpu/memory have no oracle source; the
  // real fields (performance_variance, hgi_raw, gpu_hours_verified) do -- so the
  // chart plots those rather than fabricating the missing ones.
  useEffect(() => {
    let cancelled = false;
    const fetchTelemetry = async () => {
      try {
        const perAgent = await Promise.all(
          agents.map((a) =>
            oracle
              .getTelemetry(a.eth_address)
              .then((events) =>
                events.map((e) => ({ e, agent: a.alias })),
              )
              .catch(() => [] as { e: any; agent: string }[]),
          ),
        );
        const sorted = perAgent
          .flat()
          .sort((x, y) => new Date(x.e.created_at).getTime() - new Date(y.e.created_at).getTime());

        const formatted = sorted.map(({ e, agent }) => {
          const date = new Date(e.created_at);
          return {
            // Absolute epoch ms — the real X coordinate. The previous HH:MM:SS *string*
            // discarded the date, so identical clock times on different days collapsed
            // onto the same categorical tick and the axis cycled instead of advancing.
            ts: date.getTime(),
            performance_variance: e.performance_variance,
            hgi_raw: e.hgi_raw,
            gpu_hours_verified: e.gpu_hours_verified,
            agent,
          };
        });

        if (cancelled) return;
        setData(formatted);
        const unique = Array.from(new Set(formatted.map((d) => d.agent)));
        setSelectedAgents((prev) => (prev.length === 0 ? unique : prev));
      } catch (e) {
        console.error('Telemetry fetch error:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [agents]);

  const uniqueAgentsList = useMemo(() => {
    const unique = new Set<string>();
    data.forEach(d => unique.add(d.agent));
    return Array.from(unique);
  }, [data]);

  // Real telemetry metrics reported by the oracle (TelemetryEventDetailDto).
  const METRICS = [
    { id: 'performance_variance', label: 'Performance Variance', color: '#f43f5e' },
    { id: 'hgi_raw', label: 'Grounding Index (HGI)', color: '#10b981' },
    { id: 'gpu_hours_verified', label: 'GPU Hours Verified', color: '#d4af37' }
  ];

  const toggleMetric = (id: string) => {
    setSelectedMetrics(prev => 
      prev.includes(id) 
        ? prev.filter(m => m !== id)
        : [...prev, id]
    );
  };

  const activeMetrics = METRICS.filter(m => selectedMetrics.includes(m.id));

  // Transform into correlated rows keyed on the ABSOLUTE timestamp, then sorted
  // chronologically so the numeric time axis is monotonic. Each row carries every
  // agent×metric value present at that instant; missing ones stay undefined and the
  // series `connectNulls` across them (each agent is an independent event stream, so
  // exact-ms coincidence between agents is rare and expected).
  const formattedChartData = useMemo(() => {
    const timeGroups: Record<number, any> = {};
    data.forEach(d => {
      const timeKey = d.ts;
      if (!timeGroups[timeKey]) {
        timeGroups[timeKey] = { ts: timeKey };
      }
      METRICS.forEach(m => {
        timeGroups[timeKey][`${d.agent}_${m.id}`] = d[m.id];
      });
    });
    return Object.values(timeGroups).sort((a, b) => a.ts - b.ts);
  }, [data]);

  // Readable HH:MM(:SS) label for a given epoch-ms tick. Seconds are shown only when the
  // visible span is short enough that minute-resolution ticks would collide.
  const fmtTime = (ts: number) => {
    const d = new Date(ts);
    const hh = d.getHours().toString().padStart(2, '0');
    const mm = d.getMinutes().toString().padStart(2, '0');
    return `${hh}:${mm}`;
  };
  const fmtTimeFull = (ts: number) => {
    const d = new Date(ts);
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  // Generate distinct colors & lines for each selected agent & metric combination
  const activeSeries = useMemo(() => {
    const series: { id: string; label: string; color: string; dataKey: string }[] = [];
    const colors = ['#f43f5e', '#10b981', '#d4af37', '#8b5cf6', '#ec4899', '#0ea5e9', '#f59e0b', '#3b82f6'];
    
    selectedAgents.forEach((agent, agentIdx) => {
      activeMetrics.forEach((metric, metricIdx) => {
        const colorIndex = (metricIdx + agentIdx * activeMetrics.length) % colors.length;
        series.push({
          id: `${agent}_${metric.id}`,
          label: `${agent.split(' ').slice(-1)[0]} - ${metric.label}`,
          color: colors[colorIndex],
          dataKey: `${agent}_${metric.id}`
        });
      });
    });
    return series;
  }, [selectedAgents, activeMetrics]);

  return (
    <div className="enterprise-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '40px', borderRadius: '16px', overflow: 'hidden' }}>
      <div className="card-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', padding: isMobile ? '16px' : '24px 32px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px', background: 'linear-gradient(90deg, rgba(255,255,255,0.02) 0%, transparent 100%)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(16, 185, 129, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#10b981', boxShadow: '0 0 20px rgba(16, 185, 129, 0.2)' }}>
            <Activity size={20} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <h2 style={{ fontSize: '0.85rem', fontWeight: 800, color: 'white', textTransform: 'uppercase', letterSpacing: '0.25em', fontFamily: 'Inter, sans-serif', margin: 0 }}>Multi-Metric Telemetry</h2>
            <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.2em', marginTop: '4px' }}>Correlated Data Streams</span>
          </div>
        </div>

        {/* Global Agent Multi-Checkboxes Filter */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Plot Nodes:</span>
          {uniqueAgentsList.map(agent => {
            const isChecked = selectedAgents.includes(agent);
            return (
              <label 
                key={agent} 
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px', 
                  background: isChecked ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255,255,255,0.02)', 
                  border: `1px solid ${isChecked ? '#10b981' : 'rgba(255,255,255,0.1)'}`,
                  padding: '4px 10px', 
                  borderRadius: '6px', 
                  fontSize: '0.7rem', 
                  color: isChecked ? '#10b981' : 'rgba(255,255,255,0.5)', 
                  cursor: 'pointer',
                  fontWeight: 600,
                  transition: 'all 0.15s'
                }}
              >
                <input 
                  type="checkbox" 
                  checked={isChecked}
                  onChange={() => {
                    setSelectedAgents(prev => 
                      prev.includes(agent)
                        ? prev.filter(a => a !== agent)
                        : [...prev, agent]
                    );
                  }}
                  style={{ display: 'none' }}
                />
                {agent}
              </label>
            );
          })}
        </div>
      </div>

      <div style={{ padding: isMobile ? '16px' : '24px 32px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Metric Toggles */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
          {METRICS.map(m => {
            const isActive = selectedMetrics.includes(m.id);
            return (
              <button
                key={m.id}
                onClick={() => toggleMetric(m.id)}
                style={{
                  background: isActive ? `${m.color}20` : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${isActive ? m.color : 'rgba(255,255,255,0.1)'}`,
                  color: isActive ? '#fff' : 'rgba(255,255,255,0.5)',
                  padding: '6px 14px',
                  borderRadius: '20px',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: isActive ? `0 0 10px ${m.color}30` : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: isActive ? m.color : 'transparent', border: `1px solid ${m.color}` }} />
                {m.label}
              </button>
            );
          })}
        </div>

        {/* Main Area Chart */}
        <div style={{ width: '100%', height: '400px', position: 'relative' }}>
          {loading && data.length === 0 ? (
            <div className="skeleton" style={{ width: '100%', height: '100%', borderRadius: '12px' }} />
          ) : selectedAgents.length > 0 && activeSeries.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={formattedChartData} margin={{ top: 20, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  {activeSeries.map(s => (
                    <linearGradient key={`color-${s.id}`} id={`color-${s.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={s.color} stopOpacity={0.2}/>
                      <stop offset="95%" stopColor={s.color} stopOpacity={0}/>
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="ts"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={fmtTime}
                  stroke="rgba(255,255,255,0.2)"
                  fontSize={10}
                  tickMargin={10}
                />
                <YAxis stroke="rgba(255,255,255,0.2)" fontSize={10} />
                <Tooltip
                  labelFormatter={(ts) => fmtTimeFull(ts as number)}
                  contentStyle={{ background: 'rgba(5, 13, 24, 0.9)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}
                  itemStyle={{ fontSize: '0.8rem', fontWeight: 600 }}
                  labelStyle={{ color: 'rgba(255,255,255,0.5)', marginBottom: '8px', fontSize: '0.7rem' }}
                />
                {activeSeries.map(s => (
                  <Area
                    key={s.id}
                    type="monotone"
                    dataKey={s.dataKey}
                    stroke={s.color}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill={`url(#color-${s.id})`}
                    name={s.label}
                    connectNulls
                    activeDot={{ r: 6, strokeWidth: 0, fill: s.color, style: { filter: `drop-shadow(0 0 8px ${s.color})` } }}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px dashed rgba(255,255,255,0.1)' }}>
              Select at least one agent node to render telemetry streams.
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

