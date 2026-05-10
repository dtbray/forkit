import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:8080';

// Fetch a recipe ID before tests need it
async function getFirstRecipe(request: import('@playwright/test').APIRequestContext) {
	const res = await request.get(`${BASE}/api/recipes`);
	const { recipes } = await res.json();
	return recipes[0] as { id: string; title: string };
}

// Navigate to cook page for a given recipe
async function goToCookPage(page: import('@playwright/test').Page, recipeId: string) {
	await page.goto(`${BASE}/recipes/${recipeId}`);
	// "Start Cooking" is an <a> in the fixed footer
	await page.getByRole('link', { name: /start cooking/i }).click();
	await page.waitForURL(`${BASE}/cook/${recipeId}`);
}

test.describe('Option C — Cook Flow Regression', () => {

	test('Sticky CTA visible without scrolling on detail page', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await page.goto(`${BASE}/recipes/${recipe.id}`);

		const cta = page.getByRole('link', { name: /start cooking/i });
		await expect(cta).toBeVisible();

		// Must be in viewport on first paint (no scroll required)
		const box = await cta.boundingBox();
		const vh = page.viewportSize()?.height ?? 800;
		expect(box).not.toBeNull();
		expect(box!.y + box!.height).toBeLessThanOrEqual(vh);
	});

	test('Cook page loads real recipe data (not mock "Chocolate Chip Cookies")', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		// Header title should match real recipe
		const header = page.locator('.header-title');
		await expect(header).toBeVisible();
		const text = await header.textContent();
		expect(text?.trim()).toBe(recipe.title);
		expect(text?.trim()).not.toBe('Chocolate Chip Cookies');
	});

	test('Done → We made it → Logged! confirmation with navigation buttons', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		// Open the sheet
		await page.getByRole('button', { name: 'Done cooking' }).click();

		// Prompt state: "Did you make it?" heading and buttons
		await expect(page.getByRole('heading', { name: 'Did you make it?' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'We made it' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Not this time' })).toBeVisible();

		// Confirm — triggers POST and transitions to success state
		await page.getByRole('button', { name: 'We made it' }).click();

		// Success state: "Logged! Cook #N"
		const successHeading = page.locator('.sheet-heading');
		await expect(successHeading).toContainText('Logged!', { timeout: 5000 });
		await expect(successHeading).toContainText('Cook #');

		// Navigation buttons present
		await expect(page.getByRole('button', { name: 'Browse recipes' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Back to recipe' })).toBeVisible();
	});

	test('Success sheet: "Browse recipes" navigates to /recipes', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		await page.getByRole('button', { name: 'Done cooking' }).click();
		await page.getByRole('button', { name: 'We made it' }).click();
		await expect(page.locator('.sheet-heading')).toContainText('Logged!', { timeout: 5000 });

		await page.getByRole('button', { name: 'Browse recipes' }).click();
		await page.waitForURL(`${BASE}/recipes`);
		expect(page.url()).toBe(`${BASE}/recipes`);
	});

	test('Success sheet: "Back to recipe" navigates to detail page', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		await page.getByRole('button', { name: 'Done cooking' }).click();
		await page.getByRole('button', { name: 'We made it' }).click();
		await expect(page.locator('.sheet-heading')).toContainText('Logged!', { timeout: 5000 });

		await page.getByRole('button', { name: 'Back to recipe' }).click();
		await page.waitForURL(`${BASE}/recipes/${recipe.id}`);
		expect(page.url()).toContain(`/recipes/${recipe.id}`);
	});

	test('"Not this time" closes sheet and stays on cook page', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		const cookUrl = page.url();
		await page.getByRole('button', { name: 'Done cooking' }).click();
		await expect(page.getByRole('heading', { name: 'Did you make it?' })).toBeVisible();

		// Click "Not this time" scoped inside the sheet dialog
		await page.locator('[role="dialog"]').getByRole('button', { name: 'Not this time' }).click();

		// Sheet gone, still on cook page
		await expect(page.getByRole('heading', { name: 'Did you make it?' })).not.toBeVisible();
		expect(page.url()).toBe(cookUrl);
	});

	test('Sheet resets to prompt state after closing and reopening', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		// Open, confirm, reach success state
		await page.getByRole('button', { name: 'Done cooking' }).click();
		await page.getByRole('button', { name: 'We made it' }).click();
		await expect(page.locator('.sheet-heading')).toContainText('Logged!', { timeout: 5000 });

		// Close via backdrop
		await page.locator('.sheet-backdrop').click();
		await expect(page.getByRole('dialog')).not.toBeVisible();

		// Reopen — must be back to prompt state, not success
		await page.getByRole('button', { name: 'Done cooking' }).click();
		await expect(page.getByRole('heading', { name: 'Did you make it?' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'We made it' })).toBeVisible();
	});

	test('Portrait ingredient chip contains chevron and toggles', async ({ page, request }) => {
		// Set viewport to portrait/mobile to trigger portrait mode
		await page.setViewportSize({ width: 390, height: 844 });

		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		// Portrait chip should be visible
		const chip = page.locator('.ingredient-chip-btn');
		await expect(chip).toBeVisible();

		// Chevron must be present
		const chevron = chip.locator('.chip-chevron');
		await expect(chevron).toBeVisible();

		// Panel is closed by default
		const panel = page.locator('#portrait-ingredient-panel');
		await expect(panel).not.toBeVisible();

		// Click opens panel
		await chip.click();
		await expect(panel).toBeVisible();

		// Click again closes panel
		await chip.click();
		await expect(panel).not.toBeVisible();
	});

	test('Back link on cook page returns to recipe detail', async ({ page, request }) => {
		const recipe = await getFirstRecipe(request);
		await goToCookPage(page, recipe.id);

		// Header back link has aria-label="Back to recipe"
		await page.getByRole('link', { name: 'Back to recipe' }).click();
		await page.waitForURL(`${BASE}/recipes/${recipe.id}`);
		expect(page.url()).toContain(`/recipes/${recipe.id}`);
	});
});
