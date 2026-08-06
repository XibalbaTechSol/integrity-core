import { useState, useEffect } from 'react';
import { Panel } from '../shared/Panel';
import { ShieldCheck, AlertTriangle, RefreshCw } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';
import { oracle, type AuditLogEntryDto } from '../../services/oracle';

interface ComplianceEvent {
  id: string;
  type: 'success' | 'warning' | 'info';
  text: string;
  time: string;
}

// The audit trail is the real "compliance events" source: bcc_middleware's
// ALLOW/DENY intercept decisions + flagged telemetry for this agent
// (oracle /v1/audit-log). A deny reads as a warning, a shadow would-be-block as
// info, everything else as success.
function mapAuditEvent(e: AuditLogEntryDto): ComplianceEvent {
  const isDeny = e.decision === 'deny' || e.decision === 'STATUS_CODE_ERROR';
  const isShadow = e.decision === 'shadow_deny';
  return {
    id: e.id,
    type: isDeny ? 'warning' : isShadow ? 'info' : 'success',
    text: e.detail || `${e.event_type}: ${e.reason_code ?? e.decision}`,
    time: new Date(e.created_at).toLocaleString(),
  };
}

export function CompliancePanel() {
  const { selectedAgent } = useDashboard();
  const [score, setScore] = useState(0);
  const [isCompliant, setIsCompliant] = useState<boolean | null>(null);
  const [vertical, setVertical] = useState<string | null>(null);
  const [events, setEvents] = useState<ComplianceEvent[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchComplianceData = async () => {
    if (!selectedAgent) return;
    setLoading(true);
    try {
      // Real compliance score comes from the agent's AIS compliance component
      // (already resolved by the oracle in DashboardProvider).
      setScore(selectedAgent.compliance_score || 0);

      // Real on-chain/vertical compliance status + the real audit trail.
      const [compliance, auditLog] = await Promise.all([
        oracle.getCompliance(selectedAgent.eth_address).catch(() => null),
        oracle.getAuditLog(selectedAgent.eth_address, 25).catch(() => [] as AuditLogEntryDto[]),
      ]);
      setIsCompliant(compliance?.is_compliant ?? null);
      setVertical(compliance?.vertical ?? null);
      setEvents(auditLog.map(mapAuditEvent));
    } catch (err) {
      console.error('Failed to fetch compliance data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchComplianceData();
  }, [selectedAgent]);

  return (
    <div className="grid-cols-2">
      <Panel 
        title="Compliance Scorecard" 
        icon={<ShieldCheck size={18} />}
        action={
          <button className="btn btn-icon" onClick={fetchComplianceData} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        }
      >
        {!selectedAgent ? (
          <div className="text-muted">Select an agent</div>
        ) : (
          <>
            <div style={{ textAlign: 'center', padding: 'var(--space-4) 0' }}>
              <div style={{ fontSize: '4.5rem', fontWeight: 800, color: 'var(--success)', lineHeight: 1, textShadow: '0 0 20px rgba(16, 185, 129, 0.4)' }}>
                {score}
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '2px', marginTop: '8px' }}>Overall Rating</div>
              {selectedAgent.verification_tier !== undefined && (
                <div style={{ fontSize: '0.85rem', color: 'var(--primary)', marginTop: '8px', fontWeight: 600 }}>
                  Verified Tier {selectedAgent.verification_tier}
                </div>
              )}
              {isCompliant !== null && (
                <div style={{ fontSize: '0.85rem', marginTop: '8px', fontWeight: 600, color: isCompliant ? 'var(--success)' : 'var(--warning)' }}>
                  {vertical ? `${vertical} · ` : ''}{isCompliant ? 'Compliant' : 'Non-compliant'}
                </div>
              )}
            </div>

            <div className="flex-col gap-3">
              {/* Real audit-trail events for this agent */}
              {events.length === 0 && (
                <div className="text-muted" style={{ fontSize: '0.75rem', textAlign: 'center', padding: 'var(--space-3)' }}>No recorded compliance events</div>
              )}
              {events.map(event => (
                 <div key={event.id} className="flex items-center justify-between" style={{ padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--glass-border)', fontSize: '0.75rem' }}>
                    <span className="text-muted">{event.text}</span>
                    <span style={{ color: event.type === 'warning' ? 'var(--warning)' : 'var(--success)', fontWeight: 600 }}>{event.time}</span>
                 </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <Panel title="Audit Trail & Alerts" icon={<AlertTriangle size={18} />}>
        <div className="flex-col gap-3">
          {events.length === 0 && (
            <div className="text-muted" style={{ fontSize: '0.8rem', textAlign: 'center', padding: 'var(--space-4)' }}>
              {selectedAgent ? 'No audit events for this agent yet' : 'Select an agent'}
            </div>
          )}
          {events.map(event => (
            <div key={event.id} style={{ 
              padding: 'var(--space-4)', 
              background: 'var(--bg-card)', 
              borderRadius: 'var(--radius-sm)', 
              borderLeft: `4px solid ${
                event.type === 'success' ? 'var(--success)' : 
                event.type === 'warning' ? 'var(--warning)' : 'var(--primary)'
              }` 
            }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)' }}>{event.text}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>{event.time}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
