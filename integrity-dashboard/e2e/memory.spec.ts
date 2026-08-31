import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// MemoryPage (src/pages/MemoryPage.tsx, route "/memory") is a client for xibalba-cortex's
// local_api (a separate project, VITE_GRAPH_MEMORY_URL, default http://localhost:8420) —
// entirely outside integrity-core and NOT started by `make up`. For this audit it's run
// against a fresh, isolated, empty profile home (not the real Hermes memory data) so the
// real empty-state paths are what's under test, and no real personal/session content
// leaks into test screenshots. Cortex is organized into three primary workspaces with
// contextual views: Activity, Evidence, and Control.
// No route/fetch mocking — real HTTP calls to a real local_api instance throughout.

test.describe('/memory (MemoryPage)', () => {
  // Unlike browser localStorage, the local_api backend's store is real, shared, and
  // persists across tests in this file (writes from "recording a real exchange" are not
  // rolled back) — serial mode plus source order keeps the zero-count/empty-state
  // assertions running before the one test that intentionally writes data.
  test.describe.configure({ mode: 'serial' });

  test('loads with no uncaught JS errors, API connects, real stat counts', async ({ page }) => {
    // Even against a freshly-created profile home, xibalba-cortex's own background
    // capture can populate a handful of memories/sessions immediately (session activity
    // auto-ingest) — asserting a literal "0" is asserting a state this store doesn't
    // reliably hold, not a real empty-state UI path. Assert real non-fabricated digit
    // counts instead of a specific number.
    const errors = collectPageErrors(page);
    await page.goto('/memory');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('API connected')).toBeVisible();
    await expect(page.getByText(/^\d+ memories$/)).toBeVisible();
    await expect(page.getByText(/^\d+ entities$/)).toBeVisible();
    await expect(page.getByText(/^\d+ relations$/)).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('primary workspaces and contextual views render and switch', async ({ page }) => {
    // Scoped to data-memory-tab, not text content — real recorded memory content (e.g.
    // "...Integrity Score...") can otherwise collide with a tab's own label text.
    await page.goto('/memory');
    for (const [primary, secondary] of [['activity', 'timeline'], ['evidence', 'graph'], ['activity', 'recall'], ['control', 'inference'], ['evidence', 'integrity']]) {
      await page.locator(`[data-memory-tab="${primary}"]`).click();
      const button = page.locator(`[data-memory-tab="${secondary}"]`);
      await button.click();
      await expect(button).toHaveClass(/active/);
    }
  });

  test('Timeline tab: reconstructs sessions and keeps manual capture secondary', async ({ page }) => {
    await page.goto('/memory');
    await page.locator('[data-memory-tab="activity"]').click();
    await page.locator('[data-memory-tab="timeline"]').click();
    // MemoryPage auto-selects the first real session on load (refresh() sets
    // selectedSessionId to nextSessions[0]) — with xibalba-cortex's own background
    // capture active, that session can already have real exchanges, so both the
    // populated and empty timeline are legitimate states here, not just the empty one.
    const empty = page.getByText('No reconstructed events');
    const exchange = page.locator('.memory-exchange');
    await expect(empty.or(exchange.first())).toBeVisible();
    await expect(page.getByText('Sessions', { exact: true })).toBeVisible();
    await expect(page.getByText('Capture an exchange manually')).toBeVisible();
    await page.getByText('Capture an exchange manually').click();
    await expect(page.getByPlaceholder('Session id')).toBeVisible();
    await expect(page.getByPlaceholder('User prompt')).toBeVisible();
    await expect(page.getByPlaceholder('Full model response')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record exchange' })).toBeVisible();
  });

  test('Timeline tab: recording a real exchange against the live local_api creates a real, visible exchange', async ({ page, request }) => {
    // Guard against the exact mistake this spec is built to avoid (see the file-header
    // comment): if local_api's store lives under a real Hermes profile rather than a
    // throwaway --home, this test would write fabricated [e2e-*] memories into someone's
    // actual persistent memory. `~/.hermes/` is that real profile's documented default
    // location (xibalba-cortex/CLAUDE.md's "Storage defaults to ~/.hermes/xibalba-cortex")
    // -- refuse to write against it rather than silently polluting real data.
    const graphMemoryUrl = process.env.VITE_GRAPH_MEMORY_URL || 'http://localhost:8420';
    const statusResponse = await request.get(`${graphMemoryUrl}/api/status`);
    const status = await statusResponse.json();
    const dbPath = String(status.db_path || '');
    test.skip(
      dbPath.includes('/.hermes/'),
      `local_api's store (${dbPath}) looks like a real Hermes profile, not a throwaway ` +
      `--home -- refusing to write test data into it. Start local_api with --home pointed ` +
      `at a fresh, empty directory instead (see docs/TESTING.md).`
    );

    await page.goto('/memory');
    await page.locator('[data-memory-tab="activity"]').click();
    await page.locator('[data-memory-tab="timeline"]').click();
    await page.getByText('Capture an exchange manually').click();
    const before = await page.getByText(/^\d+ memories$/).innerText();
    const beforeCount = parseInt(before, 10);

    // Content-addressed: local_api dedups memories by content_hash, so recording the
    // exact same prompt/response text twice (e.g. across repeated suite runs against
    // the same persistent backend) correctly does NOT create a second memory — that's
    // real, intended dedup behavior, not a bug. A unique nonce per run keeps this
    // assertion meaningful instead of flaking on a rerun.
    const nonce = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const prompt = `What is the Agentic Integrity Score? [e2e-${nonce}]`;
    const response = `AIS is a weighted geometric mean of four component scores. [e2e-${nonce}]`;

    await page.getByPlaceholder('Session id').fill('e2e-memory-session');
    await page.getByPlaceholder('User prompt').fill(prompt);
    await page.getByPlaceholder('Full model response').fill(response);
    await page.getByRole('button', { name: 'Record exchange' }).click();

    await expect(page.getByText(prompt)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(response)).toBeVisible();
    // The header's live memory count must reflect the real write — strictly greater
    // than whatever the real baseline was, not a specific fabricated number.
    //
    // The badge text always matches /^\d+ memories$/ (even a stale "0"), so a single
    // toBeVisible() + one-shot innerText() read races ahead of CortexPage's async
    // post-write refresh() -- poll until the count actually reflects the write instead
    // of asserting on a single snapshot.
    await expect(async () => {
      const after = await page.getByText(/^\d+ memories$/).innerText();
      expect(parseInt(after, 10)).toBeGreaterThan(beforeCount);
    }).toPass({ timeout: 10000 });
  });

  test('Graph tab: filter controls render; graph stage shows real (now non-empty) data or its empty state', async ({ page }) => {
    await page.goto('/memory');
    await page.locator('[data-memory-tab="evidence"]').click();
    await page.locator('[data-memory-tab="graph"]').click();
    await expect(page.locator('.memory-shell-graph')).toBeVisible();
    await expect(page.locator('.memory-shell-graph .memory-inspector')).toHaveCount(0);
    await expect(page.getByText('Filters & Controls')).toBeVisible();
    await expect(page.getByRole('button', { name: 'All edges' })).toBeVisible();
    const unavailable = page.getByText('Graph data is unavailable.');
    const canvas = page.locator('.memory-graph-stage canvas');
    await expect(unavailable.or(canvas)).toBeVisible({ timeout: 10000 });
  });

  test('Recall tab: initial empty prompt state, then a real search against local_api', async ({ page }) => {
    await page.goto('/memory');
    await page.locator('[data-memory-tab="activity"]').click();
    await page.locator('[data-memory-tab="recall"]').click();
    await expect(page.getByText('Search the local memory store')).toBeVisible();

    await page.getByPlaceholder('Search memory content').fill('Agentic Integrity Score');
    const noMatches = page.getByText('No matching memories.');
    const resultItem = page.locator('.memory-list-item');
    await expect(noMatches.or(resultItem.first())).toBeVisible({ timeout: 10000 });
  });

  test('Inference tab: automatic-capture copy and review queue render with real empty state', async ({ page }) => {
    await page.goto('/memory');
    await page.locator('[data-memory-tab="control"]').click();
    await page.locator('[data-memory-tab="inference"]').click();
    await expect(page.getByText('Automatic capture')).toBeVisible();
    await expect(page.getByText(/Hermes automatically records prompts/)).toBeVisible();
    await expect(page.getByText('Review queue')).toBeVisible();
    await expect(page.getByText('No candidate results in this state.')).toBeVisible();
    await expect(page.getByText('No PARA proposals are waiting for review.')).toBeVisible();
  });

  test('Integrity tab: real store-status and integrity-links panels render live values', async ({ page }) => {
    await page.goto('/memory');
    await page.locator('[data-memory-tab="evidence"]').click();
    await page.locator('[data-memory-tab="integrity"]').click();
    await expect(page.getByText('Store status')).toBeVisible();
    await expect(page.getByText('Integrity links')).toBeVisible();
    // Real schema/journal/FTS5 values from the local_api /api/status response — never
    // "n/a", which would mean the fetch silently failed on a page claiming "Local checks".
    await expect(page.getByText('n/a')).toHaveCount(0);
    await expect(page.getByText('enabled').first()).toBeVisible();
  });

  test('refresh button re-fetches all panels without crashing', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/memory');
    await page.waitForLoadState('networkidle');
    // CortexPage.tsx's refresh button aria-label is "Refresh Cortex data" -- stale here
    // from before the /memory -> /cortex rename (see App.tsx's compatibility redirect).
    await page.getByRole('button', { name: 'Refresh Cortex data' }).click();
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('screenshot confirms final rendered state of the Timeline tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/memory');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/memory.png', fullPage: true });
  });
});
