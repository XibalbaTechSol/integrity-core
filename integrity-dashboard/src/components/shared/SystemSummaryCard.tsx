import { useEffect, useState } from 'react';
import { BrainCircuit, ExternalLink, ShieldCheck } from 'lucide-react';
import { Panel } from './Panel';
import { useDashboard } from '../../context/DashboardContext';
import { shieldBackend } from '../../services/shieldBackend';
import { graphMemory } from '../../services/graphMemory';
import { CORTEX_UI_URL, SHIELD_TENANT_ID, SHIELD_UI_URL } from '../../config';

// Shield and Cortex each own a full operator UI now (device management, graph exploration,
// enforcement actions) with their own cookie-authenticated login -- this dashboard has no
// session with either. This card intentionally shows only a handful of read-only summary
// numbers plus a deep link, instead of re-implementing their consoles (which duplicated,
// unauthenticated device tables and graph canvases used to do here).

type Metric = { label: string; value: string };
type CardState = { loading: boolean; error: string | null; metrics: Metric[] };

const INITIAL: CardState = { loading: true, error: null, metrics: [] };

export function SystemSummaryCard({ system }: { system: 'shield' | 'cortex' }) {
  const { selectedAgent } = useDashboard();
  const [state, setState] = useState<CardState>(INITIAL);

  const label = system === 'shield' ? 'Shield' : 'Cortex';
  const uiUrl = system === 'shield' ? SHIELD_UI_URL : CORTEX_UI_URL;
  const Icon = system === 'shield' ? ShieldCheck : BrainCircuit;
  const tenantId = SHIELD_TENANT_ID || selectedAgent?.eth_address || '';

  useEffect(() => {
    let active = true;
    setState(INITIAL);
    const load = async () => {
      try {
        if (system === 'shield') {
          if (!tenantId) { if (active) setState({ loading: false, error: 'No Shield tenant configured for this dashboard.', metrics: [] }); return; }
          const summary = await shieldBackend.dashboardSummary(tenantId);
          const denied = summary.decisions_by_action?.deny ?? summary.decisions_by_action?.block ?? 0;
          const decided = Object.values(summary.decisions_by_action ?? {}).reduce((sum, v) => sum + v, 0);
          if (active) setState({
            loading: false, error: null,
            metrics: [
              { label: 'Enrolled devices', value: String(summary.device_count) },
              { label: 'Recorded decisions', value: String(decided) },
              { label: 'Denied / contained', value: String(denied) },
            ],
          });
        } else {
          const status = await graphMemory.status();
          if (active) setState({
            loading: false, error: null,
            metrics: [
              { label: 'Memories', value: String(status.memory_count) },
              { label: 'Integrity check', value: status.integrity_check },
              { label: 'Journal mode', value: status.journal_mode },
            ],
          });
        }
      } catch (err) {
        const status = (err as { status?: number })?.status;
        if (!active) return;
        if (status === 401 || status === 403) {
          setState({ loading: false, error: `${label} is up, but this dashboard has no session with it -- sign in at the ${label} console for live data.`, metrics: [] });
        } else {
          setState({ loading: false, error: `${label} is unreachable.`, metrics: [] });
        }
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [system, tenantId]);

  return (
    <Panel
      title={<><Icon size={16} /> {label}</>}
      action={<a href={uiUrl} target="_blank" rel="noreferrer" className="control-secondary-action">Open {label} console <ExternalLink size={14} /></a>}
    >
      {state.loading && <div className="control-empty compact">Checking {label}…</div>}
      {!state.loading && state.error && <div className="control-empty compact">{state.error}</div>}
      {!state.loading && !state.error && (
        <div className="control-metric-grid compact">
          {state.metrics.map((metric) => (
            <div className="control-metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
