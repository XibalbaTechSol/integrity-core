import { test, expect } from '@playwright/test';

test.describe('CompliancePanel', () => {
  test('should display compliance scorecard and audit trail', async ({ page }) => {
    await page.goto('/integrity/');
    
    // Navigate to the Compliance tab (handle mobile accordion if present)
    const accordionBtn = page.locator('.tab-nav-accordion > button');
    if (await accordionBtn.isVisible()) {
      await accordionBtn.click();
    }
    await page.locator('button.tab-btn').filter({ hasText: 'Compliance' }).first().click();
    
    // Verify panels exist
    await expect(page.getByText('Compliance Scorecard', { exact: false })).toBeVisible();
    await expect(page.getByText('Audit Trail & Alerts', { exact: false })).toBeVisible();
  });
});
