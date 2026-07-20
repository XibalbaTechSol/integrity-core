import { test, expect } from '@playwright/test';

test.describe('Contract Factory Web IDE & Verification Suite E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock MetaMask
    await page.addInitScript(() => {
      (window as any).ethereum = {
        isMetaMask: true,
        request: async (args: any) => {
          if (args.method === 'eth_requestAccounts' || args.method === 'eth_accounts') {
            return ['0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556'];
          }
          return null;
        },
        on: () => {},
        removeListener: () => {},
      };
    });

    // Go to main dashboard route
    await page.goto('/integrity/#/integrity');
    await page.waitForTimeout(2000);
    
    // Click the Contracts tab in GlobalNav to load ContractsPage
    await page.locator('a, button, .tab-btn', { hasText: 'Contracts' }).first().click();
    await page.waitForTimeout(2000);
  });

  test('loads the Web IDE and components correctly', async ({ page }) => {
    // Check main Explorer title element
    await expect(page.getByText('Explorer')).toBeVisible();
    await expect(page.getByRole('button', { name: /Build Source/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Deploy Contract/i })).toBeVisible();

    // Verify initial validation state is idle
    await expect(page.getByText('Validation Console Idle')).toBeVisible();
  });

  test('switches template contract type and updates code editor', async ({ page }) => {
    const select = page.locator('#contract-type');
    await expect(select).toBeVisible();
    
    // Switch to Business Associate Agreement (BAA)
    await select.selectOption('BAA');
    
    // Check code editor contains BAA contract name
    const codeArea = page.locator('textarea').first();
    await expect(codeArea).toBeVisible();
    
    // Verify template changed in the preview/pre element to avoid strict mode violations
    await expect(page.locator('pre').getByText('contract SmartBAA {').first()).toBeVisible();
  });

  test('runs build/compilation and outputs logs', async ({ page }) => {
    const buildBtn = page.getByRole('button', { name: /Build Source/i });
    await buildBtn.click();

    // Verify compilation output in terminal
    await expect(page.locator('div').getByText(/SUCCESS: SLA compiled with 0 warnings/i).first()).toBeVisible({ timeout: 15000 });
  });

  test('deploys contract and runs interactive validation checks', async ({ page }) => {
    // Select the first active agent in the list to enable deploy
    const agent = page.locator('.sidebar-content div').first();
    if (await agent.count() > 0) {
      await agent.click();
    }

    // Run compile first
    await page.getByRole('button', { name: /Build Source/i }).click();
    await page.waitForTimeout(500);

    // Click Deploy
    const deployBtn = page.getByRole('button', { name: /Deploy Contract/i });
    await deployBtn.click();

    // Verify receipt info and validation checklist
    await expect(page.getByText('DEPLOYMENT VALIDATED')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText('L2 Transaction Broadcasted')).toBeVisible();
    await expect(page.getByText('Bytecode Match Verified')).toBeVisible();
    await expect(page.getByText('ZK Proof Verified (Base L0)')).toBeVisible();

    // Run interactive call simulation on SLA contract
    const runCallBtn = page.getByRole('button', { name: /Run Validation Call/i });
    await expect(runCallBtn).toBeVisible();
    
    // Perform verification call simulation
    await runCallBtn.click();

    // Validate outputs are written to the validation logs
    await expect(page.getByText('Simulating execution of validation transaction...').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('SLA check complete').first()).toBeVisible({ timeout: 15000 });
  });
});
