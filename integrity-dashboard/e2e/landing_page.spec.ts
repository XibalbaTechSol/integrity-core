import { test, expect } from '@playwright/test';

test.describe('LandingPage E2E', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app root where LandingPage is typically served
    await page.goto('/integrity/');
  });

  test('should render the landing page and essential sections', async ({ page }) => {
    // Header check
    await expect(page.locator('header').getByText('INTEGRITY')).toBeVisible();

    // Hero section check
    await expect(page.getByText(/Know your agent's trustworthiness/i)).toBeVisible();

    // Verify main call-to-action buttons in Hero
    await expect(page.getByRole('button', { name: /Institutional Inquiries/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Developer Integration/i })).toBeVisible();
  });

  test('should open and close the Contact Modal', async ({ page }) => {
    // Open modal via Institutional Inquiries button
    await page.getByRole('button', { name: /Institutional Inquiries/i }).click();

    // Verify the modal appears by checking the heading
    const contactHeading = page.getByRole('heading', { name: 'Contact Us' });
    await expect(contactHeading).toBeVisible();

    // Test form field interaction
    await page.locator('input[name="name"]').fill('Test User');
    await page.locator('input[name="email"]').fill('test@example.com');

    // Close the modal using the close button (Lucide X icon)
    const closeBtn = page.locator('button').filter({ has: page.locator('svg.lucide-x') }).first();
    await closeBtn.click();

    // Verify it closed smoothly
    await expect(contactHeading).not.toBeVisible();
  });

  test('should open and close the Registry Explorer', async ({ page }) => {
    // Open Registry Explorer
    await page.getByText(/XNS Resolver —/i).click();

    // Verify the explorer opened
    const registryHeading = page.getByRole('heading', { name: 'XNS Resolver', exact: true });
    await expect(registryHeading).toBeVisible();

    // Interact with the search input
    const searchInput = page.getByPlaceholder('Agent address...');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('0xTestAgent');

    // Close the explorer
    const closeBtn = page.locator('button').filter({ has: page.locator('svg.lucide-x') }).first();
    await closeBtn.click();

    // Verify it closed
    await expect(registryHeading).not.toBeVisible();
  });

  test('should navigate to /integrity when Launch Dashboard is clicked', async ({ page }) => {
    // Ensure desktop viewport
    await page.setViewportSize({ width: 1280, height: 800 });

    // Click Launch Dashboard in header
    const launchButton = page.locator('header').getByRole('button', { name: /Launch Dashboard/i });
    await launchButton.click();

    // Assert navigation occurs (Wait for URL to change to /integrity)
    await page.waitForURL('**/integrity');
    await expect(page).toHaveURL(/.*\/integrity/);
  });

  test('responsive layout - mobile menu interaction', async ({ page }) => {
    // Set viewport to mobile
    await page.setViewportSize({ width: 375, height: 812 });

    const header = page.locator('header');

    // The desktop Launch Dashboard button should not be visible
    const launchBtnDesktop = header.getByRole('button', { name: /Launch Dashboard/i });
    await expect(launchBtnDesktop).not.toBeVisible();

    // The mobile menu button should be present
    const menuButton = header.getByRole('button').first();
    await expect(menuButton).toBeVisible();

    // Open mobile menu
    await menuButton.click();

    // Mobile menu items should now be visible
    const mobileLaunchDashboard = header.getByRole('button', { name: /Launch Dashboard/i });
    
    await expect(mobileLaunchDashboard).toBeVisible();
  });
});
