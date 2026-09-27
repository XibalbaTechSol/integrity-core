import { useEffect, useState } from 'react';
import { Eye, LockKeyhole, Plus, RefreshCw, Save, ShieldCheck, Trash2 } from 'lucide-react';
import { useDashboard } from '../context/DashboardContext';
import { userapi, type PolicyPack, type PolicyRule } from '../services/userapi';

const blankRule = (): PolicyRule => ({ tool: '', action: '', resource: '*', effect: 'allow', note: '' });

export default function PolicyPacksPage() {
  const { agents, selectedAgent } = useDashboard();
  const [packs, setPacks] = useState<PolicyPack[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [agentDid, setAgentDid] = useState(selectedAgent?.id || '');
  const [changeNote, setChangeNote] = useState('Initial observation draft');
  const [rules, setRules] = useState<PolicyRule[]>([blankRule()]);
  const [editingPackId, setEditingPackId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try { setPacks(await userapi.policyPacks()); }
    catch (err: any) { setError(err?.message || 'Could not load policy packs. Sign in to manage policies.'); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (!agentDid && selectedAgent?.id) setAgentDid(selectedAgent.id); }, [agentDid, selectedAgent]);

  const updateRule = (index: number, field: keyof PolicyRule, value: string) => {
    setRules(previous => previous.map((rule, i) => i === index ? { ...rule, [field]: value } : rule));
  };

  const createPack = async () => {
    if (!name.trim() || rules.some(rule => !rule.tool.trim() || !rule.action.trim())) return;
    setSaving(true); setError(null);
    try {
      if (editingPackId) {
        await userapi.createPolicyRevision(editingPackId, { rules, change_note: changeNote.trim() });
      } else {
        await userapi.createPolicyPack({ name: name.trim(), description: description.trim(), agent_did: agentDid || null, rules, change_note: changeNote.trim() });
      }
      setName(''); setDescription(''); setRules([blankRule()]); setChangeNote('New observation revision'); setEditingPackId(null);
      await load();
    } catch (err: any) { setError(err?.message || 'Could not save policy pack.'); }
    finally { setSaving(false); }
  };

  const activate = async (pack: PolicyPack, mode: 'observe' | 'enforce') => {
    setSaving(true); setError(null);
    try {
      const updated = await userapi.activatePolicyPack(pack.id, mode);
      setPacks(previous => previous.map(item => item.id === updated.id ? updated : item));
    } catch (err: any) { setError(err?.message || 'Could not activate policy pack.'); }
    finally { setSaving(false); }
  };

  return (
    <div className="control-page control-page-full" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      <div className="control-page-header">
        <div>
          <p className="eyebrow">Structured policy management</p>
          <h2>Policy packs</h2>
          <p className="control-page-description">Create versioned rules for an agent or workload. Saving and observation never blocks tools; enforcement is an explicit promotion.</p>
        </div>
        <ShieldCheck size={28} aria-hidden="true" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(280px, .9fr)', gap: 'var(--space-5)' }}>
        <section className="protocol-panel" style={{ padding: 'var(--space-5)' }}>
          <div className="panel-heading"><div><span className="panel-label">{editingPackId ? 'New revision' : 'Draft'}</span><h2>{editingPackId ? 'Revise policy pack' : 'Create policy pack'}</h2></div><Eye size={18} /></div>
          <div className="flex-col gap-4">
            {!editingPackId && <input className="input" aria-label="Policy pack name" placeholder="Pack name" value={name} onChange={event => setName(event.target.value)} />}
            {!editingPackId && <textarea className="input" aria-label="Policy pack description" placeholder="What does this pack govern?" value={description} onChange={event => setDescription(event.target.value)} rows={2} />}
            {!editingPackId && <select className="input" aria-label="Policy pack agent" value={agentDid} onChange={event => setAgentDid(event.target.value)}>
              <option value="">All owned agents / workload scope</option>
              {agents.map(agent => <option key={agent.id} value={agent.id}>{agent.alias || agent.name || agent.id}</option>)}
            </select>}
            <div className="flex-col gap-2">
              <span className="panel-label">Rules</span>
              {rules.map((rule, index) => (
                <div key={index} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8, alignItems: 'center' }}>
                  <input className="input" aria-label={`Rule ${index + 1} tool`} placeholder="Tool" value={rule.tool} onChange={event => updateRule(index, 'tool', event.target.value)} />
                  <input className="input" aria-label={`Rule ${index + 1} action`} placeholder="Action" value={rule.action} onChange={event => updateRule(index, 'action', event.target.value)} />
                  <input className="input" aria-label={`Rule ${index + 1} resource`} placeholder="Resource scope" value={rule.resource} onChange={event => updateRule(index, 'resource', event.target.value)} />
                  <button type="button" className="secondary-button" aria-label={`Remove rule ${index + 1}`} disabled={rules.length === 1} onClick={() => setRules(previous => previous.filter((_, i) => i !== index))}><Trash2 size={14} /></button>
                </div>
              ))}
              <button type="button" className="secondary-button" onClick={() => setRules(previous => [...previous, blankRule()])}><Plus size={14} /> Add rule</button>
            </div>
            <input className="input" aria-label="Change note" placeholder="Revision note" value={changeNote} onChange={event => setChangeNote(event.target.value)} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--success)', fontSize: '.8rem' }}><Eye size={14} /> New packs start in observation mode.</div>
            <button className="primary-button" disabled={saving || (!editingPackId && !name.trim()) || rules.some(rule => !rule.tool.trim() || !rule.action.trim())} onClick={() => void createPack()}><Save size={15} /> {editingPackId ? 'Save new observation revision' : 'Save observation draft'}</button>
            {editingPackId && <button className="secondary-button" onClick={() => { setEditingPackId(null); setRules([blankRule()]); setChangeNote('Initial observation draft'); }}>Cancel revision</button>}
          </div>
        </section>

        <section className="protocol-panel" style={{ padding: 'var(--space-5)' }}>
          <div className="panel-heading"><div><span className="panel-label">Lifecycle</span><h2>Promotion model</h2></div><LockKeyhole size={18} /></div>
          <div className="flex-col gap-4" style={{ fontSize: '.85rem' }}>
            <p className="text-muted">Draft → observe → explicit enforce. Each revision is durable and can be rolled back by promoting an earlier revision.</p>
            <div style={{ padding: 12, border: '1px solid rgba(34,197,94,.25)', background: 'rgba(34,197,94,.08)', borderRadius: 'var(--radius-sm)' }}><strong style={{ color: 'var(--success)' }}>Observation</strong><br /><span className="text-muted">Records matches and would-deny outcomes without stopping agents.</span></div>
            <div style={{ padding: 12, border: '1px solid rgba(245,158,11,.25)', background: 'rgba(245,158,11,.08)', borderRadius: 'var(--radius-sm)' }}><strong style={{ color: 'var(--warning)' }}>Enforcement</strong><br /><span className="text-muted">An explicit operator choice. It is never implied by registration.</span></div>
          </div>
        </section>
      </div>

      {error && <div role="alert" style={{ color: 'var(--danger)', background: 'var(--danger-dim)', padding: 12, borderRadius: 'var(--radius-sm)' }}>{error}</div>}
      <section className="protocol-panel" style={{ padding: 'var(--space-5)' }}>
        <div className="panel-heading"><div><span className="panel-label">Durable revisions</span><h2>Saved policy packs</h2></div><button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</button></div>
        {loading ? <p className="text-muted">Loading policy packs…</p> : packs.length === 0 ? <p className="text-muted">No policy packs yet. Create an observation draft above.</p> : (
          <div className="flex-col gap-3">
            {packs.map(pack => <div key={pack.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', border: '1px solid var(--glass-border)', padding: 14, borderRadius: 'var(--radius-sm)' }}>
              <div><strong>{pack.name}</strong><div className="text-muted" style={{ fontSize: '.78rem' }}>{pack.agent_did || 'All owned agents'} · revision {pack.latest_revision?.version ?? '—'} · {pack.latest_revision?.rules.length ?? 0} rules</div></div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}><span className={`protocol-state ${pack.mode === 'enforce' ? 'bad' : 'good'}`}><i />{pack.mode}</span><button className="secondary-button" disabled={saving || !pack.latest_revision} onClick={() => { setEditingPackId(pack.id); setName(pack.name); setDescription(pack.description); setAgentDid(pack.agent_did || ''); setRules(pack.latest_revision?.rules || [blankRule()]); setChangeNote(`Revision ${((pack.latest_revision?.version || 0) + 1).toString()}`); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>New revision</button><button className="secondary-button" disabled={saving || pack.mode === 'observe'} onClick={() => void activate(pack, 'observe')}>Observe</button><button className="primary-button" disabled={saving || pack.mode === 'enforce'} onClick={() => void activate(pack, 'enforce')}>Enforce</button></div>
            </div>)}
          </div>
        )}
      </section>
    </div>
  );
}
