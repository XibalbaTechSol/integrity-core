import { Page, expect } from '@playwright/test';

/**
 * Navigates to a specific tab in the Integrity Dashboard.
 * Handles responsive navigation by opening the accordion on mobile/tablet.
 */
export async function navigateTab(page: Page, tabId: string, tabLabel?: string) {
  // Navigate to the base dashboard route via hash for HashRouter
  await page.goto('/#/integrity');
  
  // Wait for the app shell to be visible
  await page.waitForSelector('.app-shell', { state: 'visible', timeout: 15000 });

  // Use the global helper to set the active tab if it exists
  await page.evaluate((id) => {
    if (window.__setActiveTab) {
      window.__setActiveTab(id);
    }
  }, tabId);

  // If a specific label is provided, we can also try to click it for visual confirmation
  if (tabLabel) {
    try {
      await page.getByText(tabLabel).first().click({ timeout: 2000 });
    } catch (e) {
      console.log(`Optional label click failed for ${tabLabel}, relying on __setActiveTab`);
    }
  }
  
  await page.waitForTimeout(500); 
}

/**
 * Ensures that an element is visible, specifically handling cases where 
 * it might be hidden in a collapsed sidebar on mobile.
 */
export async function ensureVisible(page: Page, locator: any) {
  if (await locator.count() === 0) {
    // Try to expand sidebar if possible
    const expandBtn = page.locator('.sidebar button[aria-label="Expand sidebar"]');
    if (await expandBtn.isVisible()) {
      await expandBtn.click();
    }
  }
  await expect(locator).toBeVisible({ timeout: 15000 });
}
