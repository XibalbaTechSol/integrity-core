import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('Wiki page rendering', () => {
  test('renders canonical markdown tables as navigable HTML tables', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/wiki?page=queries%2Fgas-tracking');
    await page.waitForLoadState('networkidle');

    const table = page.locator('article table').first();
    await expect(table).toBeVisible();
    await expect(table.locator('th')).toContainText(['Action', 'Count', 'Avg Gas Used', 'Avg Cost (wei)']);
    await expect(table.locator('td')).toContainText(['deploy_sovereign_agent']);
    expect(errors, `Uncaught errors on /wiki gas table: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });


  test('renders an ordered comprehensive protocol TOC with functional links', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');

    const toc = page.getByRole('navigation', { name: 'Protocol wiki table of contents' });
    await expect(toc).toBeVisible();
    await expect(toc.locator('.wiki-toc-section-title')).toContainText([
      '00Start Here',
      '01Identity & Agent Foundation',
      '02Trust, Scoring & Telemetry',
      '03Commitments & Cryptography',
      '04Compliance, Governance & Markets',
      '05Implementation Packages',
      '06Build, Test & Operate',
      '07Roadmap & Research',
    ]);
    await expect(toc).toContainText('Ecosystem Dependencies');
    await expect(toc).toContainText('Smart Contract Development');
    await expect(toc).toContainText('Multi-Domain Guardrails Design');

    await toc.getByRole('button', { name: 'Telemetry Ingestion Pipeline', exact: true }).click();
    await expect(page.locator('article h1')).toHaveText('Telemetry Ingestion Pipeline');
    await expect(page).toHaveURL(/page=concepts%2Ftelemetry-ingestion/);

    await expect(toc.getByRole('button', { name: 'Oracle ingestion pipeline' })).toBeVisible();
    await toc.getByRole('button', { name: 'Oracle ingestion pipeline' }).click();
    await expect(page).toHaveURL(/#.*oracle-ingestion-pipeline/);

    expect(errors, `Uncaught errors on /wiki protocol TOC: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('links the Xibalba Solutions logo to the landing page', async ({ page }) => {
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');

    const logo = page.getByRole('link', { name: 'Go to Xibalba Solutions landing page' });
    await expect(logo).toBeVisible();
    await expect(logo).toHaveAttribute('href', '/');
  });

  test('docks mobile search at the bottom without widening the page', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto('/wiki');
    await page.waitForLoadState('networkidle');

    const search = page.locator('.wiki-search-trigger');
    await expect(search).toBeVisible();
    const box = await search.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThan(780);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
    expect(errors, `Uncaught errors on mobile /wiki: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });
});
