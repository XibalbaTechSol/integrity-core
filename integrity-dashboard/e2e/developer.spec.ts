import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// DeveloperPage (src/pages/DeveloperPage.tsx, route "/developer") has three sub-tabs:
// IDE/Smart Contracts (FactoryPanel — a full in-browser IDE with file explorer, editor,
// AI copilot), Trace Analysis (TraceAnalysisPanel — real oracle.getTraceTree data), and
// Sandbox Console (SandboxConsole — client-side AIS simulation). No route/fetch mocking.

test.describe('/developer (DeveloperPage)', () => {
  test('loads with no uncaught JS errors, defaults to the IDE tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/developer');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Explorer')).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('IDE tab: file explorer, code editor, and AI copilot input all render', async ({ page }) => {
    await page.goto('/developer');
    await expect(page.getByText('Explorer')).toBeVisible();
    await expect(page.getByPlaceholder(/AI Contract Copilot/)).toBeVisible();
    // The code editor renders highlighted source as HTML — a real file's content should
    // include recognizable Solidity/Vyper/Noir keywords, not an empty pane.
    const editorHasContent = await page.locator('pre, code').first().innerText().catch(() => '');
    expect(editorHasContent.length).toBeGreaterThan(0);
  });

  test('switching to Trace Analysis tab renders real data or an honest empty state, never a stuck "Loading"', async ({ page }) => {
    // Regression test for a real bug: TraceAnalysisPanel collapsed "loading", "no agent
    // selected", and "agent has zero traces" into one `selectedSession === null` check,
    // permanently rendering "Loading session..." for the (common) no-telemetry-yet case
    // — indistinguishable from a hang. Fixed to track why it's null and show honest,
    // distinct copy per case.
    const errors = collectPageErrors(page);
    await page.goto('/developer');
    await page.getByRole('button', { name: /Trace Analysis/ }).click();

    const ready = page.getByText('Execution Trajectory');
    const noTraces = page.getByText('No traces recorded for this agent yet.');
    const noAgent = page.getByText('Select an agent from the sidebar to view its trace history.');
    await expect(ready.or(noTraces).or(noAgent)).toBeVisible({ timeout: 10000 });

    // Give any real "loading" transition time to settle, then assert it did NOT get
    // stuck on the literal loading copy — that copy must only ever be transient.
    await page.waitForTimeout(2000);
    await expect(page.getByText('Loading session...')).not.toBeVisible();

    if (await ready.isVisible().catch(() => false)) {
      await expect(page.getByText('Step Inspector')).toBeVisible();
    }
    expect(errors).toEqual([]);
  });

  test('switching to Sandbox Console tab renders Protocol Sandbox with no crash', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/developer');
    await page.getByRole('button', { name: /Sandbox Console/ }).click();
    await expect(page.getByRole('heading', { name: 'Protocol Sandbox' })).toBeVisible();
    await expect(page.getByText('Simulation Parameters')).toBeVisible();
    await expect(page.getByText('Real-Time AIS Result')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('tab switching is stateful — returning to IDE tab preserves the explorer', async ({ page }) => {
    await page.goto('/developer');
    await page.getByRole('button', { name: /Sandbox Console/ }).click();
    await expect(page.getByRole('heading', { name: 'Protocol Sandbox' })).toBeVisible();
    await page.getByRole('button', { name: /IDE \/ Smart Contracts/ }).click();
    await expect(page.getByText('Explorer')).toBeVisible();
  });

  test('screenshot confirms final rendered state of the IDE tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/developer');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/developer.png', fullPage: true });
  });

  test('screenshot confirms final rendered state of the Sandbox Console tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/developer');
    await page.getByRole('button', { name: /Sandbox Console/ }).click();
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/developer-sandbox.png', fullPage: true });
  });
});
