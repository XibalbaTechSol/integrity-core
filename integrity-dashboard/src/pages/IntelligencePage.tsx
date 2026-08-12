import { useState, useEffect } from 'react';
import { Activity, Brain, GitBranch, Zap, CheckCircle2, Sigma, Shield, Clock } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { TelemetryPanel } from '../components/tabs/TelemetryPanel';
import { IntegrityRadar } from '../components/shared/IntegrityRadar';
import { useDashboard } from '../context/DashboardContext';
import 'katex/dist/katex.min.css';
import { BlockMath, InlineMath } from 'react-katex';

// ─── Sub-components ──────────────────────────────────────────────────────────

const FormulaCard = ({ title, description, formula, icon, accent = 'var(--primary)' }: any) => (
  <div
    style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-4)',
      padding: 'var(--space-6)',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--glass-border)',
      borderRadius: 'var(--radius-md)',
      minWidth: '300px',
      transition: 'transform 0.2s, box-shadow 0.2s',
      cursor: 'default',
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.transform = 'translateY(-2px)';
      e.currentTarget.style.boxShadow = '0 10px 30px rgba(0,0,0,0.2)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.transform = 'none';
      e.currentTarget.style.boxShadow = 'none';
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <div
        style={{
          width: '36px',
          height: '36px',
          borderRadius: 'var(--radius-md)',
          background: `color-mix(in srgb, ${accent} 15%, transparent)`,
          border: `1px solid color-mix(in srgb, ${accent} 35%, transparent)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: accent,
        }}
      >
        {icon}
      </div>
      <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{title}</h3>
    </div>
    
    <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>
      {description}
    </div>

    <div style={{ 
      marginTop: 'auto', 
      padding: '12px', 
      background: 'var(--bg-card)', 
      borderRadius: 'var(--radius-sm)',
      border: '1px dashed var(--glass-border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden'
    }}>
      <BlockMath math={formula} />
    </div>
  </div>
);

// ─── IntelligencePage ────────────────────────────────────────────────────────

export function IntelligencePage() {
  const { stats, selectedAgent } = useDashboard() as any;

  // Customization States: control visibility of different panels
  const [showTelemetry, setShowTelemetry] = useState(true);
  const [showRadar, setShowRadar] = useState(true);

  // Custom dynamic telemetry states
  const [isAddTelemetryOpen, setIsAddTelemetryOpen] = useState(false);
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  
  const [customFields, setCustomFields] = useState<any[]>(() => {
    const saved = localStorage.getItem('integrity_custom_telemetry');
    if (!saved) return [];
    try {
      return JSON.parse(saved).filter((f: any) => f?.id !== 'drift' && f?.id !== 'memory');
    } catch {
      return [];
    }
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

  return (
    <>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-6)',
          padding: 'var(--space-6)',
          minHeight: '100%',
        }}
      >

        <div style={{ marginBottom: '1rem' }}>
          <h1 style={{ margin: '0 0 8px 0', fontSize: '2rem' }}>Intelligence & Alignment</h1>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
            Transparent oversight into mathematical formulas driving the Agent Integrity Score (AIS) and multi-dimensional behavior tracking.
          </p>
        </div>

        {/* ── Mathematical Definitions Section ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-6)' }}>
          <FormulaCard 
            title="Stability (Entropy Control)"
            description={<span>Measures the determinism and bounded variance of agent outputs using Shannon Entropy <InlineMath math="E" />.</span>}
            formula="S(E) = 1 - \left( -\sum_{x \in X} P(x) \log P(x) \right)"
            icon={<Sigma size={20} />}
            accent="#2196f3"
          />
          <FormulaCard 
            title="Grounding (Human-in-the-Loop)"
            description={<span>Time-decayed confidence scoring based on human validation <InlineMath math="v_i" /> and oracle confidence <InlineMath math="c_i" />.</span>}
            formula="G(v, c) = \frac{1}{N} \sum_{i=1}^{N} (v_i \cdot c_i) \cdot w(t_i)"
            icon={<CheckCircle2 size={20} />}
            accent="#4caf50"
          />
          <FormulaCard 
            title="Sacrifice (Economic Commitment)"
            description={<span>Time-weighted integral of Staked ITK collateral <InlineMath math="V(\tau)" /> over lock duration.</span>}
            formula="K(V, t) = \int_{t_0}^{t_f} V(\tau) \cdot e^{-\lambda(t_f - \tau)} d\tau"
            icon={<Clock size={20} />}
            accent="#f59e0b"
          />
          <FormulaCard 
            title="Overall Agent Integrity Score"
            description={<span>The final AIS aggregates all sub-metrics <InlineMath math="m \in M" /> with weights <InlineMath math="w_m" /> and applies a ZK/TEE proof multiplier <InlineMath math="\gamma_{\text{TEE}}" />.</span>}
            formula="\text{AIS} = \left( \sum_{m \in M} w_m \cdot \phi_m(x) \right) \times \gamma_{\text{TEE}}"
            icon={<Shield size={20} />}
            accent="var(--theme-accent)"
          />
        </div>

        {/* ── Interactive Radar Section (Conditional) ───────────────── */}
        {showRadar && selectedAgent && (
          <Panel title={`${selectedAgent.name || selectedAgent.alias || 'Agent'} // Multi-Dimensional Integrity Radar`} icon={<Brain size={18} />}>
            <div className="grid-cols-2" style={{ gap: 'var(--space-6)', alignItems: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                  This multi-dimensional radar chart displays the normalized performance indices of the focused agent. 
                  Reputation checks analyze alignment margins across stability (entropy control), human-in-the-loop validation (grounding), TEE checks, and economic commitments.
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Focused Agent Alias</span>
                    <span style={{ fontWeight: 600 }}>{selectedAgent.name || selectedAgent.alias || 'Agent'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Cryptographic Address</span>
                    <span className="mono" style={{ fontSize: '0.7rem' }}>{selectedAgent.eth_address}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Agent Integrity Score (AIS)</span>
                    <span style={{ fontWeight: 700, color: 'var(--theme-accent)' }}>{selectedAgent?.current_ais != null ? `${selectedAgent.current_ais.toFixed(1)} / 1000` : 'No reading yet'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>ZK Proof Boost</span>
                    <span style={{ color: selectedAgent.tee_verified ? 'var(--success)' : 'var(--text-muted)' }}>
                      {selectedAgent.tee_verified ? 'VERIFIED (bb)' : 'NOT BOOSTED'}
                    </span>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', minWidth: 0, minHeight: 0, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--glass-border)', padding: 'var(--space-6)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ width: '100%', height: '240px', minWidth: 0, minHeight: 0, position: 'relative' }}>
                  <IntegrityRadar agent={selectedAgent} />
                </div>
              </div>
            </div>
          </Panel>
        )}

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

              {customFields.map(field => (
                <button
                  key={field.id}
                  onClick={() => toggleCustomField(field.id)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${field.active ? 'var(--theme-accent)' : 'var(--glass-border)'}`,
                    background: field.active ? 'rgba(212, 175, 55, 0.1)' : 'transparent',
                    color: field.active ? 'var(--theme-accent)' : 'var(--text-muted)',
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
