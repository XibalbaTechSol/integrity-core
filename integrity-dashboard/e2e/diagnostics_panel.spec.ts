import { test, expect } from '@playwright/test';

test.describe('DiagnosticsPanel E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock MetaMask
    await page.addInitScript(() => {
      (window as any).ethereum = {
        isMetaMask: true,
        request: async (args: any) => {
          if (args.method === 'eth_requestAccounts' || args.method === 'eth_accounts') {
            return ['0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556'];
          }
          return null;
        },
        on: () => {},
        removeListener: () => {},
      };
    });

    // Go to main dashboard route
    await page.goto('/integrity/#/integrity');
    await page.waitForTimeout(2000);
    
    // Click the Cognition tab to load CognitionPage
    await page.locator('a, button, .tab-btn', { hasText: 'Cognition' }).first().click();
    await page.waitForTimeout(2000);
  });

  test('should display diagnostics panel content', async ({ page }) => {
    // Verify Diagnostics title is visible
    const title = page.locator('.panel-title', { hasText: 'Agent Diagnostics' }).first();
    await expect(title).toBeVisible();

    // Verify main components are present
    await expect(page.getByText('System Diagnostics Console')).toBeVisible();
    await expect(page.getByText('Live SDK Evaluation Benchmarks')).toBeVisible();
    await expect(page.getByText('Forensic Provenance Explorer')).toBeVisible();
    await expect(page.getByText('Integrity Hash Reconstruction Tracker')).toBeVisible();
  });

  test('should allow filtering log output in console', async ({ page }) => {
    const filterInput = page.getByPlaceholder('Filter logs...');
    await expect(filterInput).toBeVisible();

    // Type a filter search term
    await filterInput.fill('OTel');
    // Verify filtered console shows matching text and hides non-matching
    await expect(page.getByText('Initializing OTel SDK')).toBeVisible();
    await expect(page.getByText('Bound to local SQLite')).not.toBeVisible();
  });

  test('should trigger diagnostic sweep simulation', async ({ page }) => {
    const sweepButton = page.getByRole('button', { name: 'Run Diagnostics Sweep' });
    await expect(sweepButton).toBeVisible();

    // Click sweep button
    await sweepButton.click();

    // Verify loading progress bar appears and sweep logs populate console
    await expect(page.getByText('Initiating manual telemetry validation sweep...')).toBeVisible();
    
    // Wait for the sweep to complete using Playwright's automatic retry polling
    await expect(page.getByText('Telemetry verification sweep completed successfully')).toBeVisible({ timeout: 15000 });
  });

  test('should calculate integrity hash dynamically in real-time', async ({ page }) => {
    // Select the latency input field specifically using testid
    const tracker = page.getByTestId('hash-input-measured-latency');
    await expect(tracker).toBeVisible();

    const initialHash = await page.locator('#state-hash').textContent();
    expect(initialHash).toBeTruthy();

    // Type a new value in latency input
    await tracker.fill('999ms');
    await page.waitForTimeout(500);

    const updatedHash = await page.locator('#state-hash').textContent();
    // Verify that the hash was updated dynamically
    expect(initialHash).not.toBe(updatedHash);
  });
});
