import { test, expect } from '@playwright/test';

test('home page loads', async ({ page }) => {
	await page.goto('/');
	await expect(page).toHaveTitle(/forkit/i);
});

test('manifest is linked', async ({ page }) => {
	await page.goto('/');
	const manifest = page.locator('link[rel="manifest"]');
	await expect(manifest).toHaveCount(1);
});

test('Tonight tab is active by default', async ({ page }) => {
	await page.goto('/');
	const tonightTab = page.getByRole('tab', { name: 'Tonight' });
	await expect(tonightTab).toHaveAttribute('aria-selected', 'true');
});

test('Library tab switches panel', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('tab', { name: 'Library' }).click();
	const libraryPanel = page.getByRole('tabpanel', { name: 'Library' });
	await expect(libraryPanel).toBeVisible();
});
