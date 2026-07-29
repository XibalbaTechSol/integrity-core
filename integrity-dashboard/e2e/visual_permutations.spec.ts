import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { navigateTab, ensureVisible } from './test-utils';

const REPORTS_DIR = path.join(process.cwd(), 'validation_reports', 'screenshots');

test.beforeAll(async () => {
  if (!fs.existsSync(REPORTS_DIR)) {
    fs.mkdirSync(REPORTS_DIR, { recursive: true });
  }
});

const MOCK_AGENT = {
  agent_id: '88d5ab08-156b-45cf-9b17-32e74a9f2690',
  eth_address: '0x1234567890abcdef1234567890abcdef12345678',
  alias: 'Visual Audit Agent',
  current_ais: 850,
  staked_itk: 10000,
};

const MOCK_CREDIT = { 
  credit_score: 750, 
  max_borrow_limit: 10000, 
  total_borrowed: 0, 
  active_loans: [] 
};

test.beforeEach(async ({ page }) => {
  // Global request logger
  await page.route('**/*', async route => {
    const url = route.request().url();
    if (url.includes('/v1/') || url.includes('/benchmarks')) {
      console.log(`NETWORK: Request to ${url}`);
    }
    await route.continue();
  });

  // Global mocks to unlock UI
  await page.route('**/v1/user/agents', async route => {
    console.log('MOCK: Intercepting /v1/user/agents');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([MOCK_AGENT]) });
  });
  await page.route('**/v1/protocol/stats', async route => {
    console.log('MOCK: Intercepting /v1/protocol/stats');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total_agents: 1, total_itk_staked: 1000000 }) });
  });
  await page.route('**/v1/agent/*/credit/profile', async route => {
    console.log('MOCK: Intercepting /v1/agent/*/credit/profile');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_CREDIT) });
  });
  
  // Prevent logs/errors from missing endpoints
  await page.route('**/v1/ledger/history', async route => {
    console.log('MOCK: Intercepting /v1/ledger/history');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ logs: [] }) });
  });

  // Mock benchmarking to avoid timeouts
  await page.route('**/benchmarks', async route => {
    console.log('MOCK: Intercepting /benchmarks');
    await route.fulfill({ 
        status: 200, 
        contentType: 'application/json',
        body: JSON.stringify([
            { model_name: 'TEST-HIGH-LOAD', provider_name: 'MOCK', simulated_ais: 999, stability_metric: 0.99, grounding_metric: 0.99 }
        ]) 
    });
  });
});

test.describe('Deep Visual Audit - Component Permutations', () => {
  
  // Helper to ensure page is ready and agent selected
  async function setupTab(page, tab) {
    await navigateTab(page, tab);
    
    // Find the mock agent in the sidebar and click it to select
    const agentLocator = page.getByText('Visual Audit Agent').first();
    const count = await agentLocator.count();
    
    if (count > 0) {
      await agentLocator.click();
      await page.waitForTimeout(500);
    } else {
      console.log(`DEBUG: Mock agent 'Visual Audit Agent' not found on tab ${tab}. Taking debug screenshot.`);
      await page.screenshot({ path: path.join(REPORTS_DIR, `debug_missing_agent_${tab}.png`), fullPage: true });
      const content = await page.content();
      console.log(`DEBUG: Page content length: ${content.length}`);
    }
    
    // Now ensure it is visible in the current view (sidebar or main area)
    await ensureVisible(page, agentLocator);
  }

  test('Identity - Registration Flow State', async ({ page }, testInfo) => {
    await setupTab(page, 'identity');
    await page.getByRole('button', { name: /Register New/i }).first().click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(REPORTS_DIR, `${testInfo.project.name}_identity_registration_modal.png`) });
  });

  test('ZKProver - Proving Pipeline State', async ({ page }, testInfo) => {
    await page.route('**/v1/zk/prove/**', async route => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ proof: { proof_hash: '0x123', proof_data: '{}' } }) });
    });

    await setupTab(page, 'zk');
    const btn = page.getByRole('button', { name: /Generate Proof/i });
    await expect(btn).toBeEnabled();
    await btn.click();
    await page.waitForSelector('.animate-fade-in', { timeout: 10000 }); 
    await page.screenshot({ path: path.join(REPORTS_DIR, `${testInfo.project.name}_zk_proving_pipeline.png`) });
  });

  test('Markets - Creating Task State', async ({ page }, testInfo) => {
    await page.route('**/v1/market/tasks', async route => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    });
    
    await setupTab(page, 'markets');
    await page.fill('#task-title', 'Visual Test Task');
    const btn = page.getByRole('button', { name: /Create A2A Task/i });
    await expect(btn).toBeEnabled();
    await btn.click();
    await page.screenshot({ path: path.join(REPORTS_DIR, `${testInfo.project.name}_markets_task_creation.png`) });
  });

  test('Credit - Error and Overlimit State', async ({ page }, testInfo) => {
    await setupTab(page, 'credit');
    await page.fill('#borrow-amount', '9999999');
    await expect(page.locator('text=Exceeds maximum borrow limit')).toBeVisible();
    await page.screenshot({ path: path.join(REPORTS_DIR, `${testInfo.project.name}_credit_overlimit_error.png`) });
  });

  test('Stability - Mocked Comparison Data', async ({ page }, testInfo) => {
    await setupTab(page, 'stability');
    await page.waitForSelector('text=TEST-HIGH-LOAD', { state: 'visible' });
    await page.screenshot({ path: path.join(REPORTS_DIR, `${testInfo.project.name}_stability_mocked_comparison.png`) });
  });
});
