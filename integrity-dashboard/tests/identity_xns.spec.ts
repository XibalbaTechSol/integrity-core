import { test, expect } from '@playwright/test';

test.describe('Identity Panel & XNS Search Service', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API calls to simulate Oracle offline/empty state
    await page.route('**/v1/protocol/stats', route => route.fulfill({ status: 503 }));
    await page.route('**/v1/user/agents', route => route.fulfill({ status: 503 }));
    await page.goto('http://localhost:5173');
  });

  test('Identity & DID Tab renders XNS Search Service', async ({ page }) => {
    // Click on Identity & DID tab
    await page.getByRole('button', { name: 'Identity & DID' }).click();
    
    // Verify Identity Panel title
    await expect(page.getByText('Decentralized Identifier (DID)')).toBeVisible();
    
    // Verify XNS Search Service section
    await expect(page.getByText('XNS Search Service')).toBeVisible();
    await expect(page.getByPlaceholder('Search handle (e.g. xibalba.intg) or DID...')).toBeVisible();
    
    // Verify Register New Agent section
    await expect(page.getByText('Register New Agent')).toBeVisible();
  });

  test('XNS Search input works', async ({ page }) => {
    await page.getByRole('button', { name: 'Identity & DID' }).click();
    
    const searchInput = page.getByPlaceholder('Search handle (e.g. xibalba.intg) or DID...');
    await searchInput.fill('xibalba.intg');
    
    // Mock the search result
    await page.route('**/v1/identity/resolve?xns=xibalba.intg', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        alias: 'Xibalba Genesis',
        eth_address: '0x67ba5d723e1f5517aff7eb980e2f73a9e17ad556',
        current_ais: 990,
        verification_tier: 3,
        trust_level: 'AAA',
        xns_handle: 'xibalba.intg'
      })
    }));
    
    // Press Enter to search
    await searchInput.press('Enter');
    
    // Verify results appear
    await expect(page.getByText('Xibalba Genesis')).toBeVisible();
    await expect(page.getByText('990')).toBeVisible();
    await expect(page.getByText('Tier 3')).toBeVisible();
    await expect(page.getByText('AAA')).toBeVisible();
  });
});
