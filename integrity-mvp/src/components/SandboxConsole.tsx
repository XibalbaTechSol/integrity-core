import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Zap, Code } from 'lucide-react';

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

    const calculateScores = useCallback(() => {
        const MAX_SCORE = 1000;
        
        // Metric 1: Entropy
        const entropyScore = Math.round(Math.exp(-1.5 * Math.pow(performanceVariance, 2)) * MAX_SCORE);
        const stabilityDrag = entropyScore / MAX_SCORE;

        // Metric 2: Grounding
        const groundingScore = Math.round(hgiRaw * MAX_SCORE);
        const groundingBoost = 1.0 + (hgiRaw * 0.2);

        // Metric 3: Base Integrity Components
        const trustflowIdx = Math.min(1.0, avgPartnerAIS / 1000.0);
        const auditIdx = 0.95; // Xibalba Audit Score (Simulated)
        const sacrificeIdx = Math.min(1.0, Math.log10(gpuHours + 1) / 3.0);
        const ageIdx = Math.min(1.0, Math.log10(agentAge + 1) / 2.56);
        const stakingAgeIdx = (0.5 * stakedRatio) + (0.5 * ageIdx);
        const volumeIdx = Math.min(1.0, Math.log10(volume + 1) / 6.0);

        const baseIntegrity = (
            (0.25 * trustflowIdx) +   // W_TRUSTFLOW
            (0.25 * auditIdx) +      // W_XIBALBA
            (0.20 * sacrificeIdx) +  // W_SACRIFICE
            (0.15 * stakingAgeIdx) + // W_STAKING_AGE
            (0.15 * volumeIdx)       // W_VOLUME
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
    }, [performanceVariance, hgiRaw, avgPartnerAIS, gpuHours, stakedRatio, agentAge, volume, tier]);

    useEffect(() => {
        calculateScores();
    }, [calculateScores]);

    return (
        <div className="enterprise-card custom-scrollbar" style={{ padding: '40px', height: '100%', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '32px' }}>
                <Code className="text-gold" size={24} />
                <h2 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>Protocol Sandbox</h2>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                    <span className="badge-gold">v8.3 TRI-METRIC</span>
                </div>
            </div>

            <div className="dash-grid-2">
                {/* Inputs */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    <h3 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Simulation Parameters</h3>
                    
                    <div className="input-group">
                        <label>Performance Variance (Entropy)</label>
                        <input 
                            type="range" min="0" max="1" step="0.01" 
                            value={performanceVariance} 
                            onChange={(e) => setPerformanceVariance(parseFloat(e.target.value))} 
                        />
                        <div className="input-footer">Variance: {performanceVariance} | Entropy: {results?.entropy}</div>
                    </div>

                    <div className="input-group">
                        <label>Human Grounding Index (HGI)</label>
                        <input 
                            type="range" min="0" max="1" step="0.01" 
                            value={hgiRaw} 
                            onChange={(e) => setHgiRaw(parseFloat(e.target.value))} 
                        />
                        <div className="input-footer">HGI: {hgiRaw} | Grounding: {results?.grounding}</div>
                    </div>

                    <div className="input-group">
                        <label>Verified GPU Hours (Sacrifice)</label>
                        <input
                            type="number"
                            value={gpuHours}
                            onChange={(e) => setGpuHours(parseInt(e.target.value))}
                        />
                        <div className="input-footer">Logarithmic scale applied</div>
                    </div>

                    <div className="input-group">
                        <label>Avg. Partner AIS (Trustflow)</label>
                        <input
                            type="range" min="0" max="1000" step="10"
                            value={avgPartnerAIS}
                            onChange={(e) => setAvgPartnerAIS(parseFloat(e.target.value))}
                        />
                        <div className="input-footer">Avg. Partner AIS: {avgPartnerAIS}</div>
                    </div>

                    <div className="input-group">
                        <label>Staked Ratio</label>
                        <input
                            type="range" min="0" max="1" step="0.01"
                            value={stakedRatio}
                            onChange={(e) => setStakedRatio(parseFloat(e.target.value))}
                        />
                        <div className="input-footer">Staked Ratio: {stakedRatio}</div>
                    </div>

                    <div className="input-group">
                        <label>Agent Age (Days)</label>
                        <input
                            type="number"
                            value={agentAge}
                            onChange={(e) => setAgentAge(parseInt(e.target.value))}
                        />
                        <div className="input-footer">Logarithmic scale applied</div>
                    </div>

                    <div className="input-group">
                        <label>Transaction Volume (ITK)</label>
                        <input
                            type="number"
                            value={volume}
                            onChange={(e) => setVolume(parseInt(e.target.value))}
                        />
                        <div className="input-footer">Logarithmic scale applied</div>
                    </div>

                    <div className="input-group">
                        <label>Identity Verification Tier</label>
                        <select value={tier} onChange={(e) => setTier(parseInt(e.target.value))}>
                            <option value={1}>Tier 1: Sovereign (600 Max)</option>
                            <option value={2}>Tier 2: Linked (850 Max)</option>
                            <option value={3}>Tier 3: Institutional (1000 Max)</option>
                        </select>
                    </div>
                </div>

                {/* Live Output */}
                <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '24px', padding: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <h3 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '32px' }}>Real-Time AIS Result</h3>
                    
                    <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                        <motion.div 
                            key={results?.ais}
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            style={{ fontSize: '5rem', fontWeight: 900, color: 'var(--gold)', fontFamily: 'inherit' }}
                        >
                            {results?.ais}
                        </motion.div>
                        <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.2em' }}>
                            Comprehensive Integrity Score
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div className="result-row">
                            <span>Stability Drag</span>
                            <span className="text-gold">× {results?.drag}</span>
                        </div>
                        <div className="result-row">
                            <span>Grounding Boost</span>
                            <span className="text-gold">× {results?.boost}</span>
                        </div>
                        <div className="result-row">
                            <span>Base Integrity <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)' }}>(incl. fixed 0.95 audit score)</span></span>
                            <span className="text-gold">{results?.base}</span>
                        </div>
                        <div className="result-row" style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '16px' }}>
                            <span>Identity Ceiling</span>
                            <span>{results?.ceiling}</span>
                        </div>
                    </div>

                    <div style={{ marginTop: '40px', padding: '16px', background: 'rgba(212, 175, 55, 0.05)', borderRadius: '12px', border: '1px solid rgba(212, 175, 55, 0.1)', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>
                        <Zap size={14} style={{ color: 'var(--gold)', marginRight: '8px', verticalAlign: 'middle' }} />
                        <strong>Dev Tip:</strong> Increasing <strong>Grounding</strong> by 0.1 provides a 2% boost to the final AIS, while high <strong>Variance</strong> exponentially drags the score down.
                    </div>
                </div>
            </div>
        </div>
    );
};
