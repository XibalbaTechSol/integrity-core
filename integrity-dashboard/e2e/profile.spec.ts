import { test, expect } from '@playwright/test';

test.describe('Profile Page Logic', () => {
  test.beforeEach(async ({ page }) => {
    // We mock localStorage so that the DashboardProvider initializes auth with our mock user
    await page.addInitScript(() => {
      window.localStorage.setItem('firebase:mock_user', JSON.stringify({
        uid: 'test-user',
        email: 'test@xibalba.io',
        name: 'Test Xibalba User',
        photoURL: 'https://example.com/test-photo.png'
      }));
    });

    // Intercept user profile fetch
    await page.route('**/api/v1/user/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uid: 'test-user',
          email: 'test@xibalba.io',
          name: 'Test Xibalba User',
          photoURL: 'https://example.com/test-photo.png'
        })
      });
    });
    
    // Mock user API keys request
    await page.route('**/api/v1/user/api-keys', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'key-123', created_at: new Date().toISOString() }
          ])
        });
      } else if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'key-new', raw_key: 'sk_test_123', created_at: new Date().toISOString() })
        });
      }
    });

    await page.route('**/api/v1/user/api-keys/*', async (route) => {
      if (route.request().method() === 'DELETE') {
        await route.fulfill({ status: 200, body: JSON.stringify({ success: true }) });
      }
    });

    await page.goto('/integrity/#/integrity#profile');
  });

  test('displays user information and profile picture', async ({ page }) => {
    // Wait for the Profile page to load
    await expect(page.locator('text=Personal Information')).toBeVisible();

    // The name should be rendered
    await expect(page.locator('text=Test Xibalba User')).toBeVisible();
    await expect(page.locator('text=test@xibalba.io')).toBeVisible();

    // Profile photo should be present in the main page
    const profileImg = page.locator('main img[alt="Profile"]');
    await expect(profileImg).toBeVisible();
    await expect(profileImg).toHaveAttribute('src', 'https://example.com/test-photo.png');

    // Sidebar should also render the profile picture
    const sidebarAvatar = page.locator('.sidebar img[alt="Profile"]');
    await expect(sidebarAvatar).toBeVisible();
  });

});
