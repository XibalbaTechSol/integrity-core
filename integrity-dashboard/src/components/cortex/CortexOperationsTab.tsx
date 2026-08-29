import { FormEvent, useCallback, useEffect, useState } from 'react';
import { BrainCircuit, Check, Database, RefreshCw, Search, ShieldAlert, X } from 'lucide-react';
import { graphMemory } from '../../services/graphMemory';
import type {
  EmbeddingModel,
  ExtractionProposal,
  HybridRetrieveResult,
  InferenceTask,
  MerkleInclusionProof,
  ProjectionCheckpoint,
  ProjectionReconciliation,
  RetrievalTrace,
} from '../../types/graphMemory';

type ProjectionId = 'memories' | 'entities' | 'relations';

const cardStyle = {
  background: 'var(--surface-color)',
  border: '1px solid var(--border-color)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-5)',
} as const;

const buttonStyle = {
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  background: 'var(--bg-color)',
  color: 'var(--text-primary)',
  padding: '0.65rem 0.9rem',
  cursor: 'pointer',
} as const;

const shortHash = (value: string) => value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
const isLoopbackHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);

export default function CortexOperationsTab() {
  const [query, setQuery] = useState('');
  const [retrieval, setRetrieval] = useState<HybridRetrieveResult | null>(null);
  const [trace, setTrace] = useState<RetrievalTrace | null>(null);
  const [proof, setProof] = useState<MerkleInclusionProof | null>(null);
  const [proposals, setProposals] = useState<ExtractionProposal[]>([]);
  const [tasks, setTasks] = useState<InferenceTask[]>([]);
  const [models, setModels] = useState<EmbeddingModel[]>([]);
  const [projectionId, setProjectionId] = useState<ProjectionId>('memories');
  const [checkpoints, setCheckpoints] = useState<ProjectionCheckpoint[]>([]);
  const [reconciliation, setReconciliation] = useState<ProjectionReconciliation | null>(null);
  const [offline, setOffline] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async (selectedProjection: ProjectionId = projectionId) => {
    const results = await Promise.allSettled([
      graphMemory.extractionProposals('proposed', 50),
      graphMemory.inferenceTasks('pending', 50),
      graphMemory.embeddingModels(),
      graphMemory.projectionCheckpoints(selectedProjection, 20),
    ]);
    const unavailable: string[] = [];
    if (results[0].status === 'fulfilled') setProposals(results[0].value); else unavailable.push('extraction review');
    if (results[1].status === 'fulfilled') setTasks(results[1].value); else unavailable.push('inference queue');
    if (results[2].status === 'fulfilled') setModels(results[2].value); else unavailable.push('embedding registry');
    if (results[3].status === 'fulfilled') setCheckpoints(results[3].value); else unavailable.push('projection health');
    setOffline(unavailable);
  }, [projectionId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const runRetrieval = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy('retrieval');
    setNotice(null);
    try {
      const result = await graphMemory.hybridRetrieve({ query: query.trim(), limit: 8, max_per_source: 3, max_total_chars: 12000 });
      setRetrieval(result);
      const [traceResult, proofResult] = await Promise.allSettled([
        graphMemory.retrievalTrace(result.trace_id),
        result.results.length > 0 ? graphMemory.retrievalTraceEvidence(result.trace_id, 1) : Promise.resolve(null),
      ]);
      setTrace(traceResult.status === 'fulfilled' ? traceResult.value : null);
      setProof(proofResult.status === 'fulfilled' ? proofResult.value : null);
    } catch (error) {
      setNotice(`Retrieval unavailable: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const decide = async (proposal: ExtractionProposal, decision: 'accept' | 'dismiss') => {
    setBusy(proposal.id);
    try {
      await graphMemory.decideExtractionProposal(proposal.id, decision);
      setProposals(current => current.filter(item => item.id !== proposal.id));
      setNotice(`Proposal ${decision === 'accept' ? 'accepted into canonical memory' : 'dismissed'}.`);
    } catch (error) {
      setNotice(`Decision failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const runProjectionAction = async (action: 'checkpoint' | 'reconcile' | 'rebuild') => {
    setBusy(action);
    setNotice(null);
    try {
      if (action === 'checkpoint') await graphMemory.createProjectionCheckpoint(projectionId);
      if (action === 'reconcile') setReconciliation(await graphMemory.reconcileProjectionCheckpoint(projectionId));
      if (action === 'rebuild') {
        const rebuilt = await graphMemory.rebuildProjectionCheckpoint(projectionId);
        setNotice(`Projection rebuild ${rebuilt.verified ? 'verified' : 'failed independent verification'}.`);
      }
      await refresh(projectionId);
    } catch (error) {
      setNotice(`Projection action failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="cortex-operations-heading" style={{ padding: 'var(--space-6)', display: 'grid', gap: 'var(--space-5)', minWidth: 0 }}>
      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <BrainCircuit size={28} color="var(--theme-accent)" />
          <h2 id="cortex-operations-heading" style={{ margin: 0 }}>Operations</h2>
        </div>
        <p style={{ color: 'var(--text-secondary)', maxWidth: 820 }}>
          Inspect retrieval evidence, approve deterministic extraction proposals, and verify derived projections against Cortex's canonical SQLite store.
        </p>
      </header>

      {offline.length > 0 ? (
        <div role="status" style={{ ...cardStyle, borderColor: '#f59e0b', color: '#f59e0b', display: 'flex', gap: 10 }}>
          <ShieldAlert size={18} /> Partial view: Cortex APIs unavailable for {offline.join(', ')}. No placeholder records are shown.
        </div>
      ) : (
        <div role="status" style={{ color: '#10b981', fontSize: '.85rem' }}>Cortex operator APIs online.</div>
      )}
      {!isLoopbackHost && <div role="alert" style={{ ...cardStyle, borderColor: '#f59e0b', color: '#f59e0b' }}>Cortex write controls are disabled outside a loopback dashboard until operator authentication is enforced.</div>}
      {notice && <div role="alert" style={{ ...cardStyle, padding: '0.85rem 1rem' }}>{notice}</div>}

      <section style={cardStyle}>
        <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Evidence-backed retrieval</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '.85rem' }}>Rank fusion may degrade when vector or graph evidence is unavailable; channel state and the persisted trace remain visible.</p>
        <form onSubmit={runRetrieval} style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input aria-label="Cortex retrieval query" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search canonical memory" style={{ flex: '1 1 280px', minWidth: 0, padding: '.75rem', borderRadius: 6, border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-primary)' }} />
          <button disabled={busy === 'retrieval' || !query.trim()} style={buttonStyle}><Search size={16} /> {busy === 'retrieval' ? 'Tracing…' : 'Retrieve'}</button>
        </form>
        {retrieval && (
          <div style={{ marginTop: 18 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: '.75rem', color: 'var(--text-secondary)' }}>
              {Object.entries(retrieval.channel_status).map(([channel, status]) => <span key={channel} style={{ padding: '4px 8px', border: '1px solid var(--border-color)', borderRadius: 999 }}>{channel}: {status}</span>)}
            </div>
            <p style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>Trace {shortHash(retrieval.trace_id)} · root {shortHash(retrieval.root_hash)}{trace?.checkpoint_id ? ` · checkpoint ${shortHash(trace.checkpoint_id)}` : ' · no projection checkpoint linked'}</p>
            {proof && <p style={{ fontSize: '.75rem', color: '#10b981' }}>Rank 1 inclusion proof: {proof.siblings.length} sibling hashes · root {shortHash(proof.root)}</p>}
            <div style={{ display: 'grid', gap: 10 }}>
              {retrieval.results.map((memory, index) => (
                <article key={memory.id} style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12, contentVisibility: 'auto' }}>
                  <strong>#{index + 1} · {memory.source.kind}</strong>
                  <p style={{ margin: '6px 0', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{memory.content.slice(0, 600)}</p>
                  <small style={{ color: 'var(--text-muted)' }}>{shortHash(memory.content_hash)} · {trace?.results[index]?.signals.join(' + ') || 'trace pending'}</small>
                </article>
              ))}
              {retrieval.results.length === 0 && <p>No canonical memory matched this query.</p>}
            </div>
          </div>
        )}
      </section>

      <div className="cortex-operations-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.25fr) minmax(280px, .75fr)', gap: 'var(--space-5)' }}>
        <section style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div><h2 style={{ margin: 0, fontSize: '1.1rem' }}>Extraction review</h2><p style={{ color: 'var(--text-secondary)', fontSize: '.8rem' }}>Human approval is required before proposed facts enter canonical memory.</p></div>
            <button aria-label="Refresh Cortex operations" onClick={() => void refresh()} style={buttonStyle}><RefreshCw size={16} /></button>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {proposals.map(proposal => (
              <article key={proposal.id} style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                <strong>{proposal.task_type}</strong>
                <p style={{ color: 'var(--text-secondary)', fontSize: '.85rem' }}>{proposal.evidence_quote || 'No evidence quote supplied.'}</p>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '.72rem', color: 'var(--text-muted)' }}>{JSON.stringify(proposal.payload, null, 2)}</pre>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button disabled={busy === proposal.id || !isLoopbackHost} onClick={() => void decide(proposal, 'accept')} style={{ ...buttonStyle, color: '#10b981' }}><Check size={15} /> Accept</button>
                  <button disabled={busy === proposal.id || !isLoopbackHost} onClick={() => void decide(proposal, 'dismiss')} style={{ ...buttonStyle, color: '#f43f5e' }}><X size={15} /> Dismiss</button>
                </div>
              </article>
            ))}
            {proposals.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No proposed extractions awaiting review.</p>}
          </div>
        </section>

        <section style={cardStyle}>
          <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Inference queue</h2>
          <div style={{ display: 'grid', gap: 8 }}>
            {tasks.slice(0, 8).map(task => <div key={task.id} style={{ borderTop: '1px solid var(--border-color)', paddingTop: 10 }}><strong>{task.task_type}</strong><small style={{ display: 'block', color: 'var(--text-muted)' }}>{task.subject_type} · attempts {task.attempt_count ?? 0}</small></div>)}
            {tasks.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No pending inference tasks.</p>}
          </div>
          <h3 style={{ marginTop: 24, fontSize: '.95rem' }}>Embedding registry</h3>
          {models.map(model => <div key={model.model_key} style={{ marginBottom: 10 }}><strong>{model.model_id}</strong><small style={{ display: 'block', color: 'var(--text-muted)' }}>{model.state} · {model.availability} · {model.dimension} dimensions</small></div>)}
          {models.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No embedding models reported.</p>}
        </section>
      </div>

      <section style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div><h2 style={{ margin: 0, fontSize: '1.1rem' }}>Projection integrity</h2><p style={{ color: 'var(--text-secondary)', fontSize: '.8rem' }}>Recompute derived views against canonical storage; mismatches remain degraded until explicitly rebuilt.</p></div>
          <select aria-label="Projection" value={projectionId} onChange={event => setProjectionId(event.target.value as ProjectionId)} style={{ ...buttonStyle, minWidth: 150 }}><option value="memories">Memories</option><option value="entities">Entities</option><option value="relations">Relations</option></select>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0' }}>
          <button disabled={Boolean(busy) || !isLoopbackHost} onClick={() => void runProjectionAction('checkpoint')} style={buttonStyle}>Create checkpoint</button>
          <button disabled={Boolean(busy) || !isLoopbackHost} onClick={() => void runProjectionAction('reconcile')} style={buttonStyle}>Reconcile</button>
          <button disabled={Boolean(busy) || !isLoopbackHost} onClick={() => void runProjectionAction('rebuild')} style={buttonStyle}><Database size={15} /> Rebuild & verify</button>
        </div>
        {reconciliation && <p style={{ color: reconciliation.equal ? '#10b981' : '#f59e0b' }}>Last reconciliation: {reconciliation.equal ? 'canonical root matches' : `${reconciliation.action}; ${reconciliation.missing.length} missing, ${reconciliation.extra.length} extra`}.</p>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
          {checkpoints.slice(0, 6).map(checkpoint => <article key={checkpoint.id} style={{ border: '1px solid var(--border-color)', borderRadius: 6, padding: 12 }}><strong>{checkpoint.leaf_count} leaves</strong><small style={{ display: 'block', color: checkpoint.status === 'active' ? '#10b981' : '#f59e0b' }}>{checkpoint.status}</small><code style={{ fontSize: '.68rem' }}>{shortHash(checkpoint.root_hash)}</code></article>)}
          {checkpoints.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No checkpoints recorded for this projection.</p>}
        </div>
      </section>
    </section>
  );
}
