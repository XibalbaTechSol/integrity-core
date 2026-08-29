import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// Every route the app router registers (src/App.tsx). Real backend calls throughout —
// no route mocking. A route with no registered agents/data should degrade to an honest
// empty state, not crash; that's exactly what this suite checks.
const ROUTES = [
  '/',
  '/auth',
  '/docs',
  '/privacy',
  '/terms',
  '/dashboard',
  '/identity',
  '/financials',
  '/intelligence',
  '/prediction-markets',
  '/health',
  '/shield',
  '/developer',
  '/settings',
];

for (const route of ROUTES) {
  test(`${route} loads without a JS crash`, async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors on ${route}: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });
}
