import { test, expect } from '@playwright/test';

test.describe('Integrity Oracle Dashboard Validation (Offline Mode)', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API calls to simulate Oracle offline/empty state
    await page.route('**/v1/protocol/stats', route => route.fulfill({ status: 503 }));
    await page.route('**/v1/user/agents', route => route.fulfill({ status: 503 }));
    await page.goto('http://localhost:5173');
  });

  test('Shell and Navigation renders correctly without backend', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Integrity Command Center');
    await expect(page.getByText('DATABASE OFFLINE')).toBeVisible();
    
    // Navigation Tabs
    const tabs = [
      'Telemetry', 'Identity & DID', 'Smart Ledger', 'ZK Prover', 
      'Contract Factory', 'Credit & Loans', 'A2A Markets', 
      'Governance', 'Compliance', 'Advanced'
    ];
    
    for (const tab of tabs) {
      await expect(page.getByRole('button', { name: tab })).toBeVisible();
    }
  });

  test('Contract Factory Tab (Code Editor)', async ({ page }) => {
    await page.getByRole('button', { name: 'Contract Factory' }).click();
    await expect(page.getByText('Contract Templates')).toBeVisible();
    await expect(page.getByText('Custom Code')).toBeVisible();
    await expect(page.getByText('Smart Contract IDE')).toBeVisible();
    await expect(page.getByRole('button', { name: /Compile & Deploy/i })).toBeVisible();
  });

  test('A2A Markets Tab (Advanced Economy)', async ({ page }) => {
    await page.getByRole('button', { name: 'A2A Markets' }).click();
    await expect(page.getByText('Agent-Owned Contract Offerings')).toBeVisible();
    await expect(page.getByText('Oracle Database Offline. Cannot fetch market offers.')).toBeVisible();
  });

  test('Advanced Capabilities Tab', async ({ page }) => {
    await page.getByRole('button', { name: 'Advanced' }).click();
    await expect(page.getByText('Advanced Contract Markets')).toBeVisible();
    await expect(page.getByText('Fractional Contract Ownership')).toBeVisible();
  });
});
