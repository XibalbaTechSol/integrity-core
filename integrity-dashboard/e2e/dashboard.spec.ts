import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// Dashboard (src/Dashboard.tsx, route "/dashboard") is the most oracle-heavy page: every
// stat/chart/table is populated by real oracle.* calls keyed off DashboardContext's
// selectedAgent. This replaces the pre-existing e2e/dashboard.spec.ts (superseded, same
// filename) under this audit's screenshot-as-truth discipline — no route/fetch mocking.

test.describe('/dashboard (Dashboard)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('renders either a real agent dashboard or the honest no-agent empty state', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const emptyState = page.getByText('No registered agents found on this network.');
    const liveHeading = page.getByRole('heading', { name: 'Dashboard' });
    await expect(emptyState.or(liveHeading)).toBeVisible();
  });

  test('with a real agent: stat panels show real numbers/dashes, never fabricated placeholders', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByRole('heading', { name: 'Dashboard' }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack');

    await expect(page.getByText('Live AIS Score')).toBeVisible();
    await expect(page.getByText('$ITK Staked')).toBeVisible();
    await expect(page.getByText('ZK Boost')).toBeVisible();
    await expect(page.getByText('Flagged Telemetry Rate')).toBeVisible();
    // Every stat value is either a real number/percentage or the explicit "—" no-data
    // marker — never blank, never "undefined"/"NaN" leaking from an unguarded render.
    // Scoped to the main content area, not `page` globally — a page-wide substring
    // search for "NaN" false-positives on the sidebar's "Financials" nav link
    // (case-insensitive substring match: "fi-NAN-cials"), confirmed while writing this.
    const main = page.locator('.main-app-layout').first();
    await expect(main.getByText(/^(—|\d)/).first()).toBeVisible();
    await expect(main.getByText('undefined', { exact: false })).toHaveCount(0);
    await expect(main.locator('text=/\\bNaN\\b/')).toHaveCount(0);
    // Also check inside the radar chart's SVG specifically — Recharts renders literal
    // "NaN" tick/label text when fed values wildly outside a chart's declared domain
    // (this caught a real bug: components were on a 0-1000 scale but the radar's data
    // mapping multiplied by 100 as if they were 0-1 fractions — fixed in Dashboard.tsx).
    await expect(page.locator('svg text', { hasText: 'NaN' })).toHaveCount(0);
  });

  test('AIS Trend and Radar charts show real data or their real empty-state copy', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByRole('heading', { name: 'Dashboard' }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack');

    await expect(page.getByRole('heading', { name: 'AIS Trend (Last Hour Buckets)' })).toBeVisible();
    const trendEmpty = page.getByText('No history yet for this window.');
    const trendChart = page.locator('.recharts-line');
    await expect(trendEmpty.or(trendChart)).toBeVisible();

    await expect(page.getByRole('heading', { name: 'AIS Components (Radar)' })).toBeVisible();
    const radarEmpty = page.getByText('No AIS reading yet.');
    const radarChart = page.locator('.recharts-radar');
    await expect(radarEmpty.or(radarChart)).toBeVisible();
  });

  test('Recent Agent Activity table and Policy Audit Feed show real rows or their real empty copy', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByRole('heading', { name: 'Dashboard' }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack');

    await expect(page.getByRole('heading', { name: 'Recent Agent Activity' })).toBeVisible();
    const noTraces = page.getByText('No recent traces.');
    const traceTable = page.locator('table');
    await expect(noTraces.or(traceTable)).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Policy Audit Feed' })).toBeVisible();
    const noAudit = page.getByText('No audit events recorded yet.');
    await expect(noAudit).toBeVisible().catch(async () => {
      // Real audit rows present instead — just confirm at least one DENY/ALLOW-style entry.
      // .first() -- a real feed has multiple entries, so the bare locator is a strict-mode
      // violation once more than one DENY/ALLOW row is present.
      await expect(page.getByText(/^(DENY|ALLOW):/).first()).toBeVisible();
    });
  });

  test('"View All" link on Recent Agent Activity navigates to /intelligence', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByRole('heading', { name: 'Dashboard' }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack');

    await page.getByRole('link', { name: 'View All' }).click();
    await expect(page).toHaveURL(/\/intelligence/);
  });

  test('Chain-of-Thought Explorer panel renders without crashing', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByRole('heading', { name: 'Dashboard' }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack');

    await expect(page.getByRole('heading', { name: 'Observability: Chain-of-Thought Explorer' })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/dashboard.png', fullPage: true });
  });
});
