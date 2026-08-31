import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// PrivacyPage (src/pages/PrivacyPage.tsx, route "/privacy") is fully static, wrapped in
// PublicLayout. No backend calls.

test.describe('/privacy (PrivacyPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/privacy');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('PublicLayout header: logo links home, Launch MVP links to /auth', async ({ page }) => {
    await page.goto('/privacy');
    const header = page.locator('header');
    await expect(header.getByRole('link', { name: 'Xibalba Solutions' })).toHaveAttribute('href', '/');
    await expect(header.getByRole('link', { name: /Launch MVP/ })).toHaveAttribute('href', '/auth');
  });

  test('main content renders Privacy Policy heading and both numbered sections', async ({ page }) => {
    await page.goto('/privacy');
    await expect(page.getByRole('heading', { name: 'Privacy Policy', level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: '1. Data Collection', level: 2 })).toBeVisible();
    await expect(page.getByRole('heading', { name: '2. Zero-Knowledge Processing', level: 2 })).toBeVisible();
    await expect(page.getByText(/No personally identifiable information \(PII\)/)).toBeVisible();
  });

  test('PublicLayout footer renders on this route', async ({ page }) => {
    await page.goto('/privacy');
    const footer = page.locator('footer');
    await footer.scrollIntoViewIfNeeded();
    await expect(footer.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy');
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/privacy');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/privacy.png', fullPage: true });
  });
});
