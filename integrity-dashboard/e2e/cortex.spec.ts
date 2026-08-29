import { expect, test, type Page, type Route } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// These intercepted responses are deterministic UI-contract fixtures. They prove that
// the dashboard sends and renders the documented Cortex HTTP contract; they are NOT
// evidence that a live Cortex store, retrieval engine, or operator pipeline is healthy.
const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

async function installCortexContract(page: Page) {
  await page.route('http://localhost:8420/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === '/api/extraction-proposals' && request.method() === 'GET') {
      return json(route, [{
        id: 'proposal-1',
        task_id: 'task-1',
        task_type: 'entity_extraction',
        item_index: 0,
        source_memory_id: 'memory-1',
        source_content_hash: 'sha256:source-memory-1',
        payload: { entity: 'Integrity Protocol', type: 'project' },
        evidence_quote: 'Integrity Protocol uses evidence-backed controls.',
        status: 'proposed',
        decision_note: null,
        decided_by: null,
        created_at: '2026-08-28T12:00:00Z',
        decided_at: null,
      }]);
    }
    if (url.pathname === '/api/inference/tasks') return json(route, []);
    if (url.pathname === '/api/embedding/models') return json(route, []);
    if (url.pathname === '/api/projections/memories/checkpoints') return json(route, []);

    if (url.pathname === '/api/retrieval/hybrid' && request.method() === 'POST') {
      expect(request.postDataJSON()).toEqual({
        query: 'operator controls',
        limit: 8,
        max_per_source: 3,
        max_total_chars: 12000,
      });
      return json(route, {
        trace_id: 'trace-contract-001',
        root_hash: 'sha256:retrieval-root-contract-001',
        signals: ['lexical', 'vector'],
        channel_status: { lexical: 'available', vector: 'available', graph: 'degraded' },
        degraded: [{ channel: 'graph', reason: 'fixture-degraded' }],
        results: [{
          id: 'memory-1',
          content: 'Operator controls require explicit evidence and human approval.',
          content_hash: 'sha256:memory-contract-001',
          status: 'active',
          source: { kind: 'model_exchange', metadata: {} },
          quarantine_reasons: [],
          supersedes_id: null,
          evidence_class: 'recorded',
        }],
      });
    }
    if (url.pathname === '/api/retrieval/trace/trace-contract-001') {
      return json(route, {
        id: 'trace-contract-001', query: 'operator controls', signals: ['lexical', 'vector'],
        results: [{
          rank: 1, memory_id: 'memory-1', score: 0.91, signals: ['lexical', 'vector'],
          channels: { lexical: { rank: 1, raw_score: 0.8 }, vector: { rank: 1, raw_score: 0.9 } },
          cosine_similarity: 0.9,
          provenance: { content_hash: 'sha256:memory-contract-001', source_id: 'memory-1', evidence_class: 'recorded', status: 'active' },
        }],
        root_hash: 'sha256:retrieval-root-contract-001', profile_domain: 'xibalba',
        query_vector_hash: 'sha256:query-vector', embedding_model_id: 'fixture-model',
        embedding_model_revision: '1', filters: {}, candidate_pool_sizes: { lexical: 1, vector: 1 },
        rrf_params: { method: 'rrf', k: 60, weights: { lexical: 1, vector: 1 } },
        graph_evidence: [], leaf_hashes: ['sha256:memory-contract-001'], degraded: [],
        checkpoint_id: 'checkpoint-contract-001', linked_task_id: null, linked_session_id: null,
        created_at: '2026-08-28T12:00:00Z',
      });
    }
    if (url.pathname === '/api/retrieval/trace/trace-contract-001/evidence') {
      expect(url.searchParams.get('rank')).toBe('1');
      return json(route, {
        domain: 'retrieval_trace', index: 0, payload_hash: 'sha256:memory-contract-001',
        siblings: [{ hash: 'sha256:sibling-contract-001' }], root: 'sha256:retrieval-root-contract-001',
      });
    }
    if (url.pathname === '/api/extraction-proposals/proposal-1/decision' && request.method() === 'POST') {
      expect(request.postDataJSON()).toEqual({ decision: 'accept', decided_by: 'integrity-dashboard' });
      return json(route, { id: 'proposal-1', status: 'accepted' });
    }

    return json(route, { error: `Unhandled UI-contract fixture: ${request.method()} ${url.pathname}` }, 501);
  });
}

test.describe('/cortex Operations tab', () => {
  test('redirects the legacy Memory route into the Cortex workspace', async ({ page }) => {
    await page.route('http://localhost:8420/api/**', route => route.abort('connectionrefused'));
    await page.goto('/memory');

    await expect(page).toHaveURL(/\/cortex$/);
    await expect(page.getByRole('heading', { name: 'Cortex', exact: true })).toBeVisible();
  });

  test('renders an honest partial view when every Cortex operator endpoint is offline', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.route('http://localhost:8420/api/**', route => route.abort('connectionrefused'));

    await page.goto('/cortex');
    await expect(page.getByRole('heading', { name: 'Cortex', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Operations' }).click();

    await expect(page.getByRole('heading', { name: 'Operations' })).toBeVisible();
    await expect(page.getByRole('status')).toContainText('Partial view: Cortex APIs unavailable');
    await expect(page.getByRole('status')).toContainText('extraction review');
    await expect(page.getByRole('status')).toContainText('inference queue');
    await expect(page.getByRole('status')).toContainText('embedding registry');
    await expect(page.getByRole('status')).toContainText('projection health');
    await expect(page.getByText('No placeholder records are shown.')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('renders deterministic hybrid retrieval evidence from the browser API contract', async ({ page }) => {
    await installCortexContract(page);
    await page.goto('/cortex');
    await page.getByRole('button', { name: 'Operations' }).click();
    await expect(page.getByText('Cortex operator APIs online.')).toBeVisible();

    await page.getByRole('textbox', { name: 'Cortex retrieval query' }).fill('operator controls');
    await page.getByRole('button', { name: 'Retrieve' }).click();

    await expect(page.getByText('Operator controls require explicit evidence and human approval.')).toBeVisible();
    await expect(page.getByText('graph: degraded')).toBeVisible();
    await expect(page.getByText(/checkpoint checkpoint-/)).toBeVisible();
    await expect(page.getByText(/lexical \+ vector/)).toBeVisible();
    await expect(page.getByText(/Rank 1 inclusion proof: 1 sibling hashes/)).toBeVisible();
  });

  test('accepts an extraction proposal through the deterministic operator contract', async ({ page }) => {
    await installCortexContract(page);
    await page.goto('/cortex');
    await page.getByRole('button', { name: 'Operations' }).click();

    await expect(page.getByText('Integrity Protocol uses evidence-backed controls.')).toBeVisible();
    await page.getByRole('button', { name: 'Accept' }).click();

    await expect(page.getByRole('alert')).toHaveText('Proposal accepted into canonical memory.');
    await expect(page.getByText('Integrity Protocol uses evidence-backed controls.')).toHaveCount(0);
    await expect(page.getByText('No proposed extractions awaiting review.')).toBeVisible();
  });
});
