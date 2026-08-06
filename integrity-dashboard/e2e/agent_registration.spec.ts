import { test, expect } from '@playwright/test';

test.describe('Agent Registration E2E Workflow', () => {
  test('should register a new agent via Dashboard and be verifiable', async ({ page }) => {
    // 1. Navigate to the Identity page where registration is triggered
    await page.goto('/integrity/#/integrity#identity');
    
    // 2. Trigger the registration modal
    // Based on IdentityPanel.tsx, there is a button with text "Register New"
    await page.getByRole('button', { name: /Register New/i }).click();
    
    // 3. Fill out the Onboarding form (Step 1: Basic Identity)
    const alias = 'E2E-Test-Agent-' + Math.floor(Math.random() * 1000);
    const handle = 'e2e-test-' + Math.floor(Math.random() * 1000);
    
    await page.getByPlaceholder(/e.g. Neon Centurion/i).fill(alias);
    await page.getByPlaceholder(/e.g. xibalba/i).fill(handle);
    await page.getByPlaceholder(/Describe your agent's purpose/i).fill('Automated E2E Validation Agent');
    
    // Use a mock address for the controller to avoid needing a real wallet for this test
    const mockAddress = '0x1234567890123456789012345678901234567890';
    await page.getByPlaceholder('0x...').fill(mockAddress);
    
    await page.getByRole('button', { name: /Continue/i }).click();
    
    // 4. Step 2: On-Chain Registry
    // Click "Initialize Sovereign Contract"
    await page.getByRole('button', { name: /Initialize Sovereign Contract/i }).click();
    
    // Wait for the transition to Step 3
    await expect(page.getByText(/SDK Orchestration/i)).toBeVisible();
    
    // 5. Step 3: SDK Orchestration
    await page.getByRole('button', { name: /Continue/i }).click();
    
    // 6. Step 4: Finalized
    await expect(page.getByText(/Agent Sovereign/i)).toBeVisible();
    await expect(page.getByText(new RegExp(alias, 'i')).toBeVisible());
    
    // 7. Finalize and return to Command Center
    await page.getByRole('button', { name: /Enter Command Center/i }).click();
    
    // 8. Verify the agent appears in the identity list
    await expect(page.getByText(new RegExp(alias, 'i')).toBeVisible());
  });
});
