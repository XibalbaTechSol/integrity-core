import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// DocsPage (src/pages/DocsPage.tsx, route "/docs") is fully static — wrapped in
// PublicLayout (src/layouts/PublicLayout.tsx), which supplies the shared header/footer
// chrome for all public routes. No backend calls on this page.

test.describe('/docs (DocsPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/docs');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('PublicLayout header: logo links home, Launch MVP links to /auth', async ({ page }) => {
    await page.goto('/docs');
    const header = page.locator('header');
    await expect(header.getByRole('link', { name: 'Xibalba Solutions' })).toHaveAttribute('href', '/');
    await expect(header.getByRole('link', { name: /Launch MVP/ })).toHaveAttribute('href', '/auth');
  });

  test('main content renders the Documentation heading and both sections', async ({ page }) => {
    await page.goto('/docs');
    await expect(page.getByRole('heading', { name: 'Documentation', level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Getting Started', level: 2 })).toBeVisible();
    await expect(page.getByText('register an agent and obtain a Developer API key')).toBeVisible();
  });

  test('PublicLayout footer: doc/privacy/terms links and copyright', async ({ page }) => {
    await page.goto('/docs');
    const footer = page.locator('footer');
    await footer.scrollIntoViewIfNeeded();
    await expect(footer.getByRole('link', { name: 'Documentation' })).toHaveAttribute('href', '/docs');
    await expect(footer.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy');
    await expect(footer.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '/terms');
    await expect(footer.getByText(/All rights reserved/)).toBeVisible();
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/docs');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/docs.png', fullPage: true });
  });
});
