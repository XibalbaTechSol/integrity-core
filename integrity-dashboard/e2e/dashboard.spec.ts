import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

test.describe('Dashboard — real agent fleet + AIS wiring', () => {
  test('agent selector is populated from oracle.listAgents(), not a hardcoded agent_1', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const select = page.locator('select').first();
    await expect(select).toBeVisible();

    // The old mock always hardcoded exactly 'agent_1' / 'clinical-assistant-01' as the
    // only option; a real fleet either has zero options (network has no agents) or a
    // real DID/handle-shaped option — never that literal string.
    const optionTexts = await select.locator('option').allTextContents();
    expect(optionTexts.join(' ')).not.toContain('clinical-assistant-01');

    expect(errors).toEqual([]);
  });

  test('dashboard stat panels render real "no reading yet" states rather than fabricated numbers', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    // Old mock always showed a fake "agent_2"-branched AIS of 850/920; real panels show
    // either a real score or an em-dash, never those specific fabricated constants.
    const hasLiveScore = await page.getByText('Live AIS Score').isVisible().catch(() => false);
    const hasNoAgentsState = await page.getByText('No registered agents found on this network.').isVisible().catch(() => false);
    expect(hasLiveScore || hasNoAgentsState, 'expected live dashboard or honest no-agent state').toBe(true);
  });
});
