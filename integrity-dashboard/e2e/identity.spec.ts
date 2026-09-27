import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// Route "/identity" now redirects to ProtocolDashboardPage (src/pages/ProtocolDashboardPage.tsx,
// route "/dashboard"), whose default "Overview" tab renders the real Identity Management panel
// (Register/Claim + XNS Search Service) alongside a "Selected identity" panel driven entirely by
// DashboardContext's `selectedAgent`, itself populated from a real `oracle.listAgents()` call
// (src/context/DashboardContext.tsx). No route/fetch mocking, per this repo's e2e convention.
// The retired src/pages/IdentityPage.tsx and its DIDExplorer-based markup this file used to test
// no longer exist / are no longer mounted on any route — see the 2026-09-26 routing-fix handoff.

test.describe('/identity (redirects to ProtocolDashboardPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('redirects to /dashboard and highlights Command center in the sidebar', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole('link', { name: 'Command center' })).toHaveClass(/active|selected/);
  });

  test('renders either a real selected-identity panel or the honest "No agent selected" empty state', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const panel = page.locator('.selected-agent-panel');
    await expect(panel).toBeVisible();

    // Exactly one of these must be true — never both, never neither. A page that shows
    // neither the real data view nor the real empty state has silently failed to render.
    const emptyHeading = panel.getByRole('heading', { name: 'No agent selected' });
    const realHeading = panel.getByRole('heading').filter({ hasNotText: 'No agent selected' });
    await expect(emptyHeading.or(realHeading)).toBeVisible();
  });

  test('with a real selected agent, the identity panel shows its real DID (not the no-agent empty copy)', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const panel = page.locator('.selected-agent-panel');
    const hasAgent = !(await panel.getByRole('heading', { name: 'No agent selected' }).isVisible().catch(() => true));
    test.skip(!hasAgent, 'no agent selected on this stack — covered by the empty-state test instead');

    await expect(panel.getByRole('heading', { name: 'No agent selected' })).not.toBeVisible();
    // EvidenceValue renders the agent's real did:integrity:… identifier, sourced live from
    // the oracle (services/oracle.ts) — not a hardcoded placeholder DID.
    await expect(panel.getByText(/did:(integrity|xibalba):/)).toBeVisible();
  });

  test('when no agent is selected, the identity panel shows its real empty-state copy, not fake data', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const panel = page.locator('.selected-agent-panel');
    const hasAgent = !(await panel.getByRole('heading', { name: 'No agent selected' }).isVisible().catch(() => true));
    test.skip(hasAgent, 'an agent is selected on this stack — covered by the "with a selected agent" test instead');

    await expect(panel.getByRole('heading', { name: 'No agent selected' })).toBeVisible();
    // The legacy on-chain "Register an XNS Handle" panel was removed (67d3f53): handle
    // claims go through the Oracle-local directory in the XNS Search Service panel instead.
    await expect(page.getByText('Register an XNS Handle')).toHaveCount(0);
  });

  test('XNS Search Service panel and Identity Management actions are always present regardless of agent selection', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('XNS Search Service')).toBeVisible();
    await expect(page.getByRole('button', { name: /Register New/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Claim Existing/ })).toBeVisible();
  });

  test('Register New opens RegisterAgentModal, closes without crashing', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /Register New/ }).click();
    const dialog = page.locator('.modal, [role="dialog"]').first();
    await expect(dialog).toBeVisible();
    // Close via Escape or a visible close control — whichever the modal actually exposes.
    const closeButton = dialog.getByRole('button', { name: /close/i }).first();
    if (await closeButton.isVisible().catch(() => false)) {
      await closeButton.click();
    } else {
      await page.keyboard.press('Escape');
    }
    expect(errors).toEqual([]);
  });

  test('registration UI can target the existing Shield DID before wallet signing', async ({ page }) => {
    const errors = collectPageErrors(page);
    const shieldDid = 'did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4';
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /Register New/ }).click();

    const dialog = page.getByRole('dialog', { name: 'Register agent on-chain' });
    await expect(dialog).toBeVisible();
    // Default (core-identity, no bond) registration copy — the modal's `full` checkbox is
    // unchecked by default; provisioning the 100 ITK bond is opt-in, not automatic.
    await expect(dialog.getByText(/Registers identity \+ anchored memory by default/)).toBeVisible();
    await expect(dialog.getByText(/progress survives a browser or workstation restart/)).toBeVisible();
    const didInput = dialog.locator('#ra-did');
    await expect(didInput).toHaveValue(/^did:integrity:/);
    await didInput.fill(shieldDid);
    await expect(didInput).toHaveValue(shieldDid);
    // No wallet is connected in this journey, so the only available action is the
    // explicit connect step; no chain transaction can be submitted accidentally. The
    // on-chain step list (including "Deploy SovereignAgent") only renders after a
    // wallet is connected.
    await expect(dialog.getByRole('button', { name: /Connect a Base Sepolia wallet/ })).toBeVisible();
    await expect(dialog.getByText('Deploy SovereignAgent')).not.toBeVisible();
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/registration-shield-did.png', fullPage: true });
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/identity.png', fullPage: true });
  });
});
