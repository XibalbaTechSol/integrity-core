import { test, expect } from '@playwright/test';

const MOCK_AGENTS = [
  {
    eth_address: '0x1234567890abcdef1234567890abcdef12345678',
    alias: 'Alpha Node',
    current_ais: 850,
    model_class: 'gpt-4o',
    tee_verified: true,
    staked_itk: 5000,
    verification_tier: 2,
    compliance_score: 98,
    entropy_score: 12,
    grounding_score: 950,
    sacrifice_score: 800,
    registered_at: new Date().toISOString(),
    last_active: new Date().toISOString()
  }
];

const MOCK_STATS = {
  active_nodes: 10,
  aggregate_ais: 820,
  protocol_staked_itk: 150000,
  active_disputes: 0,
  tvl: 12450200
};

test.describe('Master Specification Alignment Workflows', () => {
  test.beforeEach(async ({ page }) => {
    // Mock Core API
    await page.route('**/v1/user/agents', async route => {
      await route.fulfill({ json: MOCK_AGENTS });
    });
    await page.route('**/v1/protocol/stats', async route => {
      await route.fulfill({ json: MOCK_STATS });
    });
    await page.route('**/v1/agent/*/reputation/history', async route => {
      await route.fulfill({ json: [{ date: new Date().toISOString(), ais: 850 }] });
    });
    
    // Mock Marketplace
    await page.route('**/v1/market/tasks', async route => {
      await route.fulfill({ json: [
        { task_id: 'task_001', title: 'Medical Data Inference', reward_itk: 500, min_ais_required: 800, status: 'OPEN', created_at: new Date().toISOString() }
      ]});
    });

    await page.goto('/integrity/#/integrity');
    await page.waitForTimeout(1000);
  });

  test('Domain Context Selector - Multi-Tenant Isolation', async ({ page }) => {
    const selector = page.locator('select').first(); // The domain selector is in Topbar
    await expect(selector).toBeVisible();
    
    // Check initial value
    await expect(selector).toHaveValue('global');
    
    // Switch to Shield
    await selector.selectOption('shield');
    await expect(selector).toHaveValue('shield');
    
    // Switch to Quant
    await selector.selectOption('quant');
    await expect(selector).toHaveValue('quant');
  });

  test('Xibalba Shield - Smart BAA & HIPAA Safeguards', async ({ page }) => {
    await page.click('text=Xibalba Shield');
    
    // Switch to Smart BAAs sub-tab
    await page.getByRole('button', { name: 'Smart BAAs' }).click();
    await expect(page.getByText('Smart BAA Registry')).toBeVisible();
    await expect(page.getByRole('cell', { name: '0xMayo_Clinic' }).first()).toBeVisible();
    
    // Verify Technical Safeguards
    await expect(page.getByText('HIPAA Gateway Concept & Safeguards')).toBeVisible();
    
    // Switch to Audit & Compliance sub-tab
    await page.getByRole('button', { name: 'Audit & Compliance' }).click();
    await expect(page.getByText('Medical Record Interaction Logs')).toBeVisible();
    await expect(page.getByText('BLOCKED').first()).toBeVisible();
  });

  test('Oracle Registry - World Awareness Protocol', async ({ page }) => {
    await page.click('text=Contracts');
    await page.getByRole('button', { name: 'Oracle', exact: true }).click();
    
    // Verify Registry Table
    await expect(page.getByText('World Awareness: Oracle Registry')).toBeVisible();
    await expect(page.getByText('National Medical Library')).toBeVisible();
    
    // Verify Consensus Status
    await expect(page.getByText('Oracle Consensus')).toBeVisible();
    
    // Verify Settlement Proofs
    await expect(page.getByText('Recent Settlement Proofs')).toBeVisible();
    await expect(page.getByText('0xMerkle_').first()).toBeVisible();
  });

  test('Forensic Provenance - BCC Intent-Locking audit', async ({ page }) => {
    await page.click('text=Cognition');
    
    // Verify Forensic Explorer
    await expect(page.getByText('Forensic Provenance Explorer')).toBeVisible();
    
    // Verify stability benchmarks title
    await expect(page.getByText('Live SDK Evaluation Benchmarks')).toBeVisible();
  });

  test('A2A Marketplace - Autonomous Task Creation', async ({ page }) => {
    await page.click('text=Finance');
    await page.getByRole('button', { name: 'Markets', exact: true }).click();
    
    // Verify Task Creation Form
    await expect(page.getByText('Create Autonomous Task')).toBeVisible();
    
    // Verify Protocol Logs console
    await expect(page.getByText('Protocol Logs')).toBeVisible();
    
    // Verify Open Tasks table
    await expect(page.getByText('Open Marketplace Tasks')).toBeVisible();
  });
});
