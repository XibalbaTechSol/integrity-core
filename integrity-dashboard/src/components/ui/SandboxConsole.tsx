import React, { useState, useEffect } from 'react';
import { Cpu, Zap, Code } from 'lucide-react';

export const SandboxConsole = () => {
    const [performanceVariance, setPerformanceVariance] = useState(0.1);
    const [hgiRaw, setHgiRaw] = useState(0.8);
    const [avgPartnerAIS, setAvgPartnerAIS] = useState(700);
    const [gpuHours, setGpuHours] = useState(100);
    const [stakedRatio, setStakedRatio] = useState(0.5);
    const [agentAge, setAgentAge] = useState(30);
    const [volume, setVolume] = useState(10000);
    const [tier, setTier] = useState(1);
    
    const [results, setResults] = useState<any>(null);

    const calculateScores = () => {
        const MAX_SCORE = 1000;
        
        const entropyScore = Math.round(Math.exp(-1.5 * Math.pow(performanceVariance, 2)) * MAX_SCORE);
        const stabilityDrag = entropyScore / MAX_SCORE;

        const groundingScore = Math.round(hgiRaw * MAX_SCORE);
        const groundingBoost = 1.0 + (hgiRaw * 0.2);

        const trustflowIdx = Math.min(1.0, avgPartnerAIS / 1000.0);
        const auditIdx = 0.95; 
        const sacrificeIdx = Math.min(1.0, Math.log10(gpuHours + 1) / 3.0);
        const ageIdx = Math.min(1.0, Math.log10(agentAge + 1) / 2.56);
        const stakingAgeIdx = (0.5 * stakedRatio) + (0.5 * ageIdx);
        const volumeIdx = Math.min(1.0, Math.log10(volume + 1) / 6.0);

        const baseIntegrity = (
            (0.25 * trustflowIdx) +   
            (0.25 * auditIdx) +      
            (0.20 * sacrificeIdx) +  
            (0.15 * stakingAgeIdx) + 
            (0.15 * volumeIdx)       
        );

        let finalAis = baseIntegrity * stabilityDrag * groundingBoost * MAX_SCORE;
        
        const ceiling = tier === 1 ? 600 : tier === 2 ? 850 : 1000;
        finalAis = Math.min(finalAis, ceiling);

        setResults({
            entropy: entropyScore,
            grounding: groundingScore,
            ais: Math.round(finalAis),
            drag: stabilityDrag.toFixed(3),
            boost: groundingBoost.toFixed(3),
            base: baseIntegrity.toFixed(3),
            ceiling
        });
    };

    useEffect(() => {
        calculateScores();
    }, [performanceVariance, hgiRaw, avgPartnerAIS, gpuHours, stakedRatio, agentAge, volume, tier]);

    return (
        <div className="card" style={{ width: '100%', minWidth: 0, boxSizing: 'border-box', padding: 'clamp(1rem, 3vw, 2rem)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '2rem' }}>
                <Code color="var(--text-secondary)" size={24} />
                <h2 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>Protocol Sandbox</h2>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                    <span style={{ padding: '0.25rem 0.75rem', background: 'var(--text-primary)', color: 'var(--bg-color)', borderRadius: '16px', fontSize: '0.75rem', fontWeight: 700 }}>v8.3 TRI-METRIC</span>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(280px, 100%), 1fr))', gap: '2rem', minWidth: 0, overflowX: 'hidden' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.1em', margin: 0 }}>Simulation Parameters</h3>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Performance Variance (Entropy)</label>
                        <input 
                            type="range" min="0" max="1" step="0.01" 
                            value={performanceVariance} 
                            onChange={(e) => setPerformanceVariance(parseFloat(e.target.value))} 
                            style={{ accentColor: 'var(--text-primary)' }}
                        />
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Variance: {performanceVariance} | Entropy: {results?.entropy}</div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Human Grounding Index (HGI)</label>
                        <input 
                            type="range" min="0" max="1" step="0.01" 
                            value={hgiRaw} 
                            onChange={(e) => setHgiRaw(parseFloat(e.target.value))} 
                            style={{ accentColor: 'var(--text-primary)' }}
                        />
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>HGI: {hgiRaw} | Grounding: {results?.grounding}</div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Verified GPU Hours (Sacrifice)</label>
                        <input 
                            type="number" 
                            value={gpuHours} 
                            onChange={(e) => setGpuHours(parseInt(e.target.value))} 
                            style={{ padding: '0.5rem', background: 'var(--bg-color)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                        />
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Identity Verification Tier</label>
                        <select 
                            value={tier} 
                            onChange={(e) => setTier(parseInt(e.target.value))}
                            style={{ padding: '0.5rem', background: 'var(--bg-color)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                        >
                            <option value={1}>Tier 1: Sovereign (600 Max)</option>
                            <option value={2}>Tier 2: Linked (850 Max)</option>
                            <option value={3}>Tier 3: Institutional (1000 Max)</option>
                        </select>
                    </div>
                </div>

                <div style={{ background: 'var(--surface-color)', borderRadius: '8px', padding: '2rem', border: '1px solid var(--border-color)' }}>
                    <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '2rem', margin: 0 }}>Real-Time AIS Result</h3>
                    
                    <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
                        <div style={{ fontSize: '5rem', fontWeight: 900, fontFamily: 'serif', transition: 'all 0.3s ease' }}>
                            {results?.ais}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                            Comprehensive Integrity Score
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                            <span>Stability Drag</span>
                            <span style={{ fontWeight: 600 }}>× {results?.drag}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                            <span>Grounding Boost</span>
                            <span style={{ fontWeight: 600 }}>× {results?.boost}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                            <span>Base Integrity</span>
                            <span style={{ fontWeight: 600 }}>{results?.base}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem', marginTop: '0.5rem' }}>
                            <span>Identity Ceiling</span>
                            <span style={{ fontWeight: 600 }}>{results?.ceiling}</span>
                        </div>
                    </div>

                    <div style={{ marginTop: '2.5rem', padding: '1rem', background: 'var(--bg-color)', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        <Zap size={14} style={{ marginRight: '8px', verticalAlign: 'middle', color: '#f59e0b' }} />
                        <strong>Dev Tip:</strong> Increasing <strong>Grounding</strong> by 0.1 provides a 2% boost to the final AIS, while high <strong>Variance</strong> exponentially drags the score down.
                    </div>
                </div>
            </div>
        </div>
    );
};
