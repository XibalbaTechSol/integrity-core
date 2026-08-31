import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

const SHIELD_BACKEND = process.env.SHIELD_BACKEND_URL || 'http://127.0.0.1:8765';
const ADMIN_TOKEN = process.env.SHIELD_BACKEND_TOKEN || 'dev-shield-admin';
const TENANT = `browser-e2e-${process.pid}`;

test.describe('/shield (Shield fleet dashboard)', () => {
  test('renders the honest empty-fleet state without browser errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await expect(page.getByText('Xibalba Shield')).toBeVisible();
    await expect(page.getByText('Fleet tenant')).toBeVisible();
    await expect(page.getByText('ENROLLED DEVICES')).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map((e) => e.message).join('; ')}`).toEqual([]);
  });

  test('renders real enrolled-device and health data from Shield backend', async ({ page, request }) => {
    const seed = await request.post(`${SHIELD_BACKEND}/api/shield/demo/seed`, {
      headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
      data: { tenant_id: TENANT },
    });
    expect(seed.ok(), await seed.text()).toBeTruthy();

    const errors = collectPageErrors(page);
    await page.goto('/shield');
    await page.getByPlaceholder('tenant id').fill(TENANT);
    await page.getByRole('button', { name: 'Refresh' }).click();

    await expect(page.getByRole('cell', { name: 'demo-linux-001' })).toBeVisible();
    await expect(page.getByText('Trust & evidence status')).toBeVisible();
    await expect(page.getByText('Evidence graph')).toBeVisible();
    await expect(page.getByText('DENIED / CONTAINED')).toBeVisible();
    await expect(page.getByText('Backend enrolled')).toBeVisible();
    await expect(page.getByText('DID not verified')).toBeVisible();
    await expect(page.getByText('Evidence export not_checked')).toBeVisible();
    await expect(page.getByText('Oracle readback blocked_until_rpc_credentials')).toBeVisible();
    await expect(page.getByText('Endpoint posture unknown')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Policy hash' })).toBeVisible();
    expect(errors, `Uncaught errors: ${errors.map((e) => e.message).join('; ')}`).toEqual([]);
  });
});
