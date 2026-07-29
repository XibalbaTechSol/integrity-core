import { test, expect } from '@playwright/test';

const MOCK_AGENTS = [
  {
    eth_address: '0x1234567890abcdef1234567890abcdef12345678',
    alias: 'Alpha Node',
    current_ais: 850,
    model_class: 'gpt-4o',
    tee_verified: true,
    owned_contracts: [
      { contract_address: '0xabc123', contract_type: 'SLA', revenue_generated: 500, is_collateralized: false, collateral_value: 1000 }
    ],
    credit_profile: { credit_score: 700, max_borrow_limit: 5000, total_borrowed: 0, default_count: 0, active_loans: [] },
    equity: [
      { agent_address: '0x999...', shares: 100, total_shares: 1000, percentage: 10, dividends_earned: 50 }
    ]
  }
];

const MOCK_STATS = {
  active_nodes: 10,
  aggregate_ais: 820,
  protocol_staked_itk: 150000,
  active_disputes: 0
};

test.describe('Functional Workflows & A2A Markets', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/v1/user/agents', async route => {
      await route.fulfill({ json: MOCK_AGENTS });
    });
    await page.route('**/v1/protocol/stats', async route => {
      await route.fulfill({ json: MOCK_STATS });
    });
    await page.route('**/v1/transactions/report', async route => {
      await route.fulfill({ json: { status: 'success' } });
    });
    await page.route('**/v1/contracts/factory/deploy', async route => {
      await route.fulfill({ json: { contract_address: '0xnew123456', status: 'deployed' } });
    });
    await page.route('**/v1/agent/*/reputation/history', async route => {
      await route.fulfill({ json: [{ date: new Date().toISOString(), ais: 850 }] });
    });

    await page.goto('http://localhost:5173');
    await page.waitForTimeout(1000);
  });

  test('Telemetry Tab - Form Submission', async ({ page }) => {
    await page.click('text=Telemetry');
    await expect(page.getByRole('heading', { name: 'Alpha Node' })).toBeVisible();
    
    // Fill telemetry form
    await page.getByRole('spinbutton').first().fill('500');
    await page.click('button:has-text("Validate & Submit")');
    
    // Check toast
    await expect(page.getByText('Telemetry ingested and validated successfully')).toBeVisible();
  });

  test('Contract Factory Tab - Deploy Custom Code', async ({ page }) => {
    await page.click('text=Contract Factory');
    
    // Switch to Custom Code
    await page.click('text=Custom Code');
    
    // Deploy contract
    await page.click('button:has-text("Compile & Deploy Contract")');
    
    // Check toast
    await expect(page.getByText(/Contract deployed successfully/)).toBeVisible();
  });

  test('A2A Markets Tab - Validate Equity and Contracts', async ({ page }) => {
    await page.click('text=A2A Markets');
    
    // Validate Agent Equity Holdings table renders with mock data
    await expect(page.getByText('Agent Equity Holdings')).toBeVisible();
    await expect(page.getByRole('cell', { name: '0x999...' })).toBeVisible();
    await expect(page.getByRole('cell', { name: '10%' })).toBeVisible();
    await expect(page.getByRole('cell', { name: '50 ITK' })).toBeVisible();

    // Validate Contract Trading area (even if empty, ensure no crash)
    await expect(page.getByText('Contract Trading')).toBeVisible();
  });

  test('Credit & Loans Tab - Rendering with Collateral', async ({ page }) => {
    await page.click('text=Credit & Loans');
    
    // Verify credit score is loaded
    await expect(page.getByText('700')).toBeVisible();
    
    // Verify collateral list shows the mock contract
    await expect(page.getByText('0xabc123...')).toBeVisible();
  });
});
