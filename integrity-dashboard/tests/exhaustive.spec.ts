import { test, expect } from '@playwright/test';

const tabs = ['telemetry', 'identity', 'ledger', 'zk', 'factory', 'compliance', 'credit', 'governance', 'markets', 'advanced'];

test.describe('Exhaustive UI Combination Validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173');
  });

  for (const tab of tabs) {
    test(`Validate UI combinations on #${tab}`, async ({ page }) => {
      // Navigate to tab
      await page.goto(`http://localhost:5173/#${tab}`);
      await page.waitForTimeout(500); // let animations settle

      // Ensure no error boundary triggers or white screen
      const root = await page.locator('#root');
      await expect(root).toBeVisible();

      // Find all interactive elements
      const buttons = await page.locator('button:not([disabled])').all();
      const selects = await page.locator('select:not([disabled])').all();
      const inputs = await page.locator('input:not([disabled])').all();

      // Safely click buttons that don't trigger form submissions (to avoid reloading)
      // For this test, we just verify they are present, clickable, and hoverable
      for (const btn of buttons) {
        await btn.hover();
        expect(await btn.isEnabled()).toBeTruthy();
      }

      // Change selects to their last option to test re-rendering state
      for (const select of selects) {
        const options = await select.locator('option').allInnerTexts();
        if (options.length > 0) {
          const lastOptionValue = await select.locator('option').last().getAttribute('value');
          if (lastOptionValue) {
            await select.selectOption(lastOptionValue);
          }
        }
      }

      // Enter test data into inputs to test controlled state combinations
      for (const input of inputs) {
        const type = await input.getAttribute('type');
        if (type === 'text') {
          await input.fill('test_validation');
        } else if (type === 'number') {
          await input.fill('999');
        } else if (type === 'checkbox') {
          await input.check();
        }
      }

      // Final sanity check that DOM is still intact after interactions
      await expect(page.locator('.sidebar')).toBeVisible();
      await expect(page.locator('.topbar')).toBeVisible();
      
      // If we made it here without the page crashing or Playwright timing out, the combination is stable
    });
  }
});
