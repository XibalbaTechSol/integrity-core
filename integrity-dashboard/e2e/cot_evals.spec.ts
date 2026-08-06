import { test, expect } from '@playwright/test';

test.describe('Advanced Diagnostics & Granular Evals Validation', () => {
  test('COTPlatform renders mechanistic evals layout correctly', async ({ page }) => {
    // Intercept telemetry API to supply mock trajectory with our new eval metrics
    await page.route('**/v1/telemetry/latest', async route => {
      await route.fulfill({
        status: 200,
        json: [{
          id: 'mock-traj-123',
          timestamp: new Date().toISOString(),
          agent: 'mock-agent',
          metadata: {
            task: 'Mock Task',
            semantic_drift: 0.05,
            agent_traces: [
              { id: 's1', type: 'thought', message: 'Thinking...' }
            ],
            evals: {
              reasoning_depth: 12,
              tool_efficiency: 0.85,
              backtrack_count: 2,
              langchain_helpfulness: 0.99,
              langchain_reasoning: 'The agent took logical steps and used the correct API endpoints. It successfully navigated the UI without unnecessary loops.'
            }
          }
        }]
      });
    });

    await page.goto('/integrity/#/integrity#telemetry');
    await page.waitForTimeout(1000);

    // Click the telemetry tab explicitly just in case
    await page.locator('.tab-btn', { hasText: 'Telemetry' }).first().click();
    await page.waitForTimeout(500);

    // The component should map key -> 'key.replace(/_/g, " ")'
    await expect(page.getByText(/tool efficiency/i)).toBeVisible();
    await expect(page.getByText('0.85')).toBeVisible();
    
    await expect(page.getByText(/backtrack count/i)).toBeVisible();
    await expect(page.getByText('2')).toBeVisible();
    
    await expect(page.getByText(/langchain helpfulness/i)).toBeVisible();
    await expect(page.getByText('0.99')).toBeVisible();
    
    // Check that the long reasoning text is rendered in the wider card format
    await expect(page.getByText(/langchain reasoning/i)).toBeVisible();
    await expect(page.getByText(/The agent took logical steps and used the correct API endpoints/i)).toBeVisible();
  });
});
