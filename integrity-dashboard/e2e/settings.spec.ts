import { test, expect, Page } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// SettingsPage (src/pages/SettingsPage.tsx, route "/settings") has four tabs. Appearance/
// Branding/Privacy are local-state/on-chain and work unauthenticated; the Developer API
// tab talks to real userapi-issued API keys (src/context/SettingsContext.tsx) and needs a
// real signed-in session — each Playwright test gets a fresh browser context (no shared
// session), so the authed tests register a brand-new real account via the real /auth UI
// flow first, exactly as a user would, rather than injecting a token.

const uniqueEmail = (label: string) => `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

async function registerAndSignIn(page: Page) {
  await page.goto('/auth');
  await page.getByRole('button', { name: 'Sign Up' }).click();
  await page.getByPlaceholder('john@example.com').fill(uniqueEmail('settings'));
  await page.getByPlaceholder('••••••••').fill('correct horse battery staple 1');
  await page.getByRole('button', { name: /^Sign Up/ }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });
}

test.describe('/settings (SettingsPage)', () => {
  test('loads with no uncaught JS errors, defaults to the Appearance tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: 'Appearance Settings' })).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('Appearance tab: switching theme updates the document data-theme attribute', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: 'Cyber Mode' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'cyber');
    await page.getByRole('button', { name: 'Dark Mode' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  });

  test('Appearance tab: font size slider updates the displayed value', async ({ page }) => {
    await page.goto('/settings');
    const slider = page.locator('input[type="range"]');
    await expect(page.getByText('Font Size: 16px')).toBeVisible();
    await slider.fill('20');
    await expect(page.getByText('Font Size: 20px')).toBeVisible();
  });

  test('Branding tab: app name persists to localStorage under appSettings', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Branding & Layout/ }).click();
    await expect(page.getByRole('heading', { name: 'Branding & Layout' })).toBeVisible();
    const nameInput = page.locator('input[type="text"]').first();
    await nameInput.fill('E2E Test Protocol');
    await expect.poll(async () => {
      const raw = await page.evaluate(() => localStorage.getItem('appSettings'));
      return raw ? JSON.parse(raw).appName : null;
    }).toBe('E2E Test Protocol');
  });

  test('Branding tab: navigation layout toggle switches sidebar to header mode live', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Branding & Layout/ }).click();
    await expect(page.locator('.memory-sidebar-shell, aside').first()).toBeVisible();
    await page.getByRole('button', { name: 'Header Navigation' }).click();
    await expect(page.locator('.memory-sidebar-shell')).toHaveCount(0);
    // Switch back so later tests in this file see the default sidebar layout.
    await page.getByRole('button', { name: 'Sidebar Navigation' }).click();
  });

  test('Developer API tab: signed-out state shows the real sign-in prompt, not fake keys', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Developer API/ }).click();
    await expect(page.getByText('Sign in to manage real userapi-issued API keys.')).toBeVisible();
    await expect(page.getByText('No API keys generated yet.')).toBeVisible();
  });

  test('Privacy & Security tab renders the real PrivacyPanel', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Privacy & Security/ }).click();
    await expect(page.getByRole('heading', { name: 'Privacy & Security Options' })).toBeVisible();
  });

  test('Developer API tab: signed-in user can generate, view, and revoke a real API key', async ({ page }) => {
    await registerAndSignIn(page);
    await page.goto('/settings');
    await page.getByRole('button', { name: /Developer API/ }).click();

    await expect(page.getByText('Sign in to manage real userapi-issued API keys.')).not.toBeVisible();
    await page.getByRole('button', { name: /Generate Key/ }).click();

    // Anchor on the key's `id` (rendered in <strong>) rather than the Revoke button or
    // raw-key <code> block — both disappear after revocation (the button conditionally
    // unmounts, and the raw key is only ever returned once, by the create response, not
    // by the list refresh), which would make a locator built on either self-invalidate
    // mid-test. strong -> meta wrapper -> header row -> card: three levels up reaches
    // the card, which also holds the sibling <code> raw-key block.
    const keyIdText = page.locator('strong').first();
    await expect(keyIdText).toBeVisible({ timeout: 10000 });
    const keyId = (await keyIdText.innerText()).trim();
    const keyRow = () => page.locator('strong', { hasText: keyId }).locator('../../..');

    await expect(keyRow().locator('code')).toBeVisible();
    await expect(page.getByText('No API keys generated yet.')).not.toBeVisible();

    await keyRow().getByTitle('Revoke Key').click();
    await expect(keyRow().getByText(/Revoked:/)).toBeVisible({ timeout: 10000 });
    await expect(keyRow().getByTitle('Revoke Key')).toHaveCount(0);
  });

  test('screenshot confirms final rendered state of the Appearance tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/settings.png', fullPage: true });
  });
});
