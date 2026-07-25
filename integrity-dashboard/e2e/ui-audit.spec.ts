import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('E2E Visual and Functional Audit', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock settings to use 8080 as oracle if necessary, or just rely on default.
    // By default the dashboard connects to whatever is configured.
    await page.goto('/#/integrity/telemetry');
  });

  test('Sidebar/Topbar navigation tabs', async ({ page }) => {
    const tabs = [
      { name: 'Telemetry', id: 'telemetry' },
      { name: 'Finance', id: 'finance' }, // The tab might be labeled Finance, wait the label is Finance and defaultTab is wallet.
    ];
    
    // We will click around and take screenshots
    const navItems = ['Intelligence', 'Cognition', 'Contracts', 'Finance', 'Xibalba Shield', 'Identity'];
    
    for (const nav of navItems) {
      await page.click(`text=${nav}`);
      await page.waitForTimeout(500); // Wait for transition
      await page.screenshot({ path: `e2e/screenshots/tab-${nav.toLowerCase().replace(' ', '-')}.png`, fullPage: true });
    }
  });

  test('Command Palette states', async ({ page }) => {
    await page.goto('/#/integrity/telemetry');
    // Press Cmd+K or Ctrl+K to open palette
    await page.keyboard.press('Control+K');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `e2e/screenshots/command-palette-active.png`, fullPage: true });
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `e2e/screenshots/command-palette-hidden.png`, fullPage: true });
  });

  test('Wallet connection sequences', async ({ page }) => {
    await page.goto('/#/integrity/wallet');
    await page.screenshot({ path: `e2e/screenshots/wallet-disconnected.png`, fullPage: true });
    
    // Attempt to click connect wallet if there's a button
    const connectBtn = await page.$('text="Connect Wallet"');
    if (connectBtn) {
        await connectBtn.click();
        await page.waitForTimeout(500);
        await page.screenshot({ path: `e2e/screenshots/wallet-mock-connected.png`, fullPage: true });
    }
  });

  test('Agent detail pane transitions', async ({ page }) => {
    await page.goto('/#/integrity/identity');
    await page.waitForTimeout(1000);
    
    // Let's click on the first agent in the sidebar
    const firstAgent = await page.$('aside >> text=xibalba'); // assuming an agent has this in their address/alias
    if (firstAgent) {
        await firstAgent.click();
        await page.waitForTimeout(1000);
        await page.screenshot({ path: `e2e/screenshots/agent-detail-pane.png`, fullPage: true });
    } else {
        // Fallback click on sidebar item
        await page.mouse.click(100, 300); 
        await page.waitForTimeout(500);
        await page.screenshot({ path: `e2e/screenshots/agent-detail-pane.png`, fullPage: true });
    }
  });
  
  test('Error boundaries and Offline state', async ({ page }) => {
    // To simulate offline, we can route all API calls to a dead endpoint
    await page.route('**/v1/**', route => route.abort());
    await page.goto('/#/integrity/telemetry');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `e2e/screenshots/offline-state.png`, fullPage: true });
  });
});
