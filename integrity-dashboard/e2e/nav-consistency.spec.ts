import { test, expect } from '@playwright/test';

const APP_ROUTES = [
  '/dashboard', '/agents', '/treasury', '/security', '/knowledge', '/developer', '/licence', '/wiki',
];

const NAV_HREFS = [
  '/dashboard', '/agents', '/treasury', '/security', '/knowledge', '/developer', '/licence', '/wiki',
];

test.describe('authenticated navigation consistency', () => {
  for (const route of APP_ROUTES) {
    test(`${route} renders the canonical navigation`, async ({ page }) => {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
      const links = page.locator('.memory-sidebar-shell nav a');
      const sidebar = page.locator('.memory-sidebar-shell');
      await expect(links).toHaveCount(NAV_HREFS.length);
      const hrefs = await links.evaluateAll((items) => items.map((item) => item.getAttribute('href')));
      expect(hrefs).toEqual(NAV_HREFS);
      const navBounds = await sidebar.locator('nav[aria-label="Primary navigation"]').evaluate((element) => {
        const active = element.querySelector<HTMLElement>('a[aria-current="page"]');
        const nav = element.getBoundingClientRect();
        const link = active?.getBoundingClientRect();
        return Boolean(link && link.top >= nav.top && link.bottom <= nav.bottom);
      });
      expect(navBounds).toBe(true);
      await expect(sidebar.getByText('Command', { exact: true })).toBeVisible();
      await expect(sidebar.getByText('Manage', { exact: true })).toBeVisible();
      await expect(sidebar.getByText('Build', { exact: true })).toBeVisible();
    });
  }

  test('header mode uses the same canonical route order', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Branding & Layout/ }).click();
    await page.getByRole('button', { name: 'Header Navigation' }).click();

    for (const route of NAV_HREFS) {
      await page.locator(`header nav[aria-label="Primary navigation"] a[href="${route}"]`).click();
      await page.waitForTimeout(100);
      const links = page.locator('header nav[aria-label="Primary navigation"] a');
      await expect(links).toHaveCount(NAV_HREFS.length);
      const hrefs = await links.evaluateAll((items) => items.map((item) => item.getAttribute('href')));
      expect(hrefs).toEqual(NAV_HREFS);
    }
  });

  test('sidebar remains usable when the navigation exceeds the viewport', async ({ page }) => {
    await page.goto('/dashboard');
    const nav = page.locator('.memory-sidebar-shell nav[aria-label="Primary navigation"]');
    await expect(nav).toBeVisible();
    expect(await nav.evaluate((element) => element.scrollHeight)).toBeGreaterThan(await nav.evaluate((element) => element.clientHeight));
    await page.getByRole('link', { name: 'Developer', exact: true }).click();
    await expect(page).toHaveURL(/\/developer$/);
    await expect(page.getByRole('heading', { name: 'Developer', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollTop)).toBe(0);
  });
});
