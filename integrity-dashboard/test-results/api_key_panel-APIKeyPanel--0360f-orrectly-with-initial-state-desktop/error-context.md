# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: api_key_panel.spec.ts >> APIKeyPanel Feature >> should render the APIKeyPanel correctly with initial state
- Location: e2e/api_key_panel.spec.ts:83:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('test_key_abc...l012')
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText('test_key_abc...l012')

```

```yaml
- complementary:
  - img "Xibalba"
  - button "Collapse sidebar" [expanded]
  - heading "Public Nodes" [level=2]
  - text: Network Roster (Read-Only) Agent 42994c5d Tier A Sov. did:integr...
  - button "Register New Agent"
  - button "Profile":
    - img "Profile"
- navigation:
  - button "Intelligence"
  - button "Cognition"
  - button "Contracts"
  - button "Finance"
  - button "Xibalba Shield"
  - button "Identity"
  - text: DATABASE ONLINE
  - button "Sync"
  - button "Connect Wallet"
- main:
  - heading "Appearance" [level=3]
  - text: Dashboard Theme
  - button "dark"
  - button "light"
  - button "system"
  - separator
  - text: Typography Font Family
  - button "Raleway"
  - button "Inter"
  - button "Outfit"
  - heading "Dashboard Configurations" [level=3]
  - paragraph: Configure dashboard state and data mode options.
  - text: Enable Mock Mode Load seeded mock agents instead of only the local Xibalba agent.
  - checkbox
  - heading "Protocol Config" [level=3]
  - paragraph: Manage infrastructure and storage parameters.
  - text: Storage Strategy
  - combobox:
    - option "MetaMask / Browser (Self-Custodial)" [selected]
    - option "Xibalba Secure Vault (App-Managed)"
    - option "Hardware Cold Storage (Ledger/Trezor)"
  - paragraph: Defines the primary signature provider for agent interactions.
  - text: KMS Provider
  - combobox:
    - option "Local Encrypted (Development)" [selected]
    - option "AWS KMS (Institutional)"
    - option "Fireblocks (Enterprise)"
  - checkbox
  - text: Enable Direct Hardware Bridge
  - paragraph: Required for direct HID communication with Ledger/Trezor devices via WebUSB.
  - text: RPC Endpoint
  - textbox: https://sepolia.base.org
  - text: ITK Token Contract
  - textbox: "0xF448c05074D435d256D6fbc1fC059019B86A5408"
  - paragraph: Global settings apply to the entire protocol fleet. Changing the Storage Strategy will affect how new agent identities are generated and anchored.
  - button "Save Infrastructure Config"
  - text: Developer API Keys Generate a Developer API Key to authenticate your agent with the Integrity Oracle without a hardware-backed DID. Agents using this auth bypass are mathematically capped at a Trust Level (AIS) of
  - strong: "300"
  - text: .
  - heading "Generate New Key" [level=4]
  - button "Generate Key"
  - heading "Active API Keys" [level=4]
  - text: No active API keys found.
  - strong: "Security Warning:"
  - text: Never commit your API key to public repositories. If your key is compromised, delete it immediately and generate a new one.
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test';
  2   | 
  3   | test.describe('APIKeyPanel Feature', () => {
  4   |   // Grant clipboard permissions for testing copy functionality
  5   |   test.use({ permissions: ['clipboard-read', 'clipboard-write'] });
  6   | 
  7   |   test.beforeEach(async ({ page }) => {
  8   |     // Mock the backend API calls used by the APIKeyPanel
  9   |     // Adjust the URL pattern '**/api/**' to match the actual endpoints of the Integrity Dashboard
  10  |     await page.route('**/v1/api-keys**', async (route) => {
  11  |       const request = route.request();
  12  |       const method = request.method();
  13  | 
  14  |       if (method === 'GET' && request.url().includes('keys')) {
  15  |         await route.fulfill({
  16  |           status: 200,
  17  |           contentType: 'application/json',
  18  |           body: JSON.stringify([
  19  |             {
  20  |               id: 'test_key_abc123def456ghi789jkl012',
  21  |               ais_trust_ceiling: 300,
  22  |               revoked_at: null,
  23  |               created_at: new Date().toISOString(),
  24  |             },
  25  |           ]),
  26  |         });
  27  |       } else if (method === 'POST' && request.url().includes('keys')) {
  28  |         await route.fulfill({
  29  |           status: 200,
  30  |           contentType: 'application/json',
  31  |           body: JSON.stringify({
  32  |             id: 'new_test_key_9876543210zyxwvuts',
  33  |             raw_key: 'new_test_key_9876543210zyxwvuts',
  34  |             ais_trust_ceiling: 300,
  35  |             revoked_at: null,
  36  |             created_at: new Date().toISOString(),
  37  |           }),
  38  |         });
  39  |       } else if (method === 'DELETE' && request.url().includes('keys')) {
  40  |         await route.fulfill({
  41  |           status: 200,
  42  |           contentType: 'application/json',
  43  |           body: JSON.stringify({ success: true }),
  44  |         });
  45  |       } else {
  46  |         await route.continue();
  47  |       }
  48  |     });
  49  | 
  50  |     // We mock localStorage so that the DashboardProvider initializes auth with our mock user
  51  |     await page.addInitScript(() => {
  52  |       window.localStorage.setItem('firebase:mock_user', JSON.stringify({
  53  |         uid: 'test-user',
  54  |         email: 'test@xibalba.io',
  55  |         name: 'Test Xibalba User',
  56  |         photoURL: 'https://example.com/test-photo.png'
  57  |       }));
  58  |       window.sessionStorage.setItem('integrity_userapi_jwt', 'mock-jwt-token-12345');
  59  |     });
  60  | 
  61  |     // Intercept user profile fetch
  62  |     await page.route('**/api/v1/user/me', async (route) => {
  63  |       await route.fulfill({
  64  |         status: 200,
  65  |         contentType: 'application/json',
  66  |         body: JSON.stringify({
  67  |           uid: 'test-user',
  68  |           email: 'test@xibalba.io',
  69  |           name: 'Test Xibalba User',
  70  |           photoURL: 'https://example.com/test-photo.png'
  71  |         })
  72  |       });
  73  |     });
  74  | 
  75  |     // Navigate to the dashboard
  76  |     await page.goto('/integrity/#/integrity');
  77  | 
  78  |     // Click profile avatar to open menu, then click Settings
  79  |     await page.locator('aside img[alt="Profile"]').first().click();
  80  |     await page.getByRole('button', { name: 'Settings' }).click();
  81  |   });
  82  | 
  83  |   test('should render the APIKeyPanel correctly with initial state', async ({ page }) => {
  84  |     // Verify panel header and static descriptions
  85  |     await expect(page.getByText('Developer API Keys')).toBeVisible();
  86  |     await expect(page.getByText(/Generate a Developer API Key to authenticate/i)).toBeVisible();
  87  |     
  88  |     // Verify "Generate New Key" section
  89  |     await expect(page.getByRole('heading', { name: 'Generate New Key' })).toBeVisible();
  90  |     const generateButton = page.getByRole('button', { name: 'Generate Key' });
  91  |     await expect(generateButton).toBeVisible();
  92  |     await expect(generateButton).not.toBeDisabled();
  93  |     
  94  |     // Verify active keys section loads and formats existing keys correctly
  95  |     await expect(page.getByRole('heading', { name: 'Active API Keys' })).toBeVisible();
  96  |     // test_key_abc123def456ghi789jkl012 -> test_key_abc...l012
> 97  |     await expect(page.getByText('test_key_abc...l012')).toBeVisible();
      |                                                         ^ Error: expect(locator).toBeVisible() failed
  98  |     
  99  |     // Verify security warning banner
  100 |     await expect(page.getByText('Security Warning:')).toBeVisible();
  101 |   });
  102 | 
  103 |   test('should generate a new API key and handle copying to clipboard', async ({ page }) => {
  104 |     // Click generate button
  105 |     await page.getByRole('button', { name: 'Generate Key' }).click();
  106 |     
  107 |     // Verify success UI banner appears
  108 |     await expect(page.getByText('New Key Generated')).toBeVisible();
  109 |     const newKeyInput = page.locator('input[readonly]');
  110 |     await expect(newKeyInput).toHaveValue('new_test_key_9876543210zyxwvuts');
  111 |     
  112 |     // Verify the new key is added to the active keys list at the bottom
  113 |     await expect(page.getByText('new_test_key...vuts')).toBeVisible();
  114 |     
  115 |     // Test clipboard copy logic
  116 |     const copyButton = page.locator('div', { hasText: 'New Key Generated' }).locator('button', { hasText: 'Copy' }).first();
  117 |     await copyButton.click();
  118 |     await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();
  119 |     
  120 |     // Validate the exact text was written to the system clipboard
  121 |     const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  122 |     expect(clipboardText).toBe('new_test_key_9876543210zyxwvuts');
  123 |   });
  124 | 
  125 |   test('should delete an active API key with confirmation dialog', async ({ page }) => {
  126 |     // Verify key exists before deletion
  127 |     await expect(page.getByText('test_key_abc...l012')).toBeVisible();
  128 |     
  129 |     // Setup dialog listener to automatically confirm the native confirm() popup
  130 |     page.on('dialog', dialog => dialog.accept());
  131 |     
  132 |     // Click the delete button for the specific key row
  133 |     const deleteButton = page.locator('button[title="Delete Key"]').first();
  134 |     await deleteButton.click();
  135 |     
  136 |     // Verify key is removed from the DOM
  137 |     await expect(page.getByText('test_key_abc...l012')).toBeHidden();
  138 |   });
  139 | 
  140 |   test('should be responsive on mobile viewports', async ({ page }) => {
  141 |     // Set viewport to a typical small mobile size
  142 |     await page.setViewportSize({ width: 375, height: 667 });
  143 |     
  144 |     // Ensure critical elements are still visible
  145 |     await expect(page.getByText('Developer API Keys')).toBeVisible();
  146 |     
  147 |     // Validate that inputs and buttons don't exceed screen width
  148 |     const generateButton = page.getByRole('button', { name: 'Generate Key' });
  149 |     
  150 |     const btnBox = await generateButton.boundingBox();
  151 |     
  152 |     expect(btnBox?.width).toBeLessThanOrEqual(375);
  153 |   });
  154 | });
  155 | 
```