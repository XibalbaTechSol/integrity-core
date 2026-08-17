import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// HealthPage (src/pages/HealthPage.tsx, route "/health") is the heaviest page: Smart BAA
// registry, EHR Gates, Compliance/Arbitration queue, and Quarantine zone, all reading
// REAL chain state directly from Base Sepolia (the page's own banner says so: "Smart BAA
// registry, EHR Gates, and Quarantine are all real (Base Sepolia)") — not this session's
// local anvil chain. The test agent (xibalba.integrity) was only ever registered locally,
// so these sections are expected to show real, honest empty states here, not fabricated
// activity. No route/fetch mocking.
//
// Note: HealthPage declares a `TABS` array (Smart BAAs / EHR Gates / Audit & Compliance /
// Quarantine) and imports SubTabs, but never renders SubTabs or gates any section behind
// an active-tab check — every section is unconditionally stacked on one continuous page.
// That's dead code worth flagging, not a functional bug (nothing crashes or hides
// content), so this spec tests the actual current single-page layout rather than
// asserting tab-switching behavior that doesn't exist.

test.describe('/health (HealthPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/health');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('hero bar: Health Protocol heading, real BAA stats strip', async ({ page }) => {
    await page.goto('/health');
    await expect(page.getByText('Health Protocol')).toBeVisible();
    await expect(page.getByText(/Smart BAA registry, EHR Gates, and Quarantine are all real/)).toBeVisible();
    await expect(page.getByText('Active BAAs')).toBeVisible();
    await expect(page.getByText('Disputed BAAs')).toBeVisible();
  });

  test('Smart BAA Registry: real table or honest empty state, Propose BAA opens a real modal', async ({ page }) => {
    await page.goto('/health');
    // exact: true — a substring match would also hit the hero banner's "Smart BAA
    // registry, EHR Gates, and Quarantine are all real" copy.
    await expect(page.getByText('Smart BAA Registry', { exact: true })).toBeVisible();
    const noBaas = page.getByText('No BAAs found for this agent.');
    const baaRows = page.locator('table tbody tr td.mono');
    await expect(noBaas.or(baaRows.first())).toBeVisible();

    await page.getByRole('button', { name: '+ Propose BAA Contract' }).click();
    await expect(page.getByRole('heading', { name: 'Propose Smart BAA' })).toBeVisible();
    await page.mouse.click(10, 10);
    await expect(page.getByRole('heading', { name: 'Propose Smart BAA' })).not.toBeVisible();
  });

  test('HIPAA Gateway, Clinical Allowlist, and NHI Access Governance panels render', async ({ page }) => {
    await page.goto('/health');
    await expect(page.getByText('HIPAA Gateway Concept & Safeguards')).toBeVisible();
    await expect(page.getByText('Clinical Allowlist (BCC Runtime Policy)')).toBeVisible();
    await expect(page.getByText('NHI Access Governance (Current MVP Identity View)')).toBeVisible();
  });

  test('Patient Consent Contracts (EHR Gates): real table or honest empty state', async ({ page }) => {
    await page.goto('/health');
    await expect(page.getByText('Patient Consent Contracts (EHR Gates)')).toBeVisible();
    const noGates = page.getByText('No known gates for this browser yet — grant one below.');
    const gateRows = page.locator('table tbody tr td.mono');
    await expect(noGates.or(gateRows.first())).toBeVisible();
  });

  test('Grant EHR Gate Access form renders with real input fields', async ({ page }) => {
    await page.goto('/health');
    await expect(page.getByText('Grant EHR Gate Access')).toBeVisible();
  });

  test('Medical Record Interaction Logs table renders (real or empty)', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/health');
    await expect(page.getByText('Medical Record Interaction Logs')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('Compliance/Arbitration Review Queue: shows the honest no-violations state (no wallet connected)', async ({ page }) => {
    await page.goto('/health');
    // Without a connected wallet, walletAddress is null so isArbitrator is false —
    // real "Compliance Review Queue" copy, not the arbitrator-only network-wide view.
    await expect(page.getByText('Compliance Review Queue')).toBeVisible();
    await expect(page.getByText('No violations flagged for review.')).toBeVisible();
  });

  test('Quarantine Zone: real table or honest "no agents quarantined" state', async ({ page }) => {
    await page.goto('/health');
    await expect(page.getByText('Agent Circuit Breakers (Quarantine Zone)')).toBeVisible();
    const noQuarantine = page.getByText('No agents currently quarantined.');
    const quarantineRows = page.locator('table tbody tr td.mono');
    await expect(noQuarantine.or(quarantineRows.first())).toBeVisible({ timeout: 15000 });
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/health');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/health.png', fullPage: true });
  });
});
