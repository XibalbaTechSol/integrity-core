import { useMemo, useState } from 'react';
import { Sliders, Zap, RotateCcw } from 'lucide-react';

// A live, client-side reimplementation of integrity-oracle/scoring-core's exact
// AisEngine::score() -- same constants, same formulas, same order of operations.
// This is not fabricated demo data: it's the real algorithm run against
// hypothetical inputs, so a viewer can feel out *why* the score moves the way it
// does (the geometric mean's zero-annihilation property especially) without
// needing a live agent with matching telemetry. If scoring-core's formula ever
// changes, this must change with it -- see that crate's own top docstring.
const MAX = 1000;
const WEIGHTS = { entropy: 0.3, grounding: 0.3, sacrifice: 0.2, compliance: 0.2 };
const ZK_BOOST = 1.15;
const TIER_CEILING = [300, 600, 850, 1000];

function sEntropy(variance: number) {
  const v = Math.max(variance, 0);
  return Math.min(Math.max(Math.exp(-1.5 * v * v) * MAX, 0), MAX);
}
function sGrounding(hgi: number) {
  return Math.min(Math.max(hgi, 0), 1) * MAX;
}
function sSacrifice(hours: number) {
  const h = Math.max(hours, 0);
  return Math.min((Math.log10(h + 1) / 3), 1) * MAX;
}
function sCompliance(penaltyRatio: number) {
  return (1 - Math.min(Math.max(penaltyRatio, 0), 1)) * MAX;
}

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
        <div style={{ height: '100%', width: `${(value / MAX) * 100}%`, background: color, transition: 'width 0.15s ease' }} />
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
    const s_entropy = sEntropy(variance);
    const s_grounding = sGrounding(hgi);
    const s_sacrifice = sSacrifice(hours);
    const s_compliance = sCompliance(penalty);
    const weighted =
      Math.pow(s_entropy, WEIGHTS.entropy) *
      Math.pow(s_grounding, WEIGHTS.grounding) *
      Math.pow(s_sacrifice, WEIGHTS.sacrifice) *
      Math.pow(s_compliance, WEIGHTS.compliance);
    const zk_boost = zk ? ZK_BOOST : 1.0;
    const raw = weighted * zk_boost;
    const ceiling = TIER_CEILING[tier];
    const ais = tier < 3 ? Math.min(raw, ceiling) : raw;
    return { s_entropy, s_grounding, s_sacrifice, s_compliance, weighted, zk_boost, raw, ceiling, ais, tierCapped: tier < 3 && raw > ceiling };
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
              Runs the real oracle formula client-side against hypothetical inputs -- not a live agent reading.
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p)}
              className="btn btn-outline btn-xs"
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
              <input type="checkbox" checked={zk} onChange={(e) => setZk(e.target.checked)} />
              <Zap size={14} color={zk ? '#f59e0b' : 'var(--text-muted)'} />
              Real ZK proof verified this period (x1.15)
            </label>
            <button onClick={() => applyPreset(PRESETS[1])} className="btn btn-ghost btn-xs" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
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
          <Bar label="S_compliance" value={breakdown.s_compliance} color="#8b5cf6" />

          <div style={{
            marginTop: '8px', padding: '16px', borderRadius: 'var(--radius-md)',
            background: 'rgba(0,0,0,0.25)', border: '1px solid var(--glass-border)',
            display: 'flex', flexDirection: 'column', gap: '6px',
          }}>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Resulting AIS
            </div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: breakdown.ais < 1 ? 'var(--danger)' : 'var(--theme-accent)' }}>
              {breakdown.ais.toFixed(1)} <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 500 }}>/ 1000</span>
            </div>
            <div className="mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
              {breakdown.s_entropy.toFixed(0)}^0.3 x {breakdown.s_grounding.toFixed(0)}^0.3 x {breakdown.s_sacrifice.toFixed(0)}^0.2 x {breakdown.s_compliance.toFixed(0)}^0.2 x {breakdown.zk_boost.toFixed(2)} = {breakdown.raw.toFixed(1)}
              {breakdown.tierCapped && <span style={{ color: '#f59e0b' }}> -- capped at tier ceiling {breakdown.ceiling}</span>}
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
