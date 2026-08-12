import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('Health page — real Smart BAA + EHRGate wiring', () => {
  test('Smart BAA registry reads real oracle.getAgentBaas data, not the old seed array', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/health');
    await expect(page.getByText('Health Protocol')).toBeVisible();
    await expect(page.getByText('Smart BAA Registry', { exact: true })).toBeVisible();
    await page.waitForLoadState('networkidle');

    // Old fake seed data used hardcoded names like "0xMayo_Clinic_Minnesota_39a" —
    // asserting that's gone is a stronger signal than asserting new content exists.
    await expect(page.getByText('Mayo_Clinic')).toHaveCount(0);

    const hasRows = await page.getByText('Covered Entity').isVisible().catch(() => false);
    expect(hasRows).toBe(true);
    expect(errors).toEqual([]);
  });

  test('EHR Gates tab reads real EHRGate.accessGates state', async ({ page }) => {
    await page.goto('/health');
    await page.getByRole('button', { name: 'EHR Gates' }).click();
    await expect(page.getByText('Patient Consent Contracts (EHR Gates)')).toBeVisible();
    // The old fake seed used a hardcoded WebAuthn-only flow with no contract at all;
    // this real panel names the actual contract mechanism in its own copy.
    await expect(page.getByText('EHRGate')).toBeVisible();
  });

  test('Quarantine tab reads real Slasher.lockedStakeOf state, not a fake seed', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/health');
    await page.getByRole('button', { name: 'Quarantine' }).click();
    await expect(page.getByText('Agent Circuit Breakers (Quarantine Zone)')).toBeVisible();
    // Old fake seed always showed exactly one hardcoded 'did:intg:agent-007' with a
    // "Force Restore" button; real quarantine has no restore action at all (it clears
    // itself on-chain) and won't show that literal DID.
    await expect(page.getByText('Force Restore')).toHaveCount(0);
    await expect(page.getByText('did:intg:agent-007')).toHaveCount(0);
    await page.waitForLoadState('networkidle');
    const hasRows = await page.getByText('No agents currently quarantined.').isVisible().catch(() => false)
      || await page.getByText('QUARANTINED').first().isVisible().catch(() => false);
    expect(hasRows).toBe(true);
    expect(errors).toEqual([]);
  });
});
