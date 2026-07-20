import { test } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const TABS = [
  'telemetry', 'identity', 'ledger', 'zk', 'factory', 
  'compliance', 'credit', 'governance', 'markets', 
  'staking', 'stability', 'wallet', 'advanced', 'apikeys'
];

const REPORTS_DIR = path.join(process.cwd(), 'validation_reports', 'screenshots');

test.beforeAll(async () => {
  if (!fs.existsSync(REPORTS_DIR)) {
    fs.mkdirSync(REPORTS_DIR, { recursive: true });
  }
});

TABS.forEach(tab => {
  test(`visual audit for tab: ${tab}`, async ({ page }, testInfo) => {
    // Navigate to the tab
    await page.goto(`/integrity/#/integrity#${tab}`);
    
    // Wait for the main app shell or a common panel to be visible to ensure it's loaded
    await page.waitForSelector('.app-shell', { state: 'visible', timeout: 15000 });
    await page.waitForTimeout(1000); // Wait for animations
    
    const viewportName = testInfo.project.name;
    const screenshotPath = path.join(REPORTS_DIR, `${viewportName}_${tab}.png`);
    
    await page.screenshot({ path: screenshotPath, fullPage: true });
    
    // Basic heuristic checks
    const overflow = await page.evaluate(() => {
      return document.body.scrollWidth > document.body.clientWidth;
    });
    
    if (overflow) {
      console.warn(`[WARNING] Horizontal overflow detected on ${tab} in ${viewportName}`);
    }
  });
});
