import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// LandingPage (src/LandingPage.tsx, route "/") is fully static marketing content — no
// oracle/userapi/chain calls, only `useSettings()` for theme. That makes it the cheapest
// page in the app to lock down with a strict spec: every assertion here should be about
// real rendered DOM, not a fallback/empty state, since there is no "no data yet" case.

test.describe('/ (LandingPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('header nav renders brand, section anchors, and top-level links', async ({ page }) => {
    await page.goto('/');
    const header = page.locator('header');
    await expect(header).toBeVisible();
    await expect(header.getByText('Integrity Protocol', { exact: true })).toBeVisible();

    // In-page section anchors
    await expect(header.getByRole('link', { name: 'The Problem' })).toHaveAttribute('href', '#problem');
    await expect(header.getByRole('link', { name: 'AIS Metrics' })).toHaveAttribute('href', '#ais');
    await expect(header.getByRole('link', { name: 'Market Verticals' })).toHaveAttribute('href', '#verticals');
    await expect(header.getByRole('link', { name: 'FAQ' })).toHaveAttribute('href', '#faq');

    // Router links
    await expect(header.getByRole('link', { name: 'Wiki' })).toHaveAttribute('href', '/wiki');
    await expect(header.getByRole('link', { name: 'GitHub' })).toHaveAttribute('href', 'https://github.com/xibalbatechsol');
    await expect(header.getByRole('link', { name: /Launch MVP/ })).toHaveAttribute('href', '/auth');
  });

  test('hero section states the value proposition and links to /auth', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      "we mathematically bind it to liability"
    );
    const heroCta = page.getByRole('link', { name: 'Launch MVP Dashboard' }).first();
    await expect(heroCta).toBeVisible();
    await expect(heroCta).toHaveAttribute('href', '/auth');
  });

  test('AIS formula renders as real KaTeX markup, not raw LaTeX text', async ({ page }) => {
    await page.goto('/');
    await page.locator('#ais').scrollIntoViewIfNeeded();
    const formulaBlock = page.locator('#ais .katex');
    await expect(formulaBlock).toBeVisible();
    // KaTeX always emits an accessibility-only MathML annotation containing the raw
    // TeX source (`.katex-mathml`, visually hidden via CSS clip) alongside the visible
    // HTML rendering — that's normal, not a rendering failure. What must never happen
    // is a katex-error span (react-katex's failure mode) or the raw \text{} source
    // being visible to the naked eye. Assert both.
    await expect(page.locator('#ais .katex-error')).toHaveCount(0);
    await expect(page.locator('#ais .katex-html')).not.toContainText('\\text{AIS}');
  });

  test('market vertical cards deep-link to their real prototype routes', async ({ page }) => {
    await page.goto('/');
    await page.locator('#verticals').scrollIntoViewIfNeeded();
    await expect(page.getByRole('link', { name: 'View Shield Prototype' })).toHaveAttribute('href', '/shield');
    await expect(page.getByRole('link', { name: 'View Health Prototype' })).toHaveAttribute('href', '/health');
    await expect(page.getByRole('link', { name: 'View Finance Prototype' })).toHaveAttribute('href', '/financials');
  });

  test('FAQ accordion expands and collapses answer text on click', async ({ page }) => {
    await page.goto('/');
    await page.locator('#faq').scrollIntoViewIfNeeded();
    const question = page.getByText('What happens during a slashing event?');
    const answer = page.getByText(/burns a portion of the agent's staked/);

    await expect(answer).not.toBeVisible();
    await question.click();
    await expect(answer).toBeVisible();
    await question.click();
    await expect(answer).not.toBeVisible();
  });

  test('footer links to wiki, privacy, and terms routes', async ({ page }) => {
    await page.goto('/');
    const footer = page.locator('footer');
    await footer.scrollIntoViewIfNeeded();
    await expect(footer.getByRole('link', { name: 'Integrity Wiki' })).toHaveAttribute('href', '/wiki');
    await expect(footer.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy');
    await expect(footer.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '/terms');
  });

  test('full-page screenshot captures hero, AIS formula, and verticals in final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Every section is a framer-motion `whileInView` (viewport: {once: true}) reveal,
    // driven by IntersectionObserver — it needs each section to actually cross the
    // viewport with real rendered frames in between, not just a scrollTop mutation.
    // A tight `window.scrollBy` + `setTimeout` loop outruns the observer and leaves
    // below-the-fold sections stuck at opacity:0 (reproduced and confirmed — see
    // e2e/landing.spec.ts history). scrollIntoViewIfNeeded per section, each followed
    // by a real wait, mirrors how a user's scroll actually triggers the reveal.
    const sectionIds = ['#problem', '#ais', '#verticals', '#faq', '#contact', '#specification'];
    for (const id of sectionIds) {
      await page.locator(id).scrollIntoViewIfNeeded();
      await page.waitForTimeout(250);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/landing.png', fullPage: true });
  });
});
