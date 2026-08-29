import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// IdentityPage (src/pages/IdentityPage.tsx, route "/identity") has no fetches of its
// own — everything comes from DashboardContext's `selectedAgent`, itself populated from
// a real `oracle.listAgents()` call (src/context/DashboardContext.tsx). No route/fetch
// mocking, per this repo's e2e convention. On a fresh local chain with no registered
// agents, `selectedAgent` is honestly null and the page must show its real empty state —
// not fabricated identity data.

test.describe('/identity (IdentityPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('renders either a real agent identity strip or the honest no-agent empty state', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    // "Decentralized ID" (exact) is unique to the identity-strip stat card — the panel
    // titled "Decentralized Identifier (DID)" below it is a substring superset and would
    // make a non-exact match ambiguous (strict-mode violation).
    const emptyState = page.getByText('Select an agent from the sidebar to manage identity');
    const identityStrip = page.getByText('Decentralized ID', { exact: true });

    // Exactly one of these must be true — never both, never neither. A page that shows
    // neither the real data view nor the real empty state has silently failed to render.
    await expect(emptyState.or(identityStrip)).toBeVisible();
  });

  test('with a real registered agent, the DID Explorer and XNS register form render (not the no-agent empty copy)', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const hasAgent = await page.getByText('Decentralized ID', { exact: true }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack — covered by the empty-state test instead');

    await expect(page.getByText('Select an agent from the sidebar to view its Decentralized Identity Document.')).not.toBeVisible();
    await expect(page.getByText('Select an agent to register a handle for it.')).not.toBeVisible();
    // DIDExplorer renders the agent's real did:integrity:… identifier, sourced live from
    // the oracle (services/oracle.ts) — not a hardcoded placeholder DID. It legitimately
    // appears multiple times, including as a <select><option> which Playwright never
    // reports as independently "visible" — scope to the rendered `.mono` display text.
    await expect(page.locator('.mono').getByText(/did:(integrity|xibalba):/).first()).toBeVisible();
  });

  test('when no agent is selected, DID/XNS-register panels show their real empty-state copy, not fake data', async ({ page }) => {
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const hasAgent = await page.getByText('Decentralized ID', { exact: true }).isVisible().catch(() => false);
    test.skip(hasAgent, 'an agent is registered on this stack — covered by the "with a selected agent" test instead');

    await expect(page.getByText('Select an agent from the sidebar to view its Decentralized Identity Document.')).toBeVisible();
    await expect(page.getByText('Select an agent to register a handle for it.')).toBeVisible();
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

  test('Sovereign Node status badges (XNS_RESOLVE/PROTO_VER/STATUS) render with readable width, not squeezed to near-zero', async ({ page }) => {
    // Regression test for a real layout bug: the DID Explorer's two-column grid
    // (src/components/ui/DIDExplorer.tsx) sized its left column off the DID string's
    // full un-truncated intrinsic width (a nowrap flex child with no min-width: 0),
    // which starved the right "Sovereign Node" column down to ~103px — collapsing
    // "STATUS" + "ANCHORED" into unreadable overlapping/adjacent text.
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');

    const hasAgent = await page.getByText('Decentralized ID', { exact: true }).isVisible().catch(() => false);
    test.skip(!hasAgent, 'no agent registered on this stack — nothing to verify layout on');

    const statusRow = page.getByText('STATUS', { exact: true }).locator('..');
    const box = await statusRow.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(180);
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/identity');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/identity.png', fullPage: true });
  });
});
