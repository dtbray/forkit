import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:8080';
const RECIPE_1_URL = 'https://natashaskitchen.com/chicken-tortilla-soup-recipe/';
const RECIPE_2_URL = 'https://www.cookingclassy.com/grilled-chicken-and-avocado-street-tacos/';

// Must run serially — later steps depend on UUIDs captured in earlier steps
test.describe.configure({ mode: 'serial' });

test.describe('Forkit Live Exercise', () => {
	let recipe1UUID: string;
	let recipe2UUID: string;

	async function ingestAndGetUUID(page: import('@playwright/test').Page, url: string): Promise<string> {
		await page.goto(`${BASE_URL}/ingest`);
		await page.fill('input[type="url"]', url);
		await page.click('button:has-text("save it")');

		// Wait for either a redirect to the recipe detail page or the duplicate-detection alert
		await Promise.race([
			page.waitForURL(/\/recipes\/[a-f0-9-]+/, { timeout: 45000 }),
			page.getByText("You've got this one").waitFor({ timeout: 45000 }),
			page.getByText("already in your vault").waitFor({ timeout: 45000 }),
		]);

		// If still on /ingest, the duplicate UI fired — click through to the recipe
		if (page.url().includes('/ingest')) {
			const openBtn = page.getByRole('link', { name: /open it/i })
				.or(page.getByRole('button', { name: /open it/i }));
			await openBtn.click();
			await page.waitForURL(/\/recipes\/[a-f0-9-]+/, { timeout: 10000 });
		}

		const match = page.url().match(/\/recipes\/([a-f0-9-]+)/);
		expect(match, `Expected recipe UUID in URL, got: ${page.url()}`).toBeTruthy();
		return match![1];
	}

	test('Step 1: Ingest Recipe 1 (Chicken Tortilla Soup)', async ({ page }) => {
		recipe1UUID = await ingestAndGetUUID(page, RECIPE_1_URL);
		await page.screenshot({ path: 'test-results/01-recipe1-detail.png' });
		const title = await page.title();
		expect(title.toLowerCase()).toMatch(/chicken|tortilla|soup/);
	});

	test('Step 2: Ingest Recipe 2 (Grilled Chicken Tacos)', async ({ page }) => {
		recipe2UUID = await ingestAndGetUUID(page, RECIPE_2_URL);
		await page.screenshot({ path: 'test-results/02-recipe2-detail.png' });
		const title = await page.title();
		expect(title.toLowerCase()).toMatch(/chicken|taco|grilled|avocado/);
	});

	test('Step 3: Browse Recipe Library', async ({ page }) => {
		await page.goto(`${BASE_URL}/recipes`);
		await expect(page).toHaveURL(/\/recipes/);
		const cards = page.locator('a[href*="/recipes/"]');
		await expect(cards.first()).toBeVisible({ timeout: 5000 });
		expect(await cards.count()).toBeGreaterThanOrEqual(2);
		await page.screenshot({ path: 'test-results/03-library.png' });
	});

	test('Step 4: Cook View', async ({ page }) => {
		// Fall back to API lookup if UUID wasn't captured (e.g. step 1 skipped)
		if (!recipe1UUID) {
			const data = await fetch(`${BASE_URL}/api/recipes`).then(r => r.json());
			recipe1UUID = data.recipes[0]?.id;
		}
		expect(recipe1UUID, 'recipe1UUID required for cook view test').toBeTruthy();

		await page.goto(`${BASE_URL}/recipes/${recipe1UUID}`);
		await expect(page).toHaveURL(new RegExp(`/recipes/${recipe1UUID}`));

		const cookBtn = page.getByRole('button', { name: /start cooking|cook/i })
			.or(page.getByRole('link', { name: /cook/i }));
		await cookBtn.click();

		await page.waitForURL(new RegExp(`/cook/${recipe1UUID}`), { timeout: 10000 });
		const main = page.locator('main');
		await expect(main).toBeVisible();

		await page.screenshot({ path: 'test-results/04-cook-view.png' });
	});

	test('Step 5: Home Screen Suggestion', async ({ page }) => {
		await page.goto(`${BASE_URL}/`);
		await expect(page).toHaveURL(/\/$/);
		// Tonight card or any content renders without JS error
		await expect(page.locator('main')).toBeVisible({ timeout: 5000 });
		await page.screenshot({ path: 'test-results/05-home.png' });
	});
});
