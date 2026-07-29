import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Visual Audit', () => {
  test('take screenshots of all pages', async ({ page }) => {
    // Mock user so we can see the pages
    await page.addInitScript(() => {
      window.localStorage.setItem('firebase:mock_user', JSON.stringify({
        uid: 'test-user',
        email: 'test@xibalba.io',
        name: 'Test Xibalba User',
        photoURL: 'https://example.com/test-photo.png'
      }));
    });

    const pages = [
      { url: '/#/', name: 'dashboard_home' },
      { url: '/#/profile', name: 'dashboard_profile' },
      { url: '/#/settings', name: 'dashboard_settings' },
      { url: '/#/integrity#telemetry', name: 'dashboard_telemetry' }
    ];

    const artifactsDir = '/home/xibalba/.gemini/antigravity-cli/brain/64551caf-854d-4bed-9bc6-5ca7bda4ced4/scratch';
    
    for (const p of pages) {
      await page.goto(p.url);
      await page.waitForTimeout(2000); // give it time to render
      await page.screenshot({ path: path.join(artifactsDir, `${p.name}.png`), fullPage: true });
    }
  });
});
