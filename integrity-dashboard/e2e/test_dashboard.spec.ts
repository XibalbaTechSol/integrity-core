import { test, expect } from '@playwright/test';

test('dashboard loads all advanced capabilities tabs', async ({ page }) => {
  await page.goto('/integrity/');
  
  // Test Compliance Tab
  await page.click('text=Compliance');
  await expect(page.getByText('Compliance Scorecard')).toBeVisible();

  // Test Advanced Tab
  await page.click('text=Advanced');
  await expect(page.getByText('Advanced Contract Markets')).toBeVisible();
});
