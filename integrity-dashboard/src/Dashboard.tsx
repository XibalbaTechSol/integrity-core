import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ethers } from 'ethers';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis } from 'recharts';
import { COTPlatform } from './components/COTPlatform';
import { LayoutDashboard, Bell, Activity, Zap, Lock, AlertTriangle } from 'lucide-react';
import { Panel } from './components/shared/Panel';
import { useDashboard } from './context/DashboardContext';
import { oracle, AisHistoryPoint, AuditLogEntryDto, RecentTraceDto, AisResponse } from './services/oracle';

interface ActivityRow {
  id: string;
  task: string;
  status: string;
  latency: string;
  time: string;
}

const Dashboard: React.FC = () => {
  const { selectedAgent, agentsLoading } = useDashboard();
  const [ais, setAis] = useState<AisResponse | null>(null);
  const [stakedItk, setStakedItk] = useState<number | null>(null);
  const [history, setHistory] = useState<AisHistoryPoint[]>([]);
  const [flaggedRate, setFlaggedRate] = useState<number | null>(null);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [notifications, setNotifications] = useState<AuditLogEntryDto[]>([]);

  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    const id = selectedAgent.eth_address;

    oracle.getAis(id).then(r => { if (active) setAis(r); }).catch(() => { if (active) setAis(null); });
    oracle.getStake(id).then(r => { if (active) setStakedItk(Number(ethers.formatEther(r.total_stake))); }).catch(() => { if (active) setStakedItk(null); });
    oracle.getAisHistory(id, '1h').then(r => { if (active) setHistory(r); }).catch(() => { if (active) setHistory([]); });
    oracle.getTelemetry(id).then(events => {
      if (!active) return;
      setFlaggedRate(events.length ? events.filter(e => e.flagged).length / events.length : 0);
    }).catch(() => { if (active) setFlaggedRate(null); });
    oracle.getAuditLog(id, 5).then(r => { if (active) setNotifications(r); }).catch(() => { if (active) setNotifications([]); });

    oracle.getRecentTraces(id, 3).then(async (traces: RecentTraceDto[]) => {
      if (!active) return;
      const rows = await Promise.all(traces.map(async t => {
        try {
          const tree = await oracle.getTraceTree(t.trace_id);
          const root = tree.roots[0];
          return {
            id: t.trace_id.substring(0, 12),
            task: t.name,
            status: root?.status_code || 'UNSET',
            latency: root ? `${root.duration_ms}ms` : '-',
            time: new Date(t.start_time).toLocaleTimeString(),
          };
        } catch {
          return { id: t.trace_id.substring(0, 12), task: t.name, status: 'UNSET', latency: '-', time: new Date(t.start_time).toLocaleTimeString() };
        }
      }));
      setActivity(rows);
    }).catch(() => { if (active) setActivity([]); });

    return () => { active = false; };
  }, [selectedAgent?.id]);

  if (agentsLoading) {
    return <div style={{ padding: 'var(--space-8)', color: 'var(--text-muted)' }}>Loading agent fleet from the oracle…</div>;
  }
  if (!selectedAgent) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-muted)' }}>
        No registered agents found on this network. Register an agent under Identity to populate the dashboard.
      </div>
    );
  }

  // ais.components.* are on a 0-1000 scale (integrity-oracle scoring-core's
  // MAX_COMPONENT_SCORE = 1000, matching AIS itself), not a 0-1 fraction — dividing by
  // 10 maps it onto this radar's 0-100 domain. The previous `* 100` treated it as a
  // fraction, producing values like 100,000 for a perfect score: wildly outside
  // fullMark: 100, which made Recharts render a literal "NaN" tick/label on this chart.
  const radarData = ais ? [
    { subject: 'Entropy', A: (ais.components.entropy || 0) / 10, fullMark: 100 },
    { subject: 'Grounding', A: (ais.components.grounding || 0) / 10, fullMark: 100 },
    { subject: 'Sacrifice', A: (ais.components.sacrifice || 0) / 10, fullMark: 100 },
    { subject: 'Compliance', A: (ais.components.compliance || 0) / 10, fullMark: 100 },
    { subject: 'ZK-Boost', A: ais.zk_boost > 1 ? 100 : 0, fullMark: 100 },
  ] : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0 0 var(--space-2) 0' }}>Dashboard</h2>
          <p style={{ color: 'var(--text-muted)', margin: 0 }}>Live telemetry for {selectedAgent.alias || selectedAgent.name || selectedAgent.id}.</p>
        </div>
      </div>

      {/* ── Top Stats Row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)' }}>
        <Panel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
            <div style={{ padding: '8px', background: 'var(--primary-dim)', color: 'var(--primary)', borderRadius: '8px' }}>
              <Activity size={18} />
            </div>
            <h3 style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Live AIS Score</h3>
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {ais ? ais.ais.toFixed(1) : '—'}
          </div>
        </Panel>

        <Panel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
            <div style={{ padding: '8px', background: 'var(--primary-dim)', color: 'var(--primary)', borderRadius: '8px' }}>
              <Lock size={18} />
            </div>
            <h3 style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>$ITK Staked</h3>
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>{stakedItk !== null ? stakedItk.toLocaleString() : '—'}</div>
        </Panel>

        <Panel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
            <div style={{ padding: '8px', background: 'var(--primary-dim)', color: 'var(--primary)', borderRadius: '8px' }}>
              <Zap size={18} />
            </div>
            <h3 style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>ZK Boost</h3>
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>{ais ? (ais.zk_boost > 1 ? 'ACTIVE' : 'NONE') : '—'}</div>
        </Panel>

        <Panel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
            <div style={{ padding: '8px', background: 'var(--danger-dim)', color: 'var(--danger)', borderRadius: '8px' }}>
              <AlertTriangle size={18} />
            </div>
            <h3 style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Flagged Telemetry Rate</h3>
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>{flaggedRate !== null ? `${(flaggedRate * 100).toFixed(2)}%` : '—'}</div>
        </Panel>
      </div>

      {/* ── Charts Row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 'var(--space-4)' }}>
        <Panel>
          <h3 style={{ margin: '0 0 var(--space-4) 0', fontSize: '1.1rem' }}>AIS Trend (Last Hour Buckets)</h3>
          <div style={{ height: '280px' }}>
            {history.length === 0 ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>No history yet for this window.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history.map(h => ({ time: new Date(h.bucket_start).toLocaleTimeString(), ais: h.ais }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="time" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)', borderRadius: '8px', color: 'var(--text-primary)' }}
                    itemStyle={{ color: 'var(--primary)' }}
                  />
                  <Line type="monotone" dataKey="ais" stroke="var(--primary)" strokeWidth={3} dot={{ r: 4, fill: 'var(--primary)' }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        <Panel>
          <h3 style={{ margin: '0 0 var(--space-4) 0', fontSize: '1.1rem' }}>AIS Components (Radar)</h3>
          <div style={{ height: '280px' }}>
            {!ais ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>No AIS reading yet.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
                  <PolarGrid stroke="var(--border-color)" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar name="Agent" dataKey="A" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.3} />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)', borderRadius: '8px' }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>
      </div>

      {/* ── Tables Row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-4)', alignItems: 'start' }}>
        <Panel>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Recent Agent Activity</h3>
            <Link to="/intelligence" className="button" style={{ padding: '6px 12px', fontSize: '0.85rem', textDecoration: 'none' }}>View All</Link>
          </div>
          <div style={{ overflowX: 'auto' }}>
            {activity.length === 0 ? (
              <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>No recent traces.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase' }}>
                    <th style={{ padding: '12px 0', fontWeight: 600 }}>Trace ID</th>
                    <th style={{ padding: '12px 0', fontWeight: 600 }}>Task</th>
                    <th style={{ padding: '12px 0', fontWeight: 600 }}>Status</th>
                    <th style={{ padding: '12px 0', fontWeight: 600 }}>Latency</th>
                    <th style={{ padding: '12px 0', fontWeight: 600 }}>Time</th>
                  </tr>
                </thead>
                <tbody style={{ fontSize: '0.95rem' }}>
                  {activity.map((row, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '16px 0', fontFamily: 'monospace', color: 'var(--text-primary)' }}>{row.id}</td>
                      <td style={{ padding: '16px 0', color: 'var(--text-secondary)' }}>{row.task}</td>
                      <td style={{ padding: '16px 0' }}>
                        <span style={{
                          padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600,
                          background: row.status === 'OK' ? 'var(--success-dim)' : 'var(--primary-dim)',
                          color: row.status === 'OK' ? 'var(--success)' : 'var(--primary)'
                        }}>
                          {row.status}
                        </span>
                      </td>
                      <td style={{ padding: '16px 0', color: 'var(--text-secondary)' }}>{row.latency}</td>
                      <td style={{ padding: '16px 0', color: 'var(--text-muted)' }}>{row.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Panel>

        <Panel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
            <Bell size={18} color="var(--primary)" />
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Policy Audit Feed</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {notifications.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No audit events recorded yet.</div>
            ) : notifications.map(n => (
              <div key={n.id} style={{
                padding: '12px 16px',
                background: n.decision === 'DENY' ? 'var(--danger-dim)' : 'var(--success-dim)',
                borderLeft: `3px solid ${n.decision === 'DENY' ? 'var(--danger)' : 'var(--success)'}`,
                borderRadius: '0 6px 6px 0', fontSize: '0.9rem'
              }}>
                <strong style={{ color: n.decision === 'DENY' ? 'var(--danger)' : 'var(--success)' }}>{n.decision}:</strong> {n.event_type} {n.reason_code ? `(${n.reason_code})` : ''}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {/* ── COT Explorer ── */}
      <Panel>
        <h3 style={{ margin: '0 0 var(--space-4) 0', fontSize: '1.1rem' }}>Observability: Chain-of-Thought Explorer</h3>
        <COTPlatform />
      </Panel>
    </div>
  );
};

export default Dashboard;
