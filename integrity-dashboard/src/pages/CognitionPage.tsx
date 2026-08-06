import { useState } from 'react';
import { motion } from 'framer-motion';
import { Brain, FlaskConical, GitBranch, Zap } from 'lucide-react';
import { Panel } from '../components/shared/Panel';
import { COTPlatform } from '../components/tabs/COTPlatform';
import { DiagnosticsPanel } from '../components/tabs/DiagnosticsPanel';
import { EvalsPanel } from '../components/tabs/EvalsPanel';
import { ObservabilityHub } from '../components/tabs/ObservabilityHub';
import { TokenUsagePanel } from '../components/tabs/TokenUsagePanel';

export function CognitionPage() {
  const [showReasoning, setShowReasoning] = useState(true);
  const [showDiagnostics, setShowDiagnostics] = useState(true);
  const [showEvals, setShowEvals] = useState(true);
  const [showObservability, setShowObservability] = useState(true);
  const [showUsage, setShowUsage] = useState(true);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-6)',
        padding: 'var(--space-6)',
        minHeight: '100%',
      }}
    >


      <div 
        style={{ 
          background: 'var(--bg-card)', 
          border: '1px solid var(--glass-border)', 
          borderRadius: 'var(--radius-md)', 
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderRight: '1px solid var(--glass-border)', paddingRight: '16px' }}>
          <Zap size={16} style={{ color: 'var(--primary)' }} />
          <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'white', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Modules</span>
        </div>
        
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {[
            { id: 'observability', label: 'Observability Hub', state: showObservability, set: setShowObservability },
            { id: 'reasoning', label: 'Reasoning Traces', state: showReasoning, set: setShowReasoning },
            { id: 'diagnostics', label: 'Agent Diagnostics', state: showDiagnostics, set: setShowDiagnostics },
            { id: 'evals', label: 'Mechanistic Evals', state: showEvals, set: setShowEvals },
            { id: 'usage', label: 'Token & Cost', state: showUsage, set: setShowUsage }
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
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', marginTop: 'var(--space-4)' }}>
        {showReasoning && (
          <Panel title="Chain of Thought (COT) Explorer" icon={<Brain size={18} />}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Interactive timeline of agent sub-tasks, intent resolution, tool invocations, and text stream mutations.
            </p>
            <COTPlatform />
          </Panel>
        )}

        {showDiagnostics && (
          <Panel title="Agent Diagnostics" icon={<GitBranch size={18} />}>
             <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Deep trace analysis and execution hierarchy mappings.
            </p>
            <DiagnosticsPanel />
          </Panel>
        )}

        {showEvals && (
          <Panel title="Mechanistic Evals" icon={<FlaskConical size={18} />}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Detailed LangChain-driven evaluation scores including Tool Efficiency, Reasoning Depth, and Semantic Drift mapping.
            </p>
            <EvalsPanel />
          </Panel>
        )}

        {showUsage && <TokenUsagePanel />}

        {showObservability && (
          <Panel title="Observability Hub (LangSmith-style)" icon={<Brain size={18} />}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
              Advanced platform to analyze, debug, diagnose and compare agent traces.
            </p>
            <ObservabilityHub />
          </Panel>
        )}
      </div>
    </div>
  );
}
