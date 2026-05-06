import { test, expect } from '@playwright/test';

test('cook view renders split-pane layout on iPad', async ({ page }) => {
	// Set iPad Pro 12.9" landscape viewport
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');
	await expect(page.locator('.cook-layout')).toBeVisible();
	await expect(page.locator('.ingredient-pane')).toBeVisible();
	await expect(page.locator('.step-pane')).toBeVisible();
});

test('type-size toggle persists across reload', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	// Click the XL size button
	await page.click('[data-size="XL"]');

	// Verify it became selected
	await expect(page.locator('[data-size="XL"]')).toHaveAttribute('aria-checked', 'true');

	// Reload and confirm persistence
	await page.reload();
	const selected = await page.getAttribute('[aria-checked="true"][data-size]', 'data-size');
	expect(selected).toBe('XL');
});

test('cook view header is present with title and done button', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	await expect(page.locator('.cook-header')).toBeVisible();
	await expect(page.locator('.header-title')).toContainText('Chocolate Chip Cookies');
	await expect(page.locator('.done-btn')).toBeVisible();
});

test('ingredient checklist renders all items', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	// 9 ingredients in mock data
	const checkboxes = page.locator('.ingredient-checkbox');
	await expect(checkboxes).toHaveCount(9);
});

test('step nav prev/next buttons are present', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	await expect(page.getByRole('button', { name: 'Previous step' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Next step' })).toBeVisible();
});

test('prev button is disabled on step 1', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	const prevBtn = page.getByRole('button', { name: 'Previous step' });
	await expect(prevBtn).toBeDisabled();
});

test('next step advances the step indicator', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	// Initially on step 1
	await expect(page.locator('.step-indicator-text')).toContainText('Step 1 of 8');

	// Advance
	await page.getByRole('button', { name: 'Next step' }).click();

	// Now on step 2
	await expect(page.locator('.step-indicator-text')).toContainText('Step 2 of 8');
});

test('type-size toggle has correct ARIA radiogroup role', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	await expect(page.locator('[role="radiogroup"][aria-label="Step text size"]')).toBeVisible();

	// All 4 segments present
	for (const size of ['S', 'M', 'L', 'XL']) {
		await expect(page.locator(`[data-size="${size}"]`)).toBeVisible();
	}
});

test('ingredient checkbox toggles checked state', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	const firstCheckbox = page.locator('.ingredient-checkbox').first();
	await expect(firstCheckbox).not.toBeChecked();

	await firstCheckbox.click();
	await expect(firstCheckbox).toBeChecked();
});

test('"We made this" sheet appears when done is tapped', async ({ page }) => {
	await page.setViewportSize({ width: 1366, height: 1024 });
	await page.goto('/cook/mock-uuid');

	await page.click('.done-btn');
	await expect(page.getByRole('dialog', { name: 'Did you make it?' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'We made it' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Not this time' })).toBeVisible();
});
