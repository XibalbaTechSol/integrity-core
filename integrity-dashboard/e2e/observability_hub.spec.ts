import { test, expect } from '@playwright/test';

const mockTraces = [
  {
    trace_id: 'trace_aaa',
    agent_id: 'xibalba-hermes-master',
    task_name: 'Summarize patient records',
    status: 'SUCCESS',
    start_time: '2026-07-05T12:00:00Z',
    total_latency_ms: 2450,
    tokens_total: 1820,
  },
  {
    trace_id: 'trace_bbb',
    agent_id: 'xibalba-hermes-master',
    task_name: 'Generate compliance report',
    status: 'FAILED',
    start_time: '2026-07-05T12:05:00Z',
    total_latency_ms: 5100,
    tokens_total: 3200,
  },
  {
    trace_id: 'trace_ccc',
    agent_id: 'xibalba-hermes-master',
    task_name: 'Deploy smart contract',
    status: 'SUCCESS',
    start_time: '2026-07-05T12:10:00Z',
    total_latency_ms: 1200,
    tokens_total: 900,
  },
];

const mockSpans = [
  {
    span_id: 'span_01',
    trace_id: 'trace_aaa',
    parent_span_id: null,
    agent_id: 'xibalba-hermes-master',
    interaction_type: 'THOUGHT',
    operation_name: 'plan_extraction',
    start_time: '2026-07-05T12:00:00Z',
    end_time: '2026-07-05T12:00:01Z',
    duration_ms: 800,
    tokens_in: 200,
    tokens_out: 150,
  },
  {
    span_id: 'span_02',
    trace_id: 'trace_aaa',
    parent_span_id: 'span_01',
    agent_id: 'xibalba-hermes-master',
    interaction_type: 'TOOL',
    operation_name: 'fetch_records',
    start_time: '2026-07-05T12:00:01Z',
    end_time: '2026-07-05T12:00:03Z',
    duration_ms: 1650,
    tokens_in: 300,
    tokens_out: 670,
  },
];

test.describe('ObservabilityHub E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      (window as any).ethereum = {
        isMetaMask: true,
        request: async () => [],
        on: () => {},
        removeListener: () => {},
      };
    });

    await page.route('**/v1/traces', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockTraces),
      });
    });

    await page.route('**/v1/spans?trace_id=*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSpans),
      });
    });

    await page.goto('/integrity/#/integrity');
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      (window as any).__setActiveTab('reasoning');
    });
    await page.waitForTimeout(500);
  });

  test('renders the ObservabilityHub with all tab buttons', async ({ page }) => {
    await expect(page.getByText('Observability Hub (LangSmith-style)')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Trace Explorer' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Waterfall Diagnostics' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Comparison Engine' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Datasets & Evals' })).toBeVisible();
  });

  test('Trace Explorer shows trace rows from backend', async ({ page }) => {
    await expect(page.getByRole('cell', { name: 'Summarize patient records' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Generate compliance report' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Deploy smart contract' })).toBeVisible();

    await expect(page.getByText('SUCCESS', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('FAILED', { exact: true }).first()).toBeVisible();

    await expect(page.getByText('2,450ms')).toBeVisible();
    await expect(page.getByText('5,100ms')).toBeVisible();
  });

  test('search filters traces by task name', async ({ page }) => {
    const searchInput = page.getByPlaceholder('Search traces by intent or task...');
    await searchInput.fill('compliance');
    await page.waitForTimeout(300);

    await expect(page.getByRole('cell', { name: 'Generate compliance report' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Summarize patient records' }).first()).not.toBeVisible();
    await expect(page.getByRole('cell', { name: 'Deploy smart contract' }).first()).not.toBeVisible();
  });

  test('clicking a trace row opens Waterfall Diagnostics', async ({ page }) => {
    await page.getByRole('cell', { name: 'Summarize patient records' }).click();
    await page.waitForTimeout(500);

    // Verify waterfall header shows trace details
    await expect(page.locator('h3', { hasText: 'Summarize patient records' })).toBeVisible();
    await expect(page.getByText('trace_aaa')).toBeVisible();
    await expect(page.getByText('Total Latency')).toBeVisible();
    await expect(page.getByText('2450ms', { exact: true }).first()).toBeVisible();

    // Verify span labels appear in the waterfall chart
    await expect(page.getByText('plan_extraction')).toBeVisible();
    await expect(page.getByText('fetch_records')).toBeVisible();
  });

  test('Comparison Engine allows selecting two traces', async ({ page }) => {
    await page.getByRole('button', { name: 'Comparison Engine' }).click();
    await page.waitForTimeout(300);

    await expect(page.getByText('Trace A', { exact: true })).toBeVisible();
    await expect(page.getByText('Trace B', { exact: true })).toBeVisible();

    const selects = page.locator('select');
    await selects.nth(0).selectOption({ label: 'Summarize patient records' });
    await selects.nth(1).selectOption({ label: 'Generate compliance report' });
    await page.waitForTimeout(300);

    // Verify side-by-side comparison panels render
    await expect(page.locator('h4', { hasText: 'Summarize patient records' })).toBeVisible();
    await expect(page.locator('h4', { hasText: 'Generate compliance report' })).toBeVisible();
    await expect(page.getByText('Detailed span comparison feature is active').first()).toBeVisible();
  });

  test('Datasets & Evals tab shows create button', async ({ page }) => {
    await page.getByRole('button', { name: 'Datasets & Evals' }).click();
    await page.waitForTimeout(300);

    await expect(page.getByText('Evaluation Datasets')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create New Dataset' })).toBeVisible();
  });
});
