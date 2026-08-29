import { useState, useEffect } from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts';
import type { Agent } from '../../context/DashboardContext';
import { oracle, AisComponents } from '../../services/oracle';

interface IntegrityRadarProps {
  agent: Agent;
}

const CustomTooltip = ({ active, payload, mode }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    let explanation = '';
    let formula = '';
    
    if (mode === 'integrity') {
      if (data.subject.startsWith('Stability')) {
        formula = 'Stability = (1 - Entropy) * 100';
        explanation = 'Measures prediction consistency and low system volatility. Lower entropy yields higher stability.';
      } else if (data.subject === 'Grounding') {
        formula = 'Grounding = oracle AIS component G';
        explanation = 'Measures alignment with factuality, correctness, and context verification.';
      } else if (data.subject === 'Sacrifice') {
        formula = 'Sacrifice = oracle AIS component S';
        explanation = 'Represents economic collateral staked on the platform to guarantee integrity.';
      } else if (data.subject === 'Identity') {
        formula = 'Identity = Verification Tier * 33.3';
        explanation = 'Reflects identity verification and reputation grade (Tiers 1-3).';
      } else if (data.subject === 'Compliance') {
        formula = 'Compliance = oracle AIS component C';
        explanation = 'Indicates regulatory compliance, penalized by accumulated infractions.';
      }
    } else {
      if (data.subject === 'Behavioral Drift') {
        formula = 'Drift Risk = Entropy * 100';
        explanation = 'Represents operational volatility. Higher entropy indicates fluctuating behavior or potential runaway states.';
      } else if (data.subject === 'Hallucination Risk') {
        formula = 'Hallucination Risk = 100 - Grounding';
        explanation = 'Probability of factuality drift or incorrect instruction following.';
      } else if (data.subject === 'Sybil Exposure') {
        formula = 'Sybil Risk = 100 - Sacrifice';
        explanation = 'Economic replicability exposure. Lower stake size allows identities to be cloned at low cost.';
      }
    }

    return (
      <div style={{
        background: '#0c0c14',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        padding: '12px',
        borderRadius: '8px',
        maxWidth: '220px',
        fontSize: '11px',
        color: 'rgba(255, 255, 255, 0.9)',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{ fontWeight: 600, color: mode === 'integrity' ? 'var(--primary)' : '#ef4444', marginBottom: '4px' }}>{data.subject}</div>
        <div style={{ fontWeight: 700, fontSize: '13px', marginBottom: '6px' }}>Score: {data.value}%</div>
        <div style={{ fontFamily: 'monospace', color: '#f59e0b', marginBottom: '6px', fontSize: '10px' }}>{formula}</div>
        <div style={{ color: 'rgba(255, 255, 255, 0.6)', lineHeight: '1.4' }}>{explanation}</div>
      </div>
    );
  }
  return null;
};

