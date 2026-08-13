import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// AuthPage (src/pages/AuthPage.tsx, route "/auth") talks to the real userapi service
// (src/services/userapi.ts, VITE_USERAPI_URL) — no mocking. Registration/login create
// real rows in userapi's Postgres, so each test uses a fresh unique email to stay
// independent and idempotent across repeated runs.

// userapi's RegisterRequest schema validates email via python-email-validator, which
// correctly rejects RFC 2606 reserved TLDs (.test, .invalid, etc.) as non-deliverable —
// confirmed against the live service (a 422 "special-use or reserved name" error) while
// writing this spec. example.com is itself RFC 2606-reserved-for-documentation but passes
// email-validator's syntax/deliverability check, so it's the correct fake domain to use.
const uniqueEmail = (label: string) => `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

test.describe('/auth (AuthPage)', () => {
  test('loads with no uncaught JS errors, defaults to the Sign In view', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/auth');
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: 'Welcome Back' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Sign In/ })).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('toggles between Sign In and Create Account views', async ({ page }) => {
    await page.goto('/auth');
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await expect(page.getByRole('heading', { name: 'Create Account' })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Sign Up/ })).toBeVisible();

    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page.getByRole('heading', { name: 'Welcome Back' })).toBeVisible();
  });

  test('registering a brand-new real account against userapi navigates to /dashboard', async ({ page }) => {
    await page.goto('/auth');
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await page.getByPlaceholder('john@example.com').fill(uniqueEmail('register'));
    await page.getByPlaceholder('••••••••').fill('correct horse battery staple 1');
    await page.getByRole('button', { name: /^Sign Up/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });
  });

  test('registering the same email twice surfaces a real userapi conflict error, not a silent failure', async ({ page }) => {
    const email = uniqueEmail('dupe');
    await page.goto('/auth');
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await page.getByPlaceholder('john@example.com').fill(email);
    await page.getByPlaceholder('••••••••').fill('correct horse battery staple 1');
    await page.getByRole('button', { name: /^Sign Up/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });

    await page.goto('/auth');
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await page.getByPlaceholder('john@example.com').fill(email);
    await page.getByPlaceholder('••••••••').fill('a different password entirely 2');
    await page.getByRole('button', { name: /^Sign Up/ }).click();
    await expect(page).toHaveURL(/\/auth/);
    // Real error copy from userapi's conflict response, not a specific brittle string.
    await expect(page.getByText(/fail|exist|taken|already|error/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('logging in with a real registered account (wrong password) shows a real 401 error', async ({ page }) => {
    const email = uniqueEmail('wrongpw');
    await page.goto('/auth');
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await page.getByPlaceholder('john@example.com').fill(email);
    await page.getByPlaceholder('••••••••').fill('the real correct password 1');
    await page.getByRole('button', { name: /^Sign Up/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });

    await page.goto('/auth');
    await page.getByPlaceholder('john@example.com').fill(email);
    await page.getByPlaceholder('••••••••').fill('definitely the wrong password');
    await page.getByRole('button', { name: /^Sign In/ }).click();
    await expect(page).toHaveURL(/\/auth/);
    await expect(page.getByText(/./).filter({ hasText: /fail|invalid|incorrect|unauthorized|credential/i }).first()).toBeVisible({ timeout: 10000 });
  });

  test('logging in with a nonexistent account surfaces a real error without crashing', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/auth');
    await page.getByPlaceholder('john@example.com').fill(uniqueEmail('nonexistent'));
    await page.getByPlaceholder('••••••••').fill('whatever password 1');
    await page.getByRole('button', { name: /^Sign In/ }).click();
    await expect(page).toHaveURL(/\/auth/);
    await expect(page.getByText(/fail|invalid|incorrect|unauthorized|credential/i).first()).toBeVisible({ timeout: 10000 });
    expect(errors).toEqual([]);
  });

  test('Web3 wallet button is present; clicking it without an injected wallet fails gracefully', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/auth');
    const walletButton = page.getByRole('button', { name: /Continue with Web3 Wallet/ });
    await expect(walletButton).toBeVisible();
    await walletButton.click();
    // No window.ethereum in a plain Playwright Chromium context — connectWallet()
    // (src/context/DashboardContext.tsx) should addToast an error and stay put,
    // not navigate to /dashboard with a fake wallet session.
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/auth/);
    expect(errors).toEqual([]);
  });

  test('screenshot confirms final rendered state of the Sign In view', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/auth');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/auth.png', fullPage: true });
  });
});
