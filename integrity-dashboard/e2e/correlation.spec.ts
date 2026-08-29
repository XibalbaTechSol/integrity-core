import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('/correlation (Cortex invocation correlation)', () => {
  test('is a primary navigation surface and degrades honestly when sources are offline', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/correlation');
    await expect(page.getByRole('heading', { name: 'Invocation Correlation' })).toBeVisible();
    await expect(page.getByText('Observed invocations')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Correlation' })).toBeVisible();
    await expect(page.getByText(/Partial view:|Cortex, Shield, and Oracle responded/)).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('filters and refresh control remain operable', async ({ page }) => {
    await page.goto('/correlation');
    await page.getByRole('button', { name: 'Needs attention' }).click();
    await expect(page.getByRole('button', { name: 'Needs attention' })).toHaveCSS('cursor', 'pointer');
    await page.getByRole('button', { name: 'Refresh evidence' }).click();
    await expect(page.getByRole('heading', { name: 'Invocation Correlation' })).toBeVisible();
  });

  test('desktop and mobile layouts do not overflow', async ({ page }) => {
    await page.goto('/correlation');
    await expect(page.getByRole('heading', { name: 'Invocation Correlation' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: 'e2e/screenshots/correlation-desktop.png', fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Invocation Correlation' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: 'e2e/screenshots/correlation-mobile.png', fullPage: true });
  });
});
