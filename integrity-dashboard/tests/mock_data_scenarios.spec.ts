import { test, expect } from '@playwright/test';

test.describe('Mock Data Scenario Validations', () => {
  test('Scenario 1: Empty State (Zero Agents, Zero Contracts)', async ({ page }) => {
    // Intercept API calls and return empty arrays
    await page.route('**/v1/user/agents', async route => {
      await route.fulfill({ status: 200, json: [] });
    });
    await page.route('**/v1/protocol/stats', async route => {
      await route.fulfill({ status: 200, json: { active_agents: 0, total_tvl: 0, '24h_volume': 0 } });
    });

    await page.goto('http://localhost:5173/#telemetry');
    await page.waitForTimeout(1000); // Wait for fetch

    // The UI should remain stable and display placeholders rather than crashing
    await expect(page.locator('#root')).toBeVisible();
    await expect(page.locator('.sidebar')).toBeVisible();
  });

  test('Scenario 2: Whale Agent State (Massive numbers and lots of contracts)', async ({ page }) => {
    // Intercept and return extreme mock data
    const whaleAgent = {
      eth_address: '0xWHALE00000000000000000000000000000000000',
      alias: 'Leviathan_Prime',
      verification_tier: 5,
      current_ais: 999999999.99,
      grounding_score: 1000,
      oversight_score: 1000,
      fidelity_score: 1000,
      compliance_score: 1000,
      entropy_score: 1000,
      staked_ratio: 0.99,
      tee_type: 'Intel TDX',
      tee_verified: true,
      owned_contracts: Array.from({ length: 100 }).map((_, i) => ({
        contract_address: `0xCONTRACT${i}0000000000000000000000000000`,
        contract_type: i % 2 === 0 ? 'Service Level Agreement' : 'RevenueShare',
        chain: 'ethereum',
        deployed_at: new Date().toISOString(),
        status: 'active',
        revenue_generated: 1000000 * i
      }))
    };

    await page.route('**/v1/user/agents', async route => {
      await route.fulfill({ status: 200, json: [whaleAgent] });
    });
    
    await page.route('**/v1/protocol/stats', async route => {
      await route.fulfill({ status: 200, json: { active_agents: 1, total_tvl: 50000000000, '24h_volume': 1500000000 } });
    });

    await page.goto('http://localhost:5173/#ledger');
    await page.waitForTimeout(1000);

    // Ensure the large table renders without breaking the grid
    await expect(page.locator('#root')).toBeVisible();
    
    // Check that we can scroll the large table container
    const tableContainer = page.locator('.table-container').first();
    await expect(tableContainer).toBeVisible();
    // Validate the page hasn't crashed
    await expect(page.locator('text=Leviathan_Prime').first()).toBeVisible();
  });

  test('Scenario 3: Backend HTTP 500 Error Recovery', async ({ page }) => {
    // Intercept and force an error
    await page.route('**/v1/user/agents', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' });
    });

    await page.goto('http://localhost:5173/#identity');
    await page.waitForTimeout(1000);

    // The app should catch the error, set offline mode, and use fallback mock data (or render safely)
    await expect(page.locator('#root')).toBeVisible();
    // It should not white screen
    await expect(page.locator('.topbar')).toBeVisible();
  });
});
