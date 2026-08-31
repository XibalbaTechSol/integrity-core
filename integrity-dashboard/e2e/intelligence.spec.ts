import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// IntelligencePage (src/pages/IntelligencePage.tsx, route "/intelligence") is mostly
// client-side: 4 static KaTeX formula cards, a Radar panel driven by DashboardContext's
// selectedAgent (real oracle data), a filter toolbar, and a "custom telemetry" feature
// persisted to localStorage (`integrity_custom_telemetry`) — no dedicated backend of its
// own for that feature.

test.describe('/intelligence (IntelligencePage)', () => {
  test.beforeEach(async ({ page }) => {
    // Custom telemetry fields persist in localStorage across tests in the same browser
    // context — start each test from a clean slate so toolbar/modal assertions are
    // deterministic regardless of test order.
    await page.goto('/intelligence');
    await page.evaluate(() => localStorage.removeItem('integrity_custom_telemetry'));
  });

  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/intelligence');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('renders all five AIS formula cards with real KaTeX, not raw LaTeX text', async ({ page }) => {
    // Titles verbatim from integrity-oracle/scoring-core/src/lib.rs's real formulas --
    // the previous titles ("Stability (Entropy Control)", "Grounding (Human-in-the-Loop)",
    // "Sacrifice (Economic Commitment)") described formulas that were fabricated and never
    // matched what the oracle actually computes (see IntelligencePage.tsx's own comment on
    // the fix). "Compliance" was previously untested entirely.
    await page.goto('/intelligence');
    const titles = ['Stability (Entropy)', 'Grounding (Human Oversight)', 'Sacrifice (Compute Commitment)', 'Compliance', 'Overall Agent Integrity Score'];
    for (const title of titles) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
    }
    // At minimum, one block formula per card (5) plus the inline math spans in each
    // card's description — exact count is fragile against copy changes, so assert a
    // floor and that nothing failed to parse, rather than a brittle exact number.
    const katexBlocks = page.locator('.katex');
    expect(await katexBlocks.count()).toBeGreaterThanOrEqual(titles.length);
    await expect(page.locator('.katex-error')).toHaveCount(0);
  });

  test('formula boxes show the formula from its start, unclipped, without needing to scroll first', async ({ page }) => {
    // Regression test for a real bug: FormulaCard's formula box used `overflow: hidden`
    // with `justify-content: center`, so any formula wider than the box was clipped on
    // BOTH edges — "AIS = (...)" rendered as the unreadable "[S = (...)" with the leading
    // "A"/"I" sheared off. Switching to overflowX: auto alone wasn't sufficient either:
    // a centered flex item inside an auto-overflow container starts pre-scrolled to the
    // midpoint, so the default (unscrolled) view was still clipped on both sides. The fix
    // is justify-content: flex-start, so the formula's beginning is flush left and always
    // fully visible without user interaction — assert that directly via scrollLeft.
    //
    // Selects the formula box via its own `.thin-scrollbar-x` class (added along with the
    // slim custom scrollbar styling) rather than ".katex.first()" — the Overall AIS card's
    // description contains several *inline* KaTeX spans (w_E, w_G, ...) that appear before
    // the block formula in DOM order, so ".katex.first()" resolved to one of those instead
    // of the block formula box.
    await page.goto('/intelligence');
    const overallCard = page.getByRole('heading', { name: 'Overall Agent Integrity Score' }).locator('../..');
    const overallFormulaBox = overallCard.locator('.thin-scrollbar-x');
    await expect(overallFormulaBox).toBeVisible();
    const scrollLeft = await overallFormulaBox.evaluate((el) => el.scrollLeft);
    expect(scrollLeft).toBe(0);
    // With scrollLeft at 0 and flex-start alignment, the formula's own first glyph sits
    // at (or very near) the box's left inner edge — not shifted inward by centering.
    const formulaLeft = await overallFormulaBox.evaluate((el) => el.querySelector('.katex')!.getBoundingClientRect().left);
    const boxLeft = await overallFormulaBox.evaluate((el) => el.getBoundingClientRect().left);
    expect(formulaLeft - boxLeft).toBeLessThan(20);
  });

  test('radar panel shows the selected agent\'s real identity and AIS, or is absent with no agent', async ({ page }) => {
    await page.goto('/intelligence');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByText('Cryptographic Address').isVisible().catch(() => false);
    if (hasAgent) {
      // Scoped to the radar Panel itself (by its own heading, "<agent> // Multi-Dimensional
      // Integrity Radar") -- the page also has a live "AIS Mechanics Explorer" simulator
      // whose own "Resulting AIS" readout renders an unrelated "X / 1000" span, which
      // otherwise makes an unscoped page-wide search match 2 elements (strict-mode
      // violation).
      const radarPanel = page.getByText(/Multi-Dimensional Integrity Radar/).locator('../..');
      await expect(radarPanel.getByText('Agent Integrity Score (AIS)', { exact: true })).toBeVisible();
      await expect(radarPanel.getByText(/\/ 1000|No reading yet/)).toBeVisible();
    } else {
      await expect(page.getByText(/Multi-Dimensional Integrity Radar/)).toHaveCount(0);
    }
  });

  test('filter toolbar toggles the Telemetry Stream panel on and off', async ({ page }) => {
    await page.goto('/intelligence');
    await expect(page.locator('canvas, svg').first()).toBeVisible().catch(() => {});
    const telemetryToggle = page.getByRole('button', { name: /Telemetry Stream/ });
    await expect(telemetryToggle).toContainText('✓');

    await telemetryToggle.click();
    await expect(telemetryToggle).not.toContainText('✓');

    await telemetryToggle.click();
    await expect(telemetryToggle).toContainText('✓');
  });

  test('filter toolbar toggles the Radar panel on and off (when an agent is present)', async ({ page }) => {
    await page.goto('/intelligence');
    await page.waitForLoadState('networkidle');
    const hasAgent = await page.getByText('Cryptographic Address').isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent selected — radar panel never renders regardless of toggle');

    const radarToggle = page.getByRole('button', { name: /Radar Graphs/ });
    await expect(radarToggle).toContainText('✓');
    await expect(page.getByText('Cryptographic Address')).toBeVisible();

    await radarToggle.click();
    await expect(page.getByText('Cryptographic Address')).not.toBeVisible();

    await radarToggle.click();
    await expect(page.getByText('Cryptographic Address')).toBeVisible();
  });

  test('Add Custom Telemetry modal: cancel discards without adding a filter chip', async ({ page }) => {
    await page.goto('/intelligence');
    await page.getByRole('button', { name: '+ Add Custom Telemetry' }).click();
    const modal = page.getByRole('heading', { name: 'Add Custom Telemetry' }).locator('..');
    await expect(modal).toBeVisible();
    await modal.getByPlaceholder('e.g. Enclave Temperature').fill('Enclave Temp');
    await modal.getByPlaceholder(/42.5|99.8/).fill('55C');
    await modal.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'Add Custom Telemetry' })).not.toBeVisible();
    await expect(page.getByRole('button', { name: /Enclave Temp/ })).toHaveCount(0);
  });

  test('Add Custom Telemetry: Add Stream is disabled until both fields are filled, then creates a real toggleable chip persisted to localStorage', async ({ page }) => {
    await page.goto('/intelligence');
    await page.getByRole('button', { name: '+ Add Custom Telemetry' }).click();
    const addButton = page.getByRole('button', { name: 'Add Stream' });
    await expect(addButton).toBeDisabled();

    await page.getByPlaceholder('e.g. Enclave Temperature').fill('Enclave Temp');
    await expect(addButton).toBeDisabled();
    await page.getByPlaceholder(/42.5|99.8/).fill('55C');
    await expect(addButton).toBeEnabled();

    await addButton.click();
    await expect(page.getByRole('heading', { name: 'Add Custom Telemetry' })).not.toBeVisible();

    const chip = page.getByRole('button', { name: /Enclave Temp/ });
    await expect(chip).toBeVisible();
    await expect(chip).toContainText('✓');

    await expect.poll(async () => {
      const raw = await page.evaluate(() => localStorage.getItem('integrity_custom_telemetry'));
      return raw ? JSON.parse(raw).map((f: any) => f.label) : [];
    }).toContain('Enclave Temp');

    await chip.click();
    await expect(chip).not.toContainText('✓');
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/intelligence');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/intelligence.png', fullPage: true });
  });
});
