import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Brain, GitBranch, Zap, TrendingUp, FlaskConical } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { TelemetryPanel } from '../components/tabs/TelemetryPanel';
import { TraceAnalysisPanel } from '../components/tabs/TraceAnalysisPanel';
import { IntegrityRadar } from '../components/shared/IntegrityRadar';
import { useDashboard } from '../context/useDashboard';

// ... (keep existing types and sub-components)

// ─── Types ───────────────────────────────────────────────────────────────────

type IntelTab = 'telemetry' | 'reasoning' | 'trajectory';

interface StatCardProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent?: string;
}

// ─── Sub-components ──────────────────────────────────────────────────────────

const LiveBadge = () => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '3px 10px',
      background: 'rgba(34, 197, 94, 0.12)',
      border: '1px solid var(--success)',
      borderRadius: '999px',
      fontSize: '0.65rem',
      fontWeight: 700,
      letterSpacing: '0.1em',
      color: 'var(--success)',
      textTransform: 'uppercase' as const,
    }}
  >
    <span
      style={{
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        background: 'var(--success)',
        display: 'inline-block',
        animation: 'intel-pulse 1.4s ease-in-out infinite',
      }}
    />
    LIVE
  </span>
);

const StatCard = ({ label, value, icon, accent = 'var(--primary)' }: StatCardProps) => (
  <div
    style={{
      flex: 1,
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-4)',
      padding: 'var(--space-4)',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--glass-border)',
      borderRadius: 'var(--radius-md)',
      minWidth: 0,
    }}
  >
    <div
      style={{
        width: '40px',
        height: '40px',
        borderRadius: 'var(--radius-md)',
        background: `color-mix(in srgb, ${accent} 15%, transparent)`,
        border: `1px solid color-mix(in srgb, ${accent} 35%, transparent)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        color: accent,
      }}
    >
      {icon}
    </div>
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          lineHeight: 1,
          fontFamily: 'monospace',
          color: accent,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: '0.7rem',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginTop: '4px',
        }}
      >
        {label}
      </div>
    </div>
  </div>
);

// ─── Tab config ───────────────────────────────────────────────────────────────

const TABS: { id: IntelTab; label: string; icon: React.ReactNode }[] = [
  { id: 'telemetry',  label: 'Telemetry',        icon: <Activity size={14} /> },
  { id: 'reasoning',  label: 'Reasoning Traces',  icon: <Brain size={14} /> },
  { id: 'trajectory', label: 'Diagnostics',        icon: <GitBranch size={14} /> },
];

// ─── Section animation variants ──────────────────────────────────────────────

const sectionVariants = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -12, transition: { duration: 0.2, ease: 'easeIn' } },
} as any;

// ─── IntelligencePage ────────────────────────────────────────────────────────

export function IntelligencePage() {
  const { stats, agents, selectedAgent, selectAgent } = useDashboard();

  const activeNodes    = stats?.active_nodes    ?? 0;
  const aggregateAis   = stats?.aggregate_ais   ?? 0;
  const activeDisputes = stats?.active_disputes ?? 0;

  // Customization States: control visibility of different panels
  const [showTelemetry, setShowTelemetry] = useState(true);
  const [showRadar, setShowRadar] = useState(true);

  // Custom dynamic telemetry states
  const [isAddTelemetryOpen, setIsAddTelemetryOpen] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [customFields, setCustomFields] = useState<any[]>(() => {
    const saved = localStorage.getItem('integrity_custom_telemetry');
    return saved ? JSON.parse(saved) : [
      { id: 'drift', label: 'Semantic Drift', value: '0.8%', active: true },
      { id: 'memory', label: 'Enclave Memory', value: '412 MB', active: true }
    ];
  });

  useEffect(() => {
    localStorage.setItem('integrity_custom_telemetry', JSON.stringify(customFields));
  }, [customFields]);

  const toggleCustomField = (id: string) => {
    setCustomFields(prev => prev.map(f => f.id === id ? { ...f, active: !f.active } : f));
  };

  const handleAddTelemetry = () => {
    if (!newFieldName || !newFieldValue) return;
    const newId = 'custom_' + Math.random().toString(36).substring(2, 9);
    setCustomFields(prev => [...prev, { id: newId, label: newFieldName, value: newFieldValue, active: true }]);
    setNewFieldName('');
    setNewFieldValue('');
    setIsAddTelemetryOpen(false);
  };

  // Radar Data calculation for the selected agent
  const radarData = selectedAgent ? [
    { subject: 'Stability (1-E)', value: (selectedAgent.entropy_score || 0) / 10 },
    { subject: 'Grounding', value: (selectedAgent.grounding_score || 0) / 10 },
    { subject: 'Sacrifice', value: (selectedAgent.sacrifice_score || 0) / 10 },
    { subject: 'Identity Tier', value: (selectedAgent.verification_tier || 1) * 33.3 },
    { subject: 'Compliance', value: selectedAgent.compliance_score || 0 },
  ] : [];

  return (
    <>
      {/* Keyframe for the LIVE pulse dot */}
      <style>{`
        @keyframes intel-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-6)',
          padding: 'var(--space-6)',
          minHeight: '100%',
        }}
      >
        {/* ── Hero Bar ────────────────────────────────────────────── */}
        <Panel>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 'var(--space-4)',
            }}
          >
            {/* Left: title + subtitle */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: 'var(--radius-md)',
                    background: 'color-mix(in srgb, var(--primary) 18%, transparent)',
                    border: '1px solid color-mix(in srgb, var(--primary) 40%, transparent)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--primary)',
                  }}
                >
                  <Zap size={18} />
                </div>
                <h1
                  style={{
                    margin: 0,
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                    color: 'var(--text-primary)',
                  }}
                >
                  Intelligence Command
                </h1>
                <LiveBadge />
              </div>
              <p
                style={{
                  margin: 0,
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  paddingLeft: '48px',
                }}
              >
                Real-time telemetry, reasoning traces &amp; trajectory analysis
              </p>
            </div>

            {/* Right: system status */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.75rem',
                color: 'var(--success)',
              }}
            >
              <TrendingUp size={14} />
              Oracle Engine v9.0.2 — Nominal
            </div>
          </div>
        </Panel>

        {/* ── Intelligence Customization Console Toolbar ── */}
        <div 
          style={{ 
            background: 'var(--bg-card)', 
            border: '1px solid var(--glass-border)', 
            borderRadius: 'var(--radius-md)', 
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px'
          }}
        >
          {/* Left: Label + Quick Toggles */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderRight: '1px solid var(--glass-border)', paddingRight: '16px' }}>
              <Activity size={16} style={{ color: 'var(--primary)' }} />
              <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'white', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Filters</span>
            </div>
            
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {[
                { id: 'telemetry', label: 'Telemetry Stream', state: showTelemetry, set: setShowTelemetry },
                { id: 'radar', label: 'Radar Graphs', state: showRadar, set: setShowRadar }
              ].map(module => (
                <button
                  key={module.id}
                  onClick={() => module.set(!module.state)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${module.state ? 'var(--primary)' : 'var(--glass-border)'}`,
                    background: module.state ? 'var(--primary-dim)' : 'transparent',
                    color: module.state ? 'var(--primary)' : 'var(--text-muted)',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                >
                  {module.state ? '✓ ' : '+ '} {module.label}
                </button>
              ))}

              {/* Dynamic custom telemetry filters */}
              {customFields.map(field => (
                <button
                  key={field.id}
                  onClick={() => toggleCustomField(field.id)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${field.active ? 'var(--gold)' : 'var(--glass-border)'}`,
                    background: field.active ? 'rgba(212, 175, 55, 0.1)' : 'transparent',
                    color: field.active ? 'var(--gold)' : 'var(--text-muted)',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                >
                  {field.active ? '✓ ' : '+ '} {field.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button 
              className="btn btn-ghost" 
              onClick={() => setIsAddTelemetryOpen(true)}
              style={{ padding: '6px 12px', fontSize: '0.7rem', height: '28px', border: '1px dashed var(--glass-border)' }}
            >
              + Add Custom Telemetry
            </button>
          </div>
        </div>

        {/* ── Stat Strip ──────────────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            gap: 'var(--space-4)',
            flexWrap: 'wrap',
          }}
        >
          <StatCard
            label="Active Nodes"
            value={activeNodes}
            icon={<Activity size={18} />}
            accent="var(--primary)"
          />
          <StatCard
            label="Aggregate AIS"
            value={aggregateAis.toLocaleString()}
            icon={<Brain size={18} />}
            accent="var(--gold)"
          />
          <StatCard
            label="Active Disputes"
            value={activeDisputes}
            icon={<GitBranch size={18} />}
            accent={activeDisputes > 0 ? 'var(--warning, #f59e0b)' : 'var(--success)'}
          />

          {/* Render active custom telemetries as config cards */}
          {customFields.filter(f => f.active).map(f => (
            <StatCard
              key={f.id}
              label={f.label}
              value={f.value}
              icon={<Zap size={18} />}
              accent="var(--emerald)"
            />
          ))}
        </div>

        {/* ── Interactive Radar Section (Conditional) ───────────────── */}
        {showRadar && selectedAgent && (
          <Panel title={`${selectedAgent.alias} // Multi-Dimensional Integrity Radar`} icon={<Brain size={18} />}>
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)', alignItems: 'center' }}>
              {/* Left Column: Legend / Info */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                  This multi-dimensional radar chart displays the normalized performance indices of the focused agent. 
                  Reputation checks analyze alignment margins across stability (entropy control), human-in-the-loop validation (grounding), TEE checks, and economic commitments.
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Focused Agent Alias</span>
                    <span style={{ fontWeight: 600 }}>{selectedAgent.alias}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Cryptographic Address</span>
                    <span className="mono" style={{ fontSize: '0.7rem' }}>{selectedAgent.eth_address}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Agent Integrity Score (AIS)</span>
                    <span style={{ fontWeight: 700, color: 'var(--gold)' }}>{selectedAgent.current_ais} / 1000</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>TEE Protection Mode</span>
                    <span style={{ color: selectedAgent.tee_verified ? 'var(--success)' : 'var(--text-muted)' }}>
                      {selectedAgent.tee_verified ? `ACTIVE (${selectedAgent.tee_type || 'SGX'})` : 'INACTIVE'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Column: Dynamic Radar Chart */}
              <div style={{ display: 'flex', justifyContent: 'center', minWidth: 0, minHeight: 0, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--glass-border)', padding: 'var(--space-6)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ width: '100%', height: '240px', minWidth: 0, minHeight: 0, position: 'relative' }}>
                  <IntegrityRadar agent={selectedAgent} />
                </div>
              </div>
            </div>
          </Panel>
        )}

        {/* ── Section content (Stacked) ─────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', marginTop: 'var(--space-4)' }}>
          {showTelemetry && <TelemetryPanel />}
        </div>
      </div>

      {/* Dynamic Telemetry Modal */}
      {isAddTelemetryOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
          <div 
            onClick={() => setIsAddTelemetryOpen(false)} 
            style={{ position: 'absolute', inset: 0, background: 'var(--navy-deep)', opacity: 0.85, backdropFilter: 'blur(8px)' }} 
          />
          <div 
            style={{ 
              position: 'relative', 
              width: '100%', 
              maxWidth: '400px', 
              background: 'var(--bg-card)', 
              border: '1px solid var(--primary)', 
              borderRadius: 'var(--radius-lg)', 
              padding: '24px', 
              display: 'flex', 
              flexDirection: 'column', 
              gap: '16px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
            }}
          >
            <h3 style={{ margin: 0, color: 'white', fontSize: '1.1rem', fontWeight: 700 }}>Add Custom Telemetry</h3>
            
            <div className="form-group">
              <label className="form-label">Telemetry Label</label>
              <input 
                type="text" 
                className="input" 
                placeholder="e.g. Enclave Temperature" 
                value={newFieldName} 
                onChange={e => setNewFieldName(e.target.value)} 
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Metric Value / Output</label>
              <input 
                type="text" 
                className="input" 
                placeholder="e.g. 42.5°C or 99.8%" 
                value={newFieldValue} 
                onChange={e => setNewFieldValue(e.target.value)} 
              />
            </div>
            
            <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
              <button 
                className="btn btn-outline" 
                style={{ flex: 1 }}
                onClick={() => setIsAddTelemetryOpen(false)}
              >
                Cancel
              </button>
              <button 
                className="btn btn-primary" 
                style={{ flex: 1 }}
                onClick={handleAddTelemetry}
                disabled={!newFieldName || !newFieldValue}
              >
                Add Stream
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
