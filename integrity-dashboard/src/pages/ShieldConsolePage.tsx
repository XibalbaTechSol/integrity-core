import { ExternalLink, ShieldCheck } from 'lucide-react';
import { SHIELD_UI_URL, withSharedAgentScope } from '../config';
import { useDashboard } from '../context/DashboardContext';

/**
 * Shield owns its operator console in xibalba-shield/ui.
 *
 * The Integrity dashboard keeps this route as a boundary and handoff only; it
 * must not grow a second device, policy, or enforcement console here.
 */
export default function ShieldConsolePage() {
  const { selectedAgent } = useDashboard();
  return (
    <div className="control-page control-page-full">
      <div className="control-page-header">
        <div>
          <p className="eyebrow">Enforcement plane</p>
          <h2>Shield console</h2>
          <p className="control-page-description">
            Endpoint inventory, policy deployment, event response, and Shield identity management
            live in the dedicated xibalba-shield UI.
          </p>
        </div>
        <ShieldCheck size={28} aria-hidden="true" />
      </div>

      <section className="control-empty" aria-labelledby="shield-console-boundary">
        <h3 id="shield-console-boundary">Dedicated Shield workspace</h3>
        <p>
          This dashboard shows protocol-level evidence and namespace context. Shield’s
          authenticated controls are maintained and served from <code>xibalba-shield/ui</code>.
        </p>
        <a className="control-primary-action" href={withSharedAgentScope(SHIELD_UI_URL, selectedAgent || undefined)} target="_blank" rel="noreferrer">
          Open Shield UI <ExternalLink size={15} />
        </a>
      </section>
    </div>
  );
}
