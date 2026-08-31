import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('/dashboard command overview', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('renders the cross-system control plane without browser errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await expect(page.getByRole('heading', { name: 'Command Overview' })).toBeVisible();
    const status = page.getByLabel('System service status');
    await expect(status.getByText('Integrity Core', { exact: true })).toBeVisible();
    await expect(status.getByText('Shield', { exact: true })).toBeVisible();
    await expect(status.getByText('Cortex', { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('integrates fleet, ITK, policy, knowledge, AIS, correlation, and COT surfaces', async ({ page }) => {
    await expect(page.getByText('Registered agents', { exact: true })).toBeVisible();
    await expect(page.getByText('Fleet ITK balance', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Gated actions' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Cortex operating context' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Agent Integrity Score' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Intent → policy → outcome' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Chain-of-Thought Explorer' })).toBeVisible();
    await expect(page.getByLabel('Evidence correlation flow')).toBeVisible();
  });

  test('never leaks undefined or NaN from partial backend states', async ({ page }) => {
    const main = page.locator('.command-center');
    await expect(main.getByText('undefined', { exact: false })).toHaveCount(0);
    await expect(main.locator('text=/\\bNaN\\b/')).toHaveCount(0);
  });

  test('primary shortcuts navigate to consolidated workspaces', async ({ page }) => {
    await page.getByRole('link', { name: /Manage agents/ }).click();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.getByRole('heading', { name: 'Agents & Identity' })).toBeVisible();
  });

  test('screenshot captures the integrated overview', async ({ page }) => {
    await page.screenshot({ path: 'e2e/screenshots/command-overview.png', fullPage: true });
  });
});
