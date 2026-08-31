import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('consolidated operator workspaces', () => {
  test('Agents combines fleet, identity, and intelligence', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/agents');
    await expect(page.getByRole('heading', { name: 'Agents & Identity' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Agent fleet' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Identity & verification' })).toBeVisible();
    await page.getByRole('tab', { name: 'Identity & verification' }).click();
    await expect(page.getByText('Identity Management')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('Funds & Access includes live AIS capital-gate context', async ({ page }) => {
    await page.goto('/treasury');
    await expect(page.getByRole('heading', { name: 'Funds & Access' })).toBeVisible();
    await expect(page.getByLabel('Capital gate context')).toBeVisible();
    await expect(page.getByText('Wallet', { exact: true })).toBeVisible();
    await expect(page.getByText('Staking', { exact: true })).toBeVisible();
    await expect(page.getByText('Credit', { exact: true })).toBeVisible();
  });

  test('Security & Policy merges production security tabs and excludes the attack demo', async ({ page }) => {
    await page.goto('/security');
    await expect(page.getByRole('heading', { name: 'Security & Policy' })).toBeVisible();
    for (const name of ['Endpoints & devices', 'Policy & guardians', 'Intent review', 'Correlation evidence']) {
      await expect(page.getByRole('tab', { name })).toBeVisible();
    }
    await expect(page.getByText('Live Attack Demo', { exact: true })).toHaveCount(0);
    await page.getByRole('tab', { name: 'Intent review' }).click();
    await expect(page.getByText('Kernel intent vs. outcome')).toBeVisible();
  });

  test('Knowledge retains Cortex, the full intelligence page, and evidence correlation', async ({ page }) => {
    await page.goto('/knowledge');
    await expect(page.getByRole('heading', { name: 'Knowledge & Evidence' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'AIS & knowledge' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('heading', { name: 'AIS time series' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Knowledge evidence graph' })).toBeVisible();
    await expect(page.locator('.knowledge-graph-stage')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await page.getByRole('tab', { name: 'Agent intelligence' }).click();
    await expect(page.getByRole('heading', { name: 'Intelligence & Alignment' })).toBeVisible();
    await expect(page.getByText('AIS Component Formulas')).toBeVisible();
    await page.getByRole('tab', { name: 'Evidence correlation' }).click();
    await expect(page.getByRole('heading', { name: 'Invocation Correlation' })).toBeVisible();
  });
});
