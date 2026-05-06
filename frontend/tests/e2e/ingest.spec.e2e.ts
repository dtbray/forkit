import { test, expect } from '@playwright/test';

test('URL input submits and enters loading state', async ({ page }) => {
	await page.goto('/ingest');
	await page.fill('input[type="url"]', 'https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/');
	await page.click('button[type="submit"]');
	// Should see loading state (mocked in dev)
	await expect(page.locator('[data-state="loading"]')).toBeVisible({ timeout: 2000 });
});

test('invalid URL shows validation error', async ({ page }) => {
	await page.goto('/ingest');
	await page.fill('input[type="url"]', 'notaurl');
	await page.click('button[type="submit"]');
	await expect(page.locator('[data-error="url"]')).toBeVisible();
});

test('submit button is disabled when input is empty', async ({ page }) => {
	await page.goto('/ingest');
	const submitBtn = page.locator('button[type="submit"]');
	await expect(submitBtn).toBeDisabled();
});

test('submit button enables when valid URL is entered', async ({ page }) => {
	await page.goto('/ingest');
	await page.fill('input[type="url"]', 'https://example.com/recipe');
	const submitBtn = page.locator('button[type="submit"]');
	await expect(submitBtn).not.toBeDisabled();
});

test('clear button removes input text', async ({ page }) => {
	await page.goto('/ingest');
	await page.fill('input[type="url"]', 'https://example.com/recipe');
	await page.click('button[aria-label="Clear URL"]');
	await expect(page.locator('input[type="url"]')).toHaveValue('');
});

test('prefill param from share target pre-fills the input', async ({ page }) => {
	const url = 'https://www.seriouseats.com/recipes/something';
	await page.goto(`/ingest?prefill=${encodeURIComponent(url)}`);
	await expect(page.locator('input[type="url"]')).toHaveValue(url);
});
