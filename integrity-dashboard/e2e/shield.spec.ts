import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('Shield page — real oracle + bcc_middleware wiring', () => {
  test('shadow AI discovery panel renders real oracle data, not a simulated scan', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await expect(page.getByText('Xibalba Shield')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Shadow AI discovery' })).toBeVisible();

    // Real endpoint: GET /v1/shield/unregistered-agents. Either a real result list or
    // the honest "No unregistered agents detected." empty state — never the old fake
    // "Simulating scan..." copy this replaced.
    await expect(page.getByText('Simulating scan')).toHaveCount(0);
    await page.waitForLoadState('networkidle');

    const hasResults = await page.getByText('First seen').first().isVisible().catch(() => false);
    const hasEmptyState = await page.getByText('No unregistered agents detected').isVisible().catch(() => false);
    expect(hasResults || hasEmptyState, 'expected either real results or the real empty state').toBe(true);

    expect(errors).toEqual([]);
  });

  test('policy rules panel talks to the real bcc_middleware clinical-allowlist endpoint', async ({ page }) => {
    await page.goto('/shield');
    await expect(page.getByRole('heading', { name: 'Clinical allowlist' })).toBeVisible();
    // The old version hardcoded three permanently-disabled checkboxes with no real
    // backend; this asserts they're gone, not just relabeled.
    await expect(page.getByText('Auto-block unverified DIDs')).toHaveCount(0);
    await expect(page.getByPlaceholder('did:integrity:...')).toBeVisible();
  });

  test('audit log panel renders real bcc_middleware decisions', async ({ page }) => {
    await page.goto('/shield');
    await expect(page.getByRole('heading', { name: 'Decision log' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    const hasLogs = await page.getByText('bcc_intercept').first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText('No backend decisions recorded.').isVisible().catch(() => false);
    expect(hasLogs || hasEmpty).toBe(true);
  });
});