export function IntegrityRadar({ agent }: IntegrityRadarProps) {
  const [mode, setMode] = useState<'integrity' | 'risk'>('integrity');
  const [components, setComponents] = useState<AisComponents | null>(null);

  useEffect(() => {
    let active = true;
    oracle.getAis(agent.eth_address)
      .then(r => { if (active) setComponents(r.components); })
      .catch(() => { if (active) setComponents(null); });
    return () => { active = false; };
  }, [agent.eth_address]);

  // Real AIS sub-scores from the oracle (already 0-1) scaled to 0-100 for the radar.
  // "Sacrifice" doubles as economic stake exposure — same axis the scoring formula uses.
  const entropy = components ? Math.round(components.entropy * 100) : 0;
  const grounding = components ? Math.round(components.grounding * 100) : 0;
  const sacrifice = components ? Math.round(components.sacrifice * 100) : 0;
  const compliance = components ? Math.round(components.compliance * 100) : 0;
  const identity = Math.round((agent.verification_tier ?? 0) * 33.3);

  const integrityData = [
    { subject: 'Stability (Entropy)', value: entropy },
    { subject: 'Grounding', value: grounding },
    { subject: 'Sacrifice', value: sacrifice },
    { subject: 'Identity', value: identity },
    { subject: 'Compliance', value: compliance },
  ];

  const riskData = [
    { subject: 'Behavioral Drift', value: 100 - entropy },
    { subject: 'Hallucination Risk', value: 100 - grounding },
    { subject: 'Sybil Exposure', value: 100 - sacrifice },
  ];

  const data = mode === 'integrity' ? integrityData : riskData;
  const activeColor = mode === 'integrity' ? 'var(--primary)' : '#ef4444';

  if (!components) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>No AIS reading yet for this agent.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%' }}>
      {/* Mode Selector Toggle */}
      <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginBottom: '4px' }}>
        <button
          onClick={() => setMode('integrity')}
          style={{
            padding: '4px 12px',
            borderRadius: '6px',
            border: `1px solid ${mode === 'integrity' ? 'var(--primary)' : 'rgba(255,255,255,0.05)'}`,
            background: mode === 'integrity' ? 'var(--primary-dim)' : 'transparent',
            color: mode === 'integrity' ? 'var(--primary)' : 'var(--text-muted)',
            fontSize: '0.65rem',
            fontWeight: 700,
            cursor: 'pointer',
            transition: 'all 0.15s'
          }}
        >
          Integrity Vectors
        </button>
        <button
          onClick={() => setMode('risk')}
          style={{
            padding: '4px 12px',
            borderRadius: '6px',
            border: `1px solid ${mode === 'risk' ? '#ef4444' : 'rgba(255,255,255,0.05)'}`,
            background: mode === 'risk' ? 'rgba(239,68,68,0.1)' : 'transparent',
            color: mode === 'risk' ? '#ef4444' : 'var(--text-muted)',
            fontSize: '0.65rem',
            fontWeight: 700,
            cursor: 'pointer',
            transition: 'all 0.15s'
          }}
        >
          Tri-Metric Risk Scores
        </button>
      </div>

      <div style={{ width: '100%', height: '240px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="var(--glass-border)" />
            <PolarAngleAxis 
              dataKey="subject" 
              tick={{ fill: 'var(--text-muted)', fontSize: 10, fontWeight: 500 }}
            />
            <Tooltip content={<CustomTooltip mode={mode} />} />
            <Radar
              name={mode === 'integrity' ? 'AIS Metrics' : 'Risk Metrics'}
              dataKey="value"
              stroke={activeColor}
              fill={activeColor}
              fillOpacity={0.3}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Description Listings explaining the mathematical components */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '16px',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        borderRadius: '12px',
        fontSize: '0.75rem',
      }}>
        <div style={{ fontWeight: 700, color: 'white', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {mode === 'integrity' ? 'Mathematical Axis Calculations' : 'Tri-Metric Risk Calculations'}
        </div>
        {mode === 'integrity' ? (
          [
            { name: 'Stability', formula: 'Stability = (1 - Entropy) * 100', desc: 'Consistency metric derived from performance entropy (lower entropy increases stability).' },
            { name: 'Grounding', formula: 'Grounding = Grounding Score / 10', desc: 'Normalized alignment with factuality and context verification indexes.' },
            { name: 'Sacrifice', formula: 'Sacrifice = Min(100, Staked ITK / 50)', desc: 'Economic collateral stake (capped at 100%) serving as "skin in the game".' },
            { name: 'Identity', formula: 'Identity = Verification Tier * 33.3', desc: 'Scaled value based on reputation verification (Tiers 1 to 3).' },
            { name: 'Compliance', formula: 'Compliance = (1.0 - Penalty Points) * 100', desc: 'Regulatory and behavioral compliance rating, adjusted downwards for infractions.' }
          ].map((axis) => (
            <div key={axis.name} style={{ display: 'flex', flexDirection: 'column', gap: '4px', borderBottom: '1px solid rgba(255, 255, 255, 0.03)', paddingBottom: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{axis.name}</span>
                <code style={{ fontSize: '0.65rem', color: '#f59e0b', background: 'rgba(0, 0, 0, 0.2)', padding: '2px 6px', borderRadius: '4px' }}>
                  {axis.formula}
                </code>
              </div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', lineHeight: 1.4 }}>{axis.desc}</span>
            </div>
          ))
        ) : (
          [
            { name: 'Behavioral Drift', formula: 'Drift Risk = Entropy * 100', desc: 'Volatility risk. Higher drift signals structural inconsistency or high error rate.' },
            { name: 'Hallucination Risk', formula: 'Hallucination Risk = 100 - Grounding', desc: 'Fidelity risk. Indicates tendency to generate ungrounded, non-compliant outputs.' },
            { name: 'Sybil Exposure', formula: 'Sybil Exposure = 100 - Sacrifice', desc: 'Security replicability risk. Low economic stake indicates identity is cheaply replaceable.' }
          ].map((axis) => (
            <div key={axis.name} style={{ display: 'flex', flexDirection: 'column', gap: '4px', borderBottom: '1px solid rgba(255, 255, 255, 0.03)', paddingBottom: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: '#ef4444' }}>{axis.name}</span>
                <code style={{ fontSize: '0.65rem', color: '#f59e0b', background: 'rgba(0, 0, 0, 0.2)', padding: '2px 6px', borderRadius: '4px' }}>
                  {axis.formula}
                </code>
              </div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', lineHeight: 1.4 }}>{axis.desc}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
