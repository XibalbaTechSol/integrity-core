import { test, expect } from '@playwright/test';

test.describe('TelemetryGraphs Component', () => {
  test('should render multiple metrics and agent xibalba correctly when API responds', async ({ page }) => {
    // Mock the backend API response
    await page.route('**/v1/telemetry/latest', async (route) => {
      const json = [
        {
          timestamp: new Date().toISOString(),
          latency: 45,
          accuracy: 0.99,
          deal_value: 120,
          agent: 'Agent Xibalba',
          metadata: {
            discrepancy_ratio: 0.01,
            semantic_drift: 0.05,
            transaction_velocity: 15,
            environment: { cpu_percent: 20, memory_percent: 40 }
          }
        }
      ];
      await route.fulfill({ json });
    });

    // Navigate to the dashboard where TelemetryGraphs is rendered
    await page.goto('/integrity/#/integrity#telemetry');

    // Wait for the UI to hydrate
    await page.waitForTimeout(2000);

    // Check for the Multi-Metric Telemetry header
    await expect(page.getByText('Multi-Metric Telemetry')).toBeVisible({ timeout: 10000 });

    // Verify Agent Xibalba is in the dropdown
    const selectLocator = page.locator('select').first();
    await expect(selectLocator).toContainText('Agent Xibalba');

    // Select Agent Xibalba
    await selectLocator.selectOption({ label: 'Agent Xibalba' });

    // Verify Metric Toggles are visible
    await expect(page.getByRole('button', { name: 'Latency (ms)' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Accuracy (%)' })).toBeVisible();

    // Verify we can toggle a metric off and on
    const semanticDriftBtn = page.getByRole('button', { name: 'Semantic Drift' });
    await expect(semanticDriftBtn).toBeVisible();
    await semanticDriftBtn.click(); // Should toggle it on
  });
});

