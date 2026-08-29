import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// ShieldPage (src/pages/ShieldPage.tsx, route "/shield") is a self-contained "Real-Time
// Defensive Intelligence Simulator" for Xibalba Shield — the AI agent/device security
// platform. It's a standalone interactive demo: clicking an attack card spawns a
// simulated 5-step detection/containment pipeline. It calls a backend at
// http://localhost:5000 that does not exist anywhere in this codebase or its sibling
// repos (confirmed: no service in this repo or xibalba-shield listens on :5000) — every
// fetch call has an explicit try/catch fallback to synthetic data, so "no backend
// reachable" is the ALWAYS-real, by-design state here, not a mocked one.
//
// This supersedes the old e2e/shield.spec.ts, which tested a completely different
// oracle/bcc_middleware-backed UI ("Shadow AI discovery", "Clinical allowlist") that no
// current route renders — confirmed via git log that ShieldPage.tsx, the old spec, and
// orphaned real-Shield-backend client code (services/shieldBackend.ts,
// components/ShieldEvidenceGraph.tsx, unused by any page) all landed in the same
// integration-reconciliation commit without being reconciled with each other. Per
// explicit product direction, this file tests the live attack-simulator page — wiring up
// the real Shield backend integration is separate, out-of-scope feature work.

test.describe('/shield (ShieldPage)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('header, subtitle, and all 10 attack cards render', async ({ page }) => {
    await page.goto('/shield');
    await expect(page.getByRole('heading', { name: /Xibalba Shield/ })).toBeVisible();
    await expect(page.getByText('Real-Time Defensive Intelligence Simulator')).toBeVisible();

    const attacks = [
      '1. Reverse Shell', '2. Data Exfiltration', '3. Privilege Escalation',
      '4. Ransomware', '5. Cryptomining', '6. Shadow AI Spawn',
      '7. SSH Key Theft', '8. Network Beaconing', '9. Log Wiping', '10. Container Escape',
    ];
    for (const label of attacks) {
      await expect(page.getByRole('heading', { name: label })).toBeVisible();
    }
  });

  test('all 5 pipeline steps render in their initial "Awaiting execution" state', async ({ page }) => {
    await page.goto('/shield');
    const steps = [
      'User Space Execution', 'Shield eBPF Sensor', 'Xibalba Security SLM (Qwen 0.5B)',
      'Shield Action Broker', 'OS Verification',
    ];
    for (const title of steps) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
    }
    await expect(page.getByText('Awaiting execution...')).toHaveCount(5);
  });

  test('triggering an attack drives the real (backend-absent) fallback pipeline through to a CONTAIN verdict', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.getByRole('heading', { name: '1. Reverse Shell' }).click();

    // Step 1: a real spawned-process line appears (synthetic fallback PID, since :5000
    // is unreachable — that fallback path is exactly what's under test here).
    const step1Terminal = page.getByText('User Space Execution').locator('../..').locator('.mini-terminal');
    await expect(step1Terminal).toContainText('$', { timeout: 5000 });
    await expect(step1Terminal).toContainText('Process assigned PID');

    // Step 3 (SLM inference) resolves to the fallback's fixed CONTAIN verdict.
    const step3Terminal = page.getByText('Xibalba Security SLM').locator('../..').locator('.mini-terminal');
    await expect(step3Terminal).toContainText('CONTAIN', { timeout: 5000 });

    // Step 4 (Action Broker) shows the real kill-process mitigation code for CONTAIN.
    const step4Terminal = page.getByText('Shield Action Broker').locator('../..').locator('.mini-terminal');
    await expect(step4Terminal).toContainText('SIGKILL', { timeout: 5000 });

    // Step 5 (OS Verification) resolves — the fallback statusData.running is always
    // false, so the "process is dead" branch is the real, deterministic outcome here.
    const step5Terminal = page.getByText('OS Verification').locator('../..').locator('.mini-terminal');
    await expect(step5Terminal).toContainText('dead', { timeout: 5000 });

    expect(errors).toEqual([]);
  });

  test('re-triggering a second attack resets all 5 terminals before replaying the pipeline', async ({ page }) => {
    await page.goto('/shield');
    await page.getByRole('heading', { name: '1. Reverse Shell' }).click();
    const step4Terminal = page.getByText('Shield Action Broker').locator('../..').locator('.mini-terminal');
    await expect(step4Terminal).toContainText('SIGKILL', { timeout: 5000 });

    await page.getByRole('heading', { name: '5. Cryptomining' }).click();
    // Immediately after the click, steps should be back to "Spawning process..." /
    // reset, not still showing the previous attack's stale SIGKILL output forever.
    const step1Terminal = page.getByText('User Space Execution').locator('../..').locator('.mini-terminal');
    await expect(step1Terminal).toContainText('Spawning process', { timeout: 2000 });
  });

  test('screenshot confirms final rendered state after an attack completes', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.getByRole('heading', { name: '6. Shadow AI Spawn' }).click();
    const step5Terminal = page.getByText('OS Verification').locator('../..').locator('.mini-terminal');
    await expect(step5Terminal).toContainText('dead', { timeout: 5000 });
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/shield.png', fullPage: true });
  });
});
