import { test, expect } from '@playwright/test';

test.describe('APIKeyPanel Feature', () => {
  // Grant clipboard permissions for testing copy functionality
  test.use({ permissions: ['clipboard-read', 'clipboard-write'] });

  test.beforeEach(async ({ page }) => {
    // Mock the backend API calls used by the APIKeyPanel
    // Adjust the URL pattern '**/api/**' to match the actual endpoints of the Integrity Dashboard
    await page.route('**/v1/api-keys**', async (route) => {
      const request = route.request();
      const method = request.method();

      if (method === 'GET' && request.url().includes('keys')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              api_key: 'test_key_abc123def456ghi789jkl012',
              created_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
            },
          ]),
        });
      } else if (method === 'POST' && request.url().includes('keys')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            api_key: 'new_test_key_9876543210zyxwvuts',
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
          }),
        });
      } else if (method === 'DELETE' && request.url().includes('keys')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        });
      } else {
        await route.continue();
      }
    });

    // Navigate to the page containing the APIKeyPanel
    await page.goto('/integrity/#/integrity'); 
    await page.getByRole('button', { name: 'Identity', exact: true }).click();
    await page.getByRole('button', { name: 'API Keys', exact: true }).click();
  });

  test('should render the APIKeyPanel correctly with initial state', async ({ page }) => {
    // Verify panel header and static descriptions
    await expect(page.getByText('Developer API Keys')).toBeVisible();
    await expect(page.getByText(/Generate a Developer API Key to authenticate/i)).toBeVisible();
    
    // Verify "Generate New Key" section
    await expect(page.getByRole('heading', { name: 'Generate New Key' })).toBeVisible();
    const generateButton = page.getByRole('button', { name: 'Generate Key' });
    await expect(generateButton).toBeVisible();
    await expect(generateButton).not.toBeDisabled();
    
    // Verify active keys section loads and formats existing keys correctly
    await expect(page.getByRole('heading', { name: 'Active API Keys' })).toBeVisible();
    // test_key_abc123def456ghi789jkl012 -> test_key_abc...l012
    await expect(page.getByText('test_key_abc...l012')).toBeVisible();
    
    // Verify security warning banner
    await expect(page.getByText('Security Warning:')).toBeVisible();
  });

  test('should generate a new API key and handle copying to clipboard', async ({ page }) => {
    // Select expiration time
    await page.locator('select').selectOption('90');
    
    // Click generate button
    await page.getByRole('button', { name: 'Generate Key' }).click();
    
    // Verify success UI banner appears
    await expect(page.getByText('New Key Generated')).toBeVisible();
    const newKeyInput = page.locator('input[readonly]');
    await expect(newKeyInput).toHaveValue('new_test_key_9876543210zyxwvuts');
    
    // Verify the new key is added to the active keys list at the bottom
    await expect(page.getByText('new_test_key...vuts')).toBeVisible();
    
    // Test clipboard copy logic
    const copyButton = page.locator('div', { hasText: 'New Key Generated' }).locator('button', { hasText: 'Copy' }).first();
    await copyButton.click();
    await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();
    
    // Validate the exact text was written to the system clipboard
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toBe('new_test_key_9876543210zyxwvuts');
  });

  test('should delete an active API key with confirmation dialog', async ({ page }) => {
    // Verify key exists before deletion
    await expect(page.getByText('test_key_abc...l012')).toBeVisible();
    
    // Setup dialog listener to automatically confirm the native confirm() popup
    page.on('dialog', dialog => dialog.accept());
    
    // Click the delete button for the specific key row
    const deleteButton = page.locator('button[title="Delete Key"]').first();
    await deleteButton.click();
    
    // Verify key is removed from the DOM
    await expect(page.getByText('test_key_abc...l012')).toBeHidden();
  });

  test('should be responsive on mobile viewports', async ({ page }) => {
    // Set viewport to a typical small mobile size
    await page.setViewportSize({ width: 375, height: 667 });
    
    // Ensure critical elements are still visible
    await expect(page.getByText('Developer API Keys')).toBeVisible();
    
    // Validate that inputs and buttons don't exceed screen width
    const generateButton = page.getByRole('button', { name: 'Generate Key' });
    const select = page.locator('select');
    
    const btnBox = await generateButton.boundingBox();
    const selectBox = await select.boundingBox();
    
    expect(btnBox?.width).toBeLessThanOrEqual(375);
    expect(selectBox?.width).toBeLessThanOrEqual(375);
  });
});
