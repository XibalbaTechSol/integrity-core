import { test, expect } from '@playwright/test';
import { navigateTab } from './test-utils';

const mockTrajectories = [
  {
    id: 'traj_01',
    intent: 'Analyze and summarize patient blood test results.',
    status: 'Validating',
    score: 950,
    steps: [
      { id: 's1', type: 'thought', message: 'First thought', time: '10:02:45' }
    ]
  },
  {
    id: 'traj_02',
    intent: 'Generate medical report',
    status: 'Drift Detected',
    score: 650,
    steps: [
      { id: 's2', type: 'tool', name: 'generate_report', args: '{}', time: '10:05:00' },
      { id: 's3', type: 'alert', message: 'Drift warning', time: '10:05:01' }
    ]
  }
];

test.describe('TrajectoryPanel Component', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the trajectory polling endpoint
    await page.route('**/v1/trajectories/recent', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ trajectories: mockTrajectories }),
      });
    });

    await navigateTab(page, 'trajectory', 'Agent Thoughts');
  });

  test('should render trajectory list and update active trajectory on click', async ({ page }) => {
    // Verify Left Column: Trajectories list renders correctly
    await expect(page.getByText('Active Intent Trajectories')).toBeVisible();
    await expect(page.getByText('traj_01')).toBeVisible();
    await expect(page.getByText('traj_02')).toBeVisible();
    await expect(page.getByText('Analyze and summarize patient blood test results.')).toBeVisible();
    await expect(page.getByText('Generate medical report')).toBeVisible();

    // Verify initial BCC Evaluation Score
    await expect(page.getByText('BCC Evaluation Score')).toBeVisible();
    await expect(page.getByText('950')).toBeVisible();

    // Verify initial Thought Trace
    await expect(page.getByText('Live Agent Cognition & Telemetry Trace')).toBeVisible();
    await expect(page.getByText('First thought')).toBeVisible();

    // Click the second trajectory
    await page.getByText('traj_02').click();

    // Verify BCC Evaluation Score updates to the second trajectory
    await expect(page.getByText('650')).toBeVisible();
    
    // Verify Thought Trace updates to the new steps
    await expect(page.getByText('generate_report')).toBeVisible();
    await expect(page.getByText('Drift warning')).toBeVisible();
    
    // Ensure the old thought trace is no longer visible
    await expect(page.getByText('First thought')).not.toBeVisible();
  });

  test('should render conditional status styling correctly', async ({ page }) => {
    const validStatus = page.locator('text=Validating');
    await expect(validStatus).toBeVisible();
    
    const driftStatus = page.locator('text=Drift Detected');
    await expect(driftStatus).toBeVisible();
  });
});
