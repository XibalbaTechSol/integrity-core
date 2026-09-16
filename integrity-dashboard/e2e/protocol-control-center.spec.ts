import { test, expect } from '@playwright/test';

const protocolRoutes = ['/dashboard', '/identity', '/records', '/proofs', '/wallets', '/transactions', '/contracts', '/security', '/activity'];

for (const route of protocolRoutes) {
  test(`renders protocol control center: ${route}`, async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('nav[aria-label="Protocol navigation"]')).toBeVisible();
    await expect(page.getByText('Key material never rendered')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    expect(pageErrors).toEqual([]);
  });
}

test('never renders private key or recovery material', async ({ page }) => {
  await page.goto('/security', { waitUntil: 'domcontentloaded' });
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/i);
  expect(body).not.toMatch(/\b(seed phrase|mnemonic|raw private key|secret recovery)\b/i);
});
