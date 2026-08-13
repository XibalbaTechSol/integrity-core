import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// WikiPage (src/pages/WikiPage.tsx, route "/wiki") reads a build-time static artifact
// (src/generated/wiki-data.json, 38 pages) — no live backend calls, so this is a purely
// client-side rendering/interaction spec. It replaces the pre-existing wiki.spec.ts (this
// file supersedes it) written under this audit's screenshot-as-truth discipline.

test.describe('/wiki (WikiPage)', () => {
  test('loads with no uncaught JS errors and shows the home article', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('article#article-top h1')).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('topbar: logo links to landing page, protocol TOC and search trigger present', async ({ page }) => {
    await page.goto('/wiki');
    await expect(page.getByRole('link', { name: 'Go to Xibalba Solutions landing page' })).toHaveAttribute('href', '/');
    await expect(page.getByRole('button', { name: /Search the protocol/ })).toBeVisible();
    await expect(page.getByText(/Last updated/)).toBeVisible();
  });

  test('protocol TOC sidebar lists numbered sections and navigates to a different page on click', async ({ page }) => {
    await page.goto('/wiki');
    const nav = page.locator('nav.wiki-master-toc');
    await expect(nav.getByText('Start Here')).toBeVisible();
    await expect(nav.getByText('Identity & Agent Foundation')).toBeVisible();

    const aisLink = nav.locator('button.wiki-page-link', { hasText: 'Agentic Integrity Score' }).first();
    // Fall back to any nav link that is not the currently-active home page, since exact
    // titles are sourced from markdown frontmatter and could legitimately change.
    const target = (await aisLink.count()) > 0
      ? aisLink
      : nav.locator('button.wiki-page-link:not(.active)').first();

    const targetTitle = (await target.innerText()).trim();
    await target.click();
    await expect(page.locator('article#article-top h1')).toHaveText(targetTitle);
    await expect(page).toHaveURL(/\/wiki\?page=/);
  });

  test('deep-links via ?page= query param load the requested article directly', async ({ page }) => {
    await page.goto('/wiki?page=concepts/ais');
    await page.waitForLoadState('networkidle');
    const activeLink = page.locator('nav.wiki-master-toc button.wiki-page-link.active');
    await expect(activeLink).toBeVisible();
    const title = await page.locator('article#article-top h1').innerText();
    expect(title.trim().length).toBeGreaterThan(0);
    await expect(activeLink).toHaveText(title.trim());
  });

  test('on-this-page TOC scrolls to a heading and marks it active', async ({ page }) => {
    // The 'home' article (16 real ##/### headings) — the class that marks heading depth
    // (`level-2`/`level-3`) lives on the wrapping `.wiki-toc-row` div, not the button
    // itself; the button only ever carries `active`.
    await page.goto('/wiki?page=home');
    await page.waitForLoadState('networkidle');
    const tocButtons = page.locator('.wiki-toc-tree .wiki-toc-row.level-2 button, .wiki-toc-tree .wiki-toc-row.level-3 button');
    await expect(tocButtons.first()).toBeVisible();
    const first = tocButtons.first();
    await first.click();
    await expect(first).toHaveClass(/active/);
    await expect(page).toHaveURL(/#/);
  });

  test('command palette search (click trigger) filters results and navigates on selection', async ({ page }) => {
    await page.goto('/wiki');
    await page.getByRole('button', { name: /Search the protocol/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Search wiki' });
    await expect(dialog).toBeVisible();

    const input = dialog.locator('input');
    await input.fill('ais');
    const results = dialog.locator('.wiki-command-results button');
    await expect(results.first()).toBeVisible();
    const firstResultTitle = (await results.first().locator('strong').innerText()).trim();

    await results.first().click();
    await expect(dialog).not.toBeVisible();
    await expect(page.locator('article#article-top h1')).toHaveText(firstResultTitle);
  });

  test('command palette closes on Escape without navigating', async ({ page }) => {
    await page.goto('/wiki');
    await page.getByRole('button', { name: /Search the protocol/ }).click();
    await expect(page.getByRole('dialog', { name: 'Search wiki' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'Search wiki' })).not.toBeVisible();
  });

  test('article pagination advances to the next article in TOC order', async ({ page }) => {
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');
    const currentTitle = (await page.locator('article#article-top h1').innerText()).trim();
    const nextButton = page.locator('nav.wiki-article-pagination button.next');
    await expect(nextButton).toBeVisible();
    // The title text sits as a trailing text node after <small>Next</small> inside the
    // same <span> — read it via the DOM directly rather than innerText, which renders
    // <small> on its own line and applies its CSS text-transform (uppercase), corrupting
    // a naive string match.
    const nextTitle = await nextButton.locator('span').evaluate((el) => {
      const last = el.lastChild;
      return last && last.nodeType === Node.TEXT_NODE ? (last.textContent || '').trim() : '';
    });
    expect(nextTitle.length).toBeGreaterThan(0);
    await nextButton.click();
    const newTitle = page.locator('article#article-top h1');
    await expect(newTitle).toHaveText(nextTitle);
    await expect(newTitle).not.toHaveText(currentTitle);
  });

  test('source provenance panel links to the real GitHub wiki source', async ({ page }) => {
    await page.goto('/wiki');
    const provenance = page.locator('.wiki-provenance');
    await expect(provenance.getByRole('link', { name: /integrity-core\/docs\/wiki/ })).toHaveAttribute(
      'href',
      /github\.com\/XibalbaTechSol\/integrity-core/
    );
    await expect(provenance.getByText('Snapshot generated')).toBeVisible();
  });

  test('markdown bold (**text**) renders as real <strong>, not literal asterisks', async ({ page }) => {
    // Regression test for a real bug: inlineMarkup's split regex (src/pages/WikiPage.tsx)
    // matched `\*\*[^*]+\*` (one closing asterisk) instead of `\*\*[^*]+\*\*` (two),
    // so every **bold** span in every one of the 38 wiki pages rendered as literal
    // asterisks around plain text instead of a <strong> element.
    await page.goto('/wiki?page=home');
    await page.waitForLoadState('networkidle');
    const article = page.locator('article#article-top');
    await expect(article.locator('strong').first()).toBeVisible();
    await expect(article).not.toContainText('**');
  });

  test('screenshot confirms final rendered state of the home article', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/wiki.png', fullPage: true });
  });
});
