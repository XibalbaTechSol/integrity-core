import { useState, useEffect } from 'react';
import { Coins, AlertTriangle } from 'lucide-react';
import { Panel } from '../shared/Panel';
import { oracle, type AgentUsageDto, type AgentEventDto } from '../../services/oracle';
import { useDashboard } from '../../context/useDashboard';

/** Token classes in the order they cost money: fresh input, generated output, then the
 *  cache classes. Any type the emitter reports that isn't listed here still renders — the
 *  list only fixes the order of the ones we know about, rather than hiding the rest. */
const KNOWN_TOKEN_ORDER = ['input', 'output', 'cacheCreation', 'cacheRead'];

const TOKEN_LABELS: Record<string, string> = {
  input: 'Input',
  output: 'Output',
  cacheCreation: 'Cache Write',
  cacheRead: 'Cache Read',
};

function orderTokenTypes(tokens: Record<string, number>): string[] {
  const known = KNOWN_TOKEN_ORDER.filter((t) => t in tokens);
  const rest = Object.keys(tokens).filter((t) => !KNOWN_TOKEN_ORDER.includes(t)).sort();
  return [...known, ...rest];
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

export function TokenUsagePanel() {
  const { selectedAgent } = useDashboard() as any;
  const [usage, setUsage] = useState<AgentUsageDto | null>(null);
  const [events, setEvents] = useState<AgentEventDto[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const did = selectedAgent?.eth_address;
    if (!did) {
      setUsage(null);
      setEvents([]);
      setIsLoading(false);
      return;
    }
    let mounted = true;
    setIsLoading(true);
    Promise.all([
      oracle.getUsage(did).catch(() => null),
      oracle.getEvents(did, 25).catch(() => [] as AgentEventDto[]),
    ]).then(([u, e]) => {
      if (!mounted) return;
      setUsage(u);
      setEvents(e);
      setIsLoading(false);
    });
    return () => {
      mounted = false;
    };
    // DID string, not the agent object — DashboardProvider re-polls every 15s and builds a
    // fresh object each time, so an object dep would refetch on every poll.
  }, [selectedAgent?.eth_address]);

  const tokenTypes = usage ? orderTokenTypes(usage.tokens) : [];
  // Token metrics and log events arrive over separate OTLP services, so an agent can have
  // one without the other (e.g. a runtime exporting logs but not metrics). Gating the whole
  // panel on token counts would hide real events; treat either as "has something to show".
  const hasTokens = usage !== null && usage.total_tokens > 0;
  const hasUsage = hasTokens || events.length > 0;

  return (
    <Panel title="TOKEN & COST USAGE" icon={<Coins size={18} />}>
      <p style={{ margin: '0 0 var(--space-4)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
        Provider-reported token consumption and cost, from the agent runtime's own OpenTelemetry
        export. Cache classes are tracked separately because they price differently from fresh input.
      </p>

      {/* Never let this be mistaken for scored evidence: it arrives over the unauthenticated
          OTLP port and carries no agent signature, so it is not an AIS input. */}
      {usage && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 12px',
            marginBottom: 'var(--space-4)',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.7rem',
            color: 'var(--text-muted)',
          }}
        >
          <AlertTriangle size={14} style={{ color: 'var(--warning, #f59e0b)', flexShrink: 0 }} />
          <span>
            Evidence tier <strong style={{ color: 'var(--text-primary)' }}>{usage.evidence_tier}</strong> —
            runtime-reported and unsigned, so it does not feed the Agent Integrity Score. Useful for cost
            visibility and for cross-checking what the agent itself attests.
          </span>
        </div>
      )}

      {isLoading ? (
        <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading usage…
        </div>
      ) : !hasUsage ? (
        <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)' }}>
          <div style={{ fontWeight: 700, marginBottom: 6, color: 'var(--text-primary)' }}>
            No usage reported
          </div>
          <div style={{ fontSize: '0.8rem' }}>
            This agent's runtime has not exported OpenTelemetry metrics to the oracle. For Claude Code,
            set <code>CLAUDE_CODE_ENABLE_TELEMETRY=1</code> with{' '}
            <code>OTEL_EXPORTER_OTLP_ENDPOINT</code> and an{' '}
            <code>integrity.agent.id</code> resource attribute.
          </div>
        </div>
      ) : (
        <>
          {hasTokens && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(auto-fit, minmax(140px, 1fr))`,
              gap: 'var(--space-3)',
              marginBottom: 'var(--space-5)',
            }}
          >
            {tokenTypes.map((type) => (
              <div
                key={type}
                style={{
                  padding: 'var(--space-3)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  {TOKEN_LABELS[type] ?? type}
                </div>
                <div className="mono" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                  {formatTokens(usage!.tokens[type])}
                </div>
              </div>
            ))}
            <div
              style={{
                padding: 'var(--space-3)',
                background: 'var(--primary-dim)',
                border: '1px solid var(--primary)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Reported Cost
              </div>
              <div className="mono" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--primary)' }}>
                ${usage!.total_cost_usd.toFixed(4)}
              </div>
            </div>
          </div>
          )}

          {usage && Object.keys(usage.cost_usd_by_model).length > 0 && (
            <div style={{ marginBottom: 'var(--space-5)' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Cost by model
              </div>
              <table style={{ width: '100%', fontSize: '0.8rem' }}>
                <tbody>
                  {Object.entries(usage.cost_usd_by_model)
                    .sort((a, b) => b[1] - a[1])
                    .map(([model, cost]) => (
                      <tr key={model}>
                        <td className="mono" style={{ padding: '4px 0', color: 'var(--text-primary)' }}>{model}</td>
                        <td className="mono" style={{ padding: '4px 0', textAlign: 'right', color: 'var(--text-muted)' }}>
                          ${cost.toFixed(4)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}

          {events.length > 0 && (
            <div>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Recent runtime events ({events.length})
              </div>
              <div style={{ maxHeight: 240, overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: '0.75rem' }}>
                  <thead>
                    <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                      <th style={{ padding: '4px 0' }}>Event</th>
                      <th style={{ padding: '4px 0' }}>Model</th>
                      <th style={{ padding: '4px 0', textAlign: 'right' }}>Tokens in/out</th>
                      <th style={{ padding: '4px 0', textAlign: 'right' }}>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e, idx) => {
                      const attrs = e.attributes ?? {};
                      const inTok = attrs['input_tokens'];
                      const outTok = attrs['output_tokens'];
                      return (
                        <tr key={`${e.time}-${idx}`}>
                          <td className="mono" style={{ padding: '4px 0', color: 'var(--text-primary)' }}>
                            {e.event_name ?? '(unnamed)'}
                          </td>
                          <td className="mono" style={{ padding: '4px 0', color: 'var(--text-muted)' }}>
                            {String(attrs['model'] ?? '—')}
                          </td>
                          <td className="mono" style={{ padding: '4px 0', textAlign: 'right', color: 'var(--text-muted)' }}>
                            {inTok !== undefined || outTok !== undefined
                              ? `${inTok ?? '—'} / ${outTok ?? '—'}`
                              : '—'}
                          </td>
                          <td className="mono" style={{ padding: '4px 0', textAlign: 'right', color: 'var(--text-muted)' }}>
                            {new Date(e.time).toLocaleTimeString()}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
