import { test, expect } from '@playwright/test';

test('library shows import progress and pages through all recipes', async ({ page }, info) => {
	await page.route(/\/api\/recipes(\?.*)?$/, async route => {
		const offset = Number(new URL(route.request().url()).searchParams.get('offset') ?? 0);
		await route.fulfill({ json: {
			recipes: Array.from({ length: 50 }, (_, i) => ({ id: String(offset + i), title: `Lentils ${offset + i + 1}`, hero_image_path: null, cuisine: null, total_time: 'PT20M', cook_count: 0 })),
			total: 101, limit: 50, offset
		} });
	});
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [{
		source_url: 'https://www.budgetbytes.com/category/recipes/vegetarian/', name: 'Vegetarian Recipes', stage: 'importing', total: 941, counts: { imported: 101, pending: 840 }, error: null
	}] } }));
	await page.goto('/recipes');
	await expect(page.getByLabel('Recipe imports')).toContainText('101 of 941 recipes saved');
	await expect(page.getByRole('heading', { name: 'Lentils 1', exact: true })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Previous', exact: true })).toBeDisabled();
	await page.screenshot({ path: info.outputPath('library-import-progress.png') });
	await page.getByRole('button', { name: 'Next', exact: true }).click();
	await expect(page).toHaveURL(/offset=50/);
	await expect(page.getByRole('heading', { name: 'Lentils 51', exact: true })).toBeVisible();
	await expect(page.getByLabel('Recipe pages')).toContainText('51–100 of 101');
	await expect(page.getByRole('button', { name: 'Previous', exact: true })).toBeEnabled();
	const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
	expect(overflow).toBe(false);
});
