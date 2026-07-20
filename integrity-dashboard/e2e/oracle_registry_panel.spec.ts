import { test, expect } from '@playwright/test';

test.describe('OracleRegistryPanel', () => {
  test('should display oracle nodes and allow registration', async ({ page }) => {
    await page.goto('/integrity/');
    
    // Navigate to the Oracle Registry tab
    const accordionBtn = page.locator('.tab-nav-accordion > button');
    if (await accordionBtn.isVisible()) {
      await accordionBtn.click();
      await page.waitForSelector('.tab-nav-accordion > div', { state: 'visible' });
    }
    // We renamed the tab to "World Awareness: Oracle Registry" or similar? Let's check.
    // Actually the button text is exactly the label in TabId.
    // Let's assume it has text "World Awareness". 
    // I should check GlobalNav.tsx or App.tsx but let's try 'Oracle Registry' first.
    await page.locator('button.tab-btn').filter({ hasText: 'Oracle Registry' }).first().click();
    
    // Verify sections exist
    await expect(page.getByText('Registered Oracles', { exact: false })).toBeVisible();
    await expect(page.getByText('Oracle Node Configuration', { exact: false })).toBeVisible();
    
    // Verify Create Node form
    await expect(page.locator('#oracle-alias')).toBeVisible();
    await expect(page.locator('#oracle-uri')).toBeVisible();
    await expect(page.locator('#oracle-stake')).toBeVisible();
    
    // Create a new node
    await page.fill('#oracle-alias', 'Playwright API');
    await page.fill('#oracle-uri', 'https://playwright.dev/api');
    await page.fill('#oracle-stake', '5000');
    await page.click('button:has-text("Register Node")');
    
    // Verify node appears
    await expect(page.getByText('Playwright API')).toBeVisible();
  });
});
