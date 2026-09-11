import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('cross-platform identity dashboard', () => {
  for (const route of ['/fleet', '/memory']) {
    test(`${route} has an explicit live-data surface and no uncaught browser errors`, async ({ page }) => {
      const errors = collectPageErrors(page);
      await page.goto(route);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('.memory-sidebar-shell nav[aria-label="Primary navigation"]')).toBeVisible();
      await expect(page.locator('body')).not.toContainText('No route matches');
      expect(errors, `Uncaught errors: ${errors.map((e) => e.message).join('; ')}`).toEqual([]);
    });
  }

  test('primary navigation exposes both cross-platform entry points', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('link', { name: 'Fleet', exact: true })).toHaveAttribute('href', '/fleet');
    await expect(page.getByRole('link', { name: 'Memory', exact: true })).toHaveAttribute('href', '/memory');
  });
});
