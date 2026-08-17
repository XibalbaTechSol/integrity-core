import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// TermsPage (src/pages/TermsPage.tsx, route "/terms") is fully static, wrapped in
// PublicLayout. No backend calls.

test.describe('/terms (TermsPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/terms');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('PublicLayout header: logo links home, Launch MVP links to /auth', async ({ page }) => {
    await page.goto('/terms');
    const header = page.locator('header');
    await expect(header.getByRole('link', { name: 'Xibalba Solutions' })).toHaveAttribute('href', '/');
    await expect(header.getByRole('link', { name: /Launch MVP/ })).toHaveAttribute('href', '/auth');
  });

  test('main content renders Terms of Service heading and both numbered sections', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.getByRole('heading', { name: 'Terms of Service', level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: '1. Protocol Usage', level: 2 })).toBeVisible();
    await expect(page.getByRole('heading', { name: '2. Liability', level: 2 })).toBeVisible();
    await expect(page.getByText(/not liable for financial losses/)).toBeVisible();
  });

  test('PublicLayout footer renders on this route', async ({ page }) => {
    await page.goto('/terms');
    const footer = page.locator('footer');
    await footer.scrollIntoViewIfNeeded();
    await expect(footer.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '/terms');
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/terms');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/terms.png', fullPage: true });
  });
});
