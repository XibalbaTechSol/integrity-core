import { useState, useEffect } from 'react';
import { Activity, Brain, Zap, CheckCircle2, Sigma, Shield, Clock } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { TelemetryPanel } from '../components/tabs/TelemetryPanel';
import { IntegrityRadar } from '../components/shared/IntegrityRadar';
import { AisSimulator } from '../components/shared/AisSimulator';
import { useDashboard } from '../context/DashboardContext';
import { useIsMobile } from '../utils/useIsMobile';
import 'katex/dist/katex.min.css';
import { BlockMath, InlineMath } from 'react-katex';

// ─── Sub-components ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.1em',
      display: 'flex', alignItems: 'center', gap: '10px',
    }}>
      {children}
      <span style={{ flex: 1, height: '1px', background: 'var(--glass-border)' }} />
    </div>
  );
}

const FormulaCard = ({ title, description, formula, icon, accent = 'var(--primary)', span = false }: any) => (
  <div
    style={{
      gridColumn: span ? '1 / -1' : undefined,
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-4)',
      padding: 'var(--space-6)',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--glass-border)',
      borderRadius: 'var(--radius-md)',
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
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3 }}>{title}</h3>
    </div>

    <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>
      {description}
    </div>

    <div
      className="thin-scrollbar-x"
      style={{
        marginTop: 'auto',
        padding: '14px 16px',
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-sm)',
        border: '1px dashed var(--glass-border)',
        display: 'flex',
        alignItems: 'center',
        // overflow: hidden clipped BOTH edges of formulas wider than the card (centered
        // content clips symmetrically) — "AIS = (...)" rendered as "[S = (...)" with the
        // leading "A" and "I" cut away. justify-content: flex-start keeps the formula's
        // start flush left and fully visible; only genuine excess width scrolls, and the
        // slim .thin-scrollbar-x styling keeps that scroll affordance from reading as a
        // stray, unfinished widget in a small card.
        justifyContent: 'flex-start',
        overflowX: 'auto',
        overflowY: 'hidden',
      }}
    >
      <BlockMath math={formula} />
    </div>
  </div>
);

// ─── IntelligencePage ────────────────────────────────────────────────────────

export function IntelligencePage() {
  const { stats, selectedAgent } = useDashboard() as any;
  const isMobile = useIsMobile();

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

        {/* ── Mathematical Definitions Section ──
            Formulas verbatim from integrity-oracle/scoring-core/src/lib.rs -- the ONLY
            place AIS is computed anywhere in the protocol (see that file's own top
            docstring). Every consumer, including this page, reads the oracle's
            GET /v1/agent/{id}/ais rather than re-deriving this math independently.
            A single grid (not a 4-card grid plus a separately-styled sibling) so the
            "Overall AIS" formula reads as the section's conclusion, not a bolted-on
            afterthought -- it spans both columns via `span`. Explicit 2 columns (not
            auto-fit) so 4 cards never orphan a lone card on its own half-empty row. */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <SectionLabel>AIS Component Formulas</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)', gap: 'var(--space-6)' }}>
            <FormulaCard
              title="Stability (Entropy)"
              description={<span>Gaussian-style decay over reported task-performance variance <InlineMath math="v" />. Small variance barely moves the score; unbounded variance saturates toward 0.</span>}
              formula="S_{\text{entropy}}(v) = 1000 \cdot e^{-1.5 v^2}"
              icon={<Sigma size={20} />}
              accent="#2196f3"
            />
            <FormulaCard
              title="Grounding (Human Oversight)"
              description={<span>Linear in the Human Grounding Index <InlineMath math="h \in [0,1]" /> -- the fraction of the agent's actions in the period checked against real human-in-the-loop feedback.</span>}
              formula="S_{\text{grounding}}(h) = 1000 \cdot \text{clamp}(h, 0, 1)"
              icon={<CheckCircle2 size={20} />}
              accent="#4caf50"
            />
            <FormulaCard
              title="Sacrifice (Compute Commitment)"
              description={<span>Log-scale over the oracle's re-derived verified compute-hours proxy <InlineMath math="g" />, saturating at 1000 hours so a whale can't simply out-spend a trust signal.</span>}
              formula="S_{\text{sacrifice}}(g) = 1000 \cdot \min\!\left(\frac{\log_{10}(g+1)}{3}, 1\right)"
              icon={<Clock size={20} />}
              accent="#f59e0b"
            />
            <FormulaCard
              title="Compliance"
              description={<span>Linear inverse of the policy-flagged action ratio <InlineMath math="p \in [0,1]" /> from the BCC/OPA pipeline -- 0 flags scores 1000, every action flagged scores 0.</span>}
              formula="S_{\text{compliance}}(p) = 1000 \cdot (1 - p)"
              icon={<Zap size={20} />}
              accent="#8b5cf6"
            />
            <FormulaCard
              span
              title="Overall Agent Integrity Score -- a weighted GEOMETRIC mean, not arithmetic"
              description={
                <span>
                  Default weights <InlineMath math="w_E{=}0.30, w_G{=}0.30, w_S{=}0.20, w_C{=}0.20" /> (sum to 1.0).{' '}
                  <InlineMath math="\gamma_{\text{ZK}} = 1.15" /> only when a real Barretenberg proof verified this
                  period, else <InlineMath math="1.0" />. Because it's a product of powers, not a sum, any single
                  zero component raises the whole product to zero -- a strong entropy/grounding/compliance score
                  cannot compensate for sacrifice never being reported. That's the exact reason the network's own
                  dogfooding agent read AIS 0.0 for weeks (see scoring-core's own regression test,{' '}
                  <code style={{ fontSize: '0.7rem' }}>any_single_zero_component_annihilates_ais</code>).
                </span>
              }
              formula="\text{AIS} = S_{\text{entropy}}^{\,w_E} \cdot S_{\text{grounding}}^{\,w_G} \cdot S_{\text{sacrifice}}^{\,w_S} \cdot S_{\text{compliance}}^{\,w_C} \cdot \gamma_{\text{ZK}}"
              icon={<Shield size={20} />}
              accent="var(--theme-accent)"
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <SectionLabel>Interactive Explorer</SectionLabel>
          <AisSimulator />
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
