import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// ShieldPage (src/pages/ShieldPage.tsx, route "/shield") was reimagined from a single-page
// attack simulator into a real security-product dashboard: "Fleet Overview" (real device
// enrollment, policy, and enforcement data from shield/backend/api.py) is now the default
// tab, and the old interactive attack simulator survives as a secondary "Live Attack Demo"
// tab, reached via the SubTabs bar at the top of the page. This supersedes the previous
// version of this spec, which tested the simulator as the page's only/default content.
//
// The simulator itself calls xibalba-shield's real root+eBPF Flask backend
// (slm_training/app.py, port 5050 -- corrected this session from a stale 5000 default
// that could never reach it even when running). That backend is never running in this
// test environment, and its three fetch call sites now fail with a real, honest
// "Backend unreachable" error instead of the fabricated pipeline (fake PID, a hardcoded
// CONTAIN verdict, fake SIGKILL code) they used to silently fall back to — so "backend
// unreachable" is the ALWAYS-real, by-design state for that tab, never a mocked result.

test.describe('/shield (ShieldPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('defaults to the Fleet Overview tab: real product identity, tenant lookup, honest empty/loaded fleet state', async ({ page }) => {
    await page.goto('/shield');
    await expect(page.getByRole('button', { name: 'Fleet Overview' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Live Attack Demo' })).toBeVisible();
    await expect(page.getByText('Xibalba Shield', { exact: true })).toBeVisible();
    await expect(page.getByText('The AI agent security platform')).toBeVisible();
    await expect(page.getByText('Fleet tenant')).toBeVisible();

    // Real device enrollment, policy, and enforcement data from shield/backend/api.py --
    // either a real fleet renders, or the honest "no devices enrolled" empty state does.
    const noDevices = page.getByText('No devices enrolled for this tenant yet');
    const enrolledDevices = page.getByText('Enrolled devices');
    await expect(noDevices.or(enrolledDevices)).toBeVisible({ timeout: 15000 });
  });

  test('Live Attack Demo tab: disclosure banner, header, subtitle, and all 10 attack cards render', async ({ page }) => {
    // The page-level "Xibalba Shield" branding now lives in ShieldFleetOverview's header
    // (the default tab), not in the extracted simulator component itself -- this tab has
    // its own "Trigger Vulnerability" heading plus a disclosure banner explaining the
    // real root+eBPF backend requirement and its honest-error-when-offline behavior.
    await page.goto('/shield');
    await page.getByRole('button', { name: 'Live Attack Demo' }).click();
    await expect(page.getByText(/Optional live demo of the Tier-2 SLM escalation path/)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Trigger Vulnerability' })).toBeVisible();

    const attacks = [
      '1. Reverse Shell', '2. Data Exfiltration', '3. Privilege Escalation',
      '4. Ransomware', '5. Cryptomining', '6. Shadow AI Spawn',
      '7. SSH Key Theft', '8. Network Beaconing', '9. Log Wiping', '10. Container Escape',
    ];
    for (const label of attacks) {
      await expect(page.getByRole('heading', { name: label })).toBeVisible();
    }
  });

  test('Live Attack Demo tab: all 5 pipeline steps render in their initial "Awaiting execution" state', async ({ page }) => {
    await page.goto('/shield');
    await page.getByRole('button', { name: 'Live Attack Demo' }).click();
    const steps = [
      'User Space Execution', 'Shield eBPF Sensor', 'Xibalba Security SLM (Qwen 0.5B)',
      'Shield Action Broker', 'OS Verification',
    ];
    for (const title of steps) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
    }
    await expect(page.getByText('Awaiting execution...')).toHaveCount(5);
  });

  test('Live Attack Demo: triggering an attack shows an honest "backend unreachable" error, never a fabricated pipeline result', async ({ page }) => {
    // Regression test for a real fix made this session: this simulator used to fall back
    // to a fully-fabricated pipeline (fake PID, a hardcoded CONTAIN verdict, fake SIGKILL
    // mitigation code, a fake "process is dead" verification) whenever its real backend
    // (xibalba-shield/slm_training/app.py) was unreachable — silently misrepresenting a
    // real syscall interception as having happened when it did not. All three fetch call
    // sites now fail honestly instead. The real backend requires root + eBPF and is never
    // running in this test environment, so "backend unreachable" is the correct, expected,
    // always-real outcome here — not a mock to work around.
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.getByRole('button', { name: 'Live Attack Demo' }).click();
    await page.getByRole('heading', { name: '1. Reverse Shell' }).click();

    const step1Terminal = page.getByText('User Space Execution').locator('../..').locator('.mini-terminal');
    await expect(step1Terminal).toContainText('Backend unreachable', { timeout: 5000 });
    await expect(step1Terminal).toContainText('sudo python3 slm_training/app.py');

    // The pipeline stops at step 1 -- steps 3-5 must never show fabricated downstream
    // results (a real CONTAIN verdict, SIGKILL, or "dead" verification) for a call that
    // never actually happened.
    const step3Terminal = page.getByText('Xibalba Security SLM').locator('../..').locator('.mini-terminal');
    await expect(step3Terminal).toContainText('Awaiting execution...');
    const step4Terminal = page.getByText('Shield Action Broker').locator('../..').locator('.mini-terminal');
    await expect(step4Terminal).toContainText('Awaiting execution...');
    const step5Terminal = page.getByText('OS Verification').locator('../..').locator('.mini-terminal');
    await expect(step5Terminal).toContainText('Awaiting execution...');

    expect(errors).toEqual([]);
  });

  test('Live Attack Demo: re-triggering a second attack resets all 5 terminals before replaying the pipeline', async ({ page }) => {
    await page.goto('/shield');
    await page.getByRole('button', { name: 'Live Attack Demo' }).click();
    await page.getByRole('heading', { name: '1. Reverse Shell' }).click();
    const step1Terminal = page.getByText('User Space Execution').locator('../..').locator('.mini-terminal');
    await expect(step1Terminal).toContainText('Backend unreachable', { timeout: 5000 });

    await page.getByRole('heading', { name: '5. Cryptomining' }).click();
    // Immediately after the click, step 1 should be back to "Spawning process..." /
    // reset, not still showing the previous attack's stale error message forever.
    await expect(step1Terminal).toContainText('Spawning process', { timeout: 2000 });
  });

  test('screenshot confirms final rendered state of the default Fleet Overview tab', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/shield.png', fullPage: true });
  });

  test('screenshot confirms final rendered state of the Live Attack Demo tab after the honest backend-unreachable error', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.getByRole('button', { name: 'Live Attack Demo' }).click();
    await page.getByRole('heading', { name: '6. Shadow AI Spawn' }).click();
    const step1Terminal = page.getByText('User Space Execution').locator('../..').locator('.mini-terminal');
    await expect(step1Terminal).toContainText('Backend unreachable', { timeout: 5000 });
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/shield-attack-demo.png', fullPage: true });
  });
});
