import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

export interface Step {
  id: string;
  label: string;
  status: 'pending' | 'loading' | 'completed' | 'error';
}

interface TransactionStepperProps {
  steps: Step[];
  title?: string;
}

export function TransactionStepper({ steps, title }: TransactionStepperProps) {
  return (
    <div className="flex-col gap-4" style={{ padding: 'var(--space-4)', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)' }}>
      {title && <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)', marginBottom: 'var(--space-2)' }}>{title}</div>}
      <div className="flex-col gap-3">
        {steps.map((step, i) => (
          <div key={step.id} className="flex items-center gap-3">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {step.status === 'completed' && <CheckCircle2 size={18} color="var(--success)" />}
              {step.status === 'loading' && <Loader2 size={18} className="animate-spin" color="var(--primary)" />}
              {step.status === 'pending' && <Circle size={18} color="var(--text-muted)" opacity={0.5} />}
              {step.status === 'error' && <Circle size={18} color="var(--danger)" />}
            </div>
            <div className="flex-col">
              <div style={{ 
                fontSize: '0.8125rem', 
                fontWeight: step.status === 'loading' ? 600 : 400,
                color: step.status === 'completed' ? 'var(--text-primary)' : step.status === 'loading' ? 'var(--primary)' : 'var(--text-muted)'
              }}>
                {step.label}
              </div>
            </div>
            {i < steps.length - 1 && (
              <div style={{ position: 'absolute', left: '25px', marginTop: '30px', width: '2px', height: '12px', background: step.status === 'completed' ? 'var(--success)' : 'var(--glass-border)' }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
