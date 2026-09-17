import { useMemo, useState } from 'react';
import { Sliders, Zap, RotateCcw } from 'lucide-react';
import {
  AIS_PROFILE,
  AIS_WEIGHTS,
  MAX_COMPONENT_SCORE,
  SHADOW_FLOORS,
  TIER_CEILINGS,
  ZK_BOOST_FACTOR,
  complianceScore,
  entropyScore,
  groundingScore,
  sacrificeProxyScore,
} from '../../services/aisProfile';

// A hypothetical explanatory model matching the accepted profile in
// integrity-oracle/scoring-core. It is not live evidence or an authoritative
// score; it lets a viewer feel out *why* the score moves the way it
// does (the geometric mean's zero-annihilation property especially) without
// needing a live agent with matching telemetry. If scoring-core's formula ever
// changes, this must change with it -- see that crate's own top docstring.
type Preset = { label: string; variance: number; hgi: number; hours: number; penalty: number; zk: boolean };
const PRESETS: Preset[] = [
  { label: 'Perfect agent', variance: 0, hgi: 1, hours: 1000, penalty: 0, zk: true },
  { label: 'Typical, unboosted', variance: 0.3, hgi: 0.7, hours: 250, penalty: 0.05, zk: false },
  { label: 'Never reports sacrifice', variance: 0.1, hgi: 0.95, hours: 0, penalty: 0, zk: false },
  { label: 'Erratic + non-compliant', variance: 1.8, hgi: 0.4, hours: 100, penalty: 0.6, zk: false },
];

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem' }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontWeight: 700, color }}>{value.toFixed(1)}</span>
      </div>
      <div style={{ height: '8px', borderRadius: '4px', background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${(value / MAX_COMPONENT_SCORE) * 100}%`, background: color, transition: 'width 0.15s ease' }} />
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; format: (v: number) => string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span className="mono" style={{ color: 'var(--theme-accent)', fontWeight: 700 }}>{format(value)}</span>
      </div>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--theme-accent)' }}
      />
    </div>
  );
}

export function AisSimulator() {
  const [variance, setVariance] = useState(0.3);
  const [hgi, setHgi] = useState(0.7);
  const [hours, setHours] = useState(250);
  const [penalty, setPenalty] = useState(0.05);
  const [zk, setZk] = useState(false);
  const [tier, setTier] = useState(3);

  const breakdown = useMemo(() => {
    const s_entropy = entropyScore(variance);
    const s_grounding = groundingScore(hgi);
    const s_sacrifice = sacrificeProxyScore(hours);
    const s_compliance = complianceScore(penalty);
    const weighted =
      Math.pow(s_entropy, AIS_WEIGHTS.entropy) *
      Math.pow(s_grounding, AIS_WEIGHTS.grounding) *
      Math.pow(s_sacrifice, AIS_WEIGHTS.sacrifice) *
      Math.pow(s_compliance, AIS_WEIGHTS.compliance);
    const zk_boost = zk ? ZK_BOOST_FACTOR : 1.0;
    const raw = weighted * zk_boost;
    const ceiling = TIER_CEILINGS[tier];
    const ais = tier < 3 ? Math.min(raw, ceiling) : raw;
    const shadowGate = s_entropy >= SHADOW_FLOORS.entropy && s_grounding >= SHADOW_FLOORS.grounding && s_compliance >= SHADOW_FLOORS.compliance;
    return { s_entropy, s_grounding, s_sacrifice, s_compliance, weighted, zk_boost, raw, ceiling, ais, shadowGate, tierCapped: tier < 3 && raw > ceiling };
  }, [variance, hgi, hours, penalty, zk, tier]);

  const applyPreset = (p: Preset) => {
    setVariance(p.variance);
    setHgi(p.hgi);
    setHours(p.hours);
    setPenalty(p.penalty);
    setZk(p.zk);
  };

  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-md)',
      padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Sliders size={18} color="var(--theme-accent)" />
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>AIS Mechanics Explorer</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              Hypothetical explorer for {AIS_PROFILE}; not live evidence or an authorization decision.
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p)}
              className="secondary-button btn-xs"
              style={{ fontSize: '0.65rem' }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid-cols-2" style={{ gap: 'var(--space-6)' }}>
        {/* Inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <Slider label="Performance variance" value={variance} min={0} max={3} step={0.05} onChange={setVariance} format={(v) => v.toFixed(2)} />
          <Slider label="Human Grounding Index (HGI)" value={hgi} min={0} max={1} step={0.01} onChange={setHgi} format={(v) => v.toFixed(2)} />
          <Slider label="Verified compute-hours proxy" value={hours} min={0} max={1500} step={10} onChange={setHours} format={(v) => v.toFixed(0)} />
          <Slider label="Policy-flagged action ratio" value={penalty} min={0} max={1} step={0.01} onChange={setPenalty} format={(v) => v.toFixed(2)} />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', cursor: 'pointer' }}>
              <input aria-label="Real ZK proof verified this period" type="checkbox" checked={zk} onChange={(e) => setZk(e.target.checked)} />
              <Zap size={14} color={zk ? '#f59e0b' : 'var(--text-muted)'} />
              Real ZK proof verified this period (x1.15)
            </label>
            <button onClick={() => applyPreset(PRESETS[1])} className="secondary-button btn-xs" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <RotateCcw size={12} /> Reset
            </button>
          </div>

          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>Verification tier (ceilings the final score)</div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['0 (Dev key) -> 300', '1 (Sovereign) -> 600', '2 (Linked) -> 850', '3 (Institutional) -> 1000'].map((label, i) => (
                <button
                  key={i}
                  onClick={() => setTier(i)}
                  style={{
                    flex: 1, padding: '6px 4px', fontSize: '0.6rem', borderRadius: '6px', cursor: 'pointer',
                    border: `1px solid ${tier === i ? 'var(--theme-accent)' : 'var(--glass-border)'}`,
                    background: tier === i ? 'var(--theme-accent-muted)' : 'transparent',
                    color: tier === i ? 'var(--theme-accent)' : 'var(--text-muted)',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Outputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <Bar label="S_entropy (Stability)" value={breakdown.s_entropy} color="#2196f3" />
          <Bar label="S_grounding" value={breakdown.s_grounding} color="#4caf50" />
          <Bar label="S_sacrifice" value={breakdown.s_sacrifice} color="#f59e0b" />
          <Bar label="S_compliance" value={breakdown.s_compliance} color="#c4b5fd" />

          <div style={{
            marginTop: '8px', padding: '16px', borderRadius: 'var(--radius-md)',
            background: 'rgba(0,0,0,0.25)', border: '1px solid var(--glass-border)',
            display: 'flex', flexDirection: 'column', gap: '6px',
          }}>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Hypothetical AIS
            </div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: breakdown.ais < 1 ? 'var(--danger)' : 'var(--theme-accent)' }}>
              {breakdown.ais.toFixed(1)} <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 500 }}>/ 1000</span>
            </div>
            <div className="mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
              base {breakdown.weighted.toFixed(1)} · post-boost {breakdown.raw.toFixed(1)} · final {breakdown.ais.toFixed(1)} · profile {AIS_PROFILE}
              {breakdown.tierCapped && <span style={{ color: '#f59e0b' }}> -- capped at tier ceiling {breakdown.ceiling}</span>}
            </div>
            <div style={{ fontSize: '0.68rem', color: breakdown.shadowGate ? 'var(--text-muted)' : '#f59e0b' }}>
              Shadow floor diagnostic: {breakdown.shadowGate ? 'would pass' : 'would fail'}; proposed gate is not enforced.
            </div>
            {breakdown.ais < 1 && (
              <div style={{ marginTop: '6px', fontSize: '0.7rem', color: 'var(--danger)', lineHeight: 1.4 }}>
                One of the four components sits at or near zero. Under a geometric mean, x^w = 0 whenever x = 0 --
                the other three axes cannot compensate, no matter how strong they are.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
