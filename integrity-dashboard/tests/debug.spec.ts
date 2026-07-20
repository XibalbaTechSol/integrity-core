import { test } from '@playwright/test';

test('debug browser errors', async ({ page }) => {
  page.on('pageerror', exception => {
    console.log(`Uncaught exception: "${exception}"`);
  });
  page.on('console', msg => {
    if (msg.type() === 'error') console.log(`Console error: "${msg.text()}"`);
  });
  await page.goto('http://localhost:5173');
  await page.waitForTimeout(2000);
});
