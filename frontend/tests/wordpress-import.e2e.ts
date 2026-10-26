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

test('import updates refresh recipes without resetting filters or pagination', async ({ page }) => {
	let imported = 1;
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: {
		recipes: [{ id: 'live-recipe', title: `Live lentils ${imported}`, hero_image_path: null, cuisine: null, total_time: 'PT20M', cook_count: 0 }],
		total: 100, limit: 50, offset: 50
	} }));
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [{
		source_url: 'https://www.budgetbytes.com/category/recipes/vegetarian/vegan/', name: 'Vegan Recipes', stage: 'importing', total: 10, counts: { imported, pending: 10 - imported }, error: null
	}] } }));
	await page.goto('/recipes?q=lentil&offset=50');
	await expect(page.getByRole('heading', { name: 'Live lentils 1' })).toBeVisible();
	await expect(page.getByLabel('Recipe imports')).toContainText('1 of 10 recipes saved');
	imported = 2;
	await expect(page.getByLabel('Recipe imports')).toContainText('2 of 10 recipes saved', { timeout: 10000 });
	await expect(page.getByRole('heading', { name: 'Live lentils 2' })).toBeVisible();
	await expect(page).toHaveURL(/q=lentil&offset=50/);
	await expect(page.getByLabel('Search recipes by keyword')).toHaveValue('lentil');
	await expect(page.getByRole('progressbar', { name: 'Vegan Recipes import progress' })).toHaveAttribute('value', '2');
});

test('dark mode follows system and remembers an explicit choice', async ({ page }, info) => {
	await page.emulateMedia({ colorScheme: 'dark' });
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: { recipes: [{ id: 'dark-lentils', title: 'Cozy lentil soup', hero_image_path: null, cuisine: null, total_time: 'PT30M', cook_count: 0 }], total: 1, limit: 50, offset: 0 } }));
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [{ source_url: 'https://www.budgetbytes.com/category/recipes/vegetarian/vegan/', name: 'Vegan Recipes', stage: 'importing', total: 297, counts: { imported: 92, existing: 12, pending: 193 }, error: null }] } }));
	await page.goto('/recipes');
	const theme = page.getByRole('combobox', { name: 'Color theme' });
	await expect(theme).toHaveValue('system');
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(24, 23, 21)');
	await page.getByLabel('Recipe imports').waitFor();
	await page.screenshot({ path: info.outputPath('dark-library.png') });
	await theme.selectOption('light');
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(248, 244, 236)');
	await page.reload();
	await expect(theme).toHaveValue('light');
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(248, 244, 236)');
	await theme.selectOption('system');
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(24, 23, 21)');
	await page.emulateMedia({ colorScheme: 'light' });
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(248, 244, 236)');
	await theme.selectOption('dark');
	await page.reload();
	await expect(theme).toHaveValue('dark');
	await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(24, 23, 21)');
	expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test('failed progress requests preserve the last counts and reconnect', async ({ page }) => {
	let unavailable = false;
	let saved = 1;
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: { recipes: [], total: 0, limit: 50, offset: 0 } }));
	await page.route('**/api/imports', route => unavailable ? route.fulfill({ status: 503, body: 'unavailable' }) : route.fulfill({ json: { sources: [{ source_url: 'https://www.budgetbytes.com/category/recipes/vegetarian/vegan/', name: 'Vegan Recipes', stage: 'importing', total: 10, counts: { imported: saved, pending: 10 - saved }, error: null }] } }));
	await page.goto('/recipes');
	await expect(page.getByLabel('Recipe imports')).toContainText('1 of 10 recipes saved');
	unavailable = true;
	await expect(page.getByLabel('Recipe imports')).toContainText('Reconnecting', { timeout: 10000 });
	await expect(page.getByLabel('Recipe imports')).toContainText('1 of 10 recipes saved');
	unavailable = false;
	saved = 2;
	await page.getByRole('button', { name: 'Refresh now' }).click();
	await expect(page.getByLabel('Recipe imports')).toContainText('2 of 10 recipes saved');
	await expect(page.getByLabel('Recipe imports')).toContainText('Live updates');
});

test('photo backfill updates an existing card without a manual refresh', async ({ page }) => {
	let photoReady = false;
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: { recipes: [{ id: 'photo-recipe', title: 'Photo lentils', hero_image_path: photoReady ? 'test-photo/hero.webp' : null, cuisine: null, total_time: 'PT20M', cook_count: 0 }], total: 1, limit: 50, offset: 0 } }));
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [{ source_url: 'https://www.budgetbytes.com/category/recipes/vegetarian/', name: 'Vegetarian Recipes', stage: 'images', total: 1, counts: { imported: 1 }, images: { saved: photoReady ? 1 : 0 }, error: null }] } }));
	await page.route('**/data/images/test-photo/hero.webp', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1" fill="orange"/></svg>' }));
	await page.goto('/recipes');
	await expect(page.getByLabel('Recipe imports')).toContainText('Adding photos');
	await expect(page.locator('.card-hero-img')).toHaveCount(0);
	photoReady = true;
	await expect(page.locator('.card-hero-img')).toBeVisible({ timeout: 10000 });
	await expect(page.getByLabel('Recipe imports')).toContainText('1 photos');
	await expect.poll(() => page.locator('.card-hero-img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
});

test('diet and source filters persist through live refresh and cards request smaller variants', async ({ page }) => {
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: { recipes: [{ id: 'filtered', title: 'Vegan lentils', hero_image_path: 'responsive/hero.webp', thumb_image_path: 'responsive/thumb.webp', medium_image_path: 'responsive/medium.webp', tags: ['vegan'], source_url: 'https://www.budgetbytes.com/lentils/', cuisine: null, total_time: null, cook_count: 0 }], total: 1, limit: 50, offset: 0 } }));
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [] } }));
	const requested: string[] = [];
	await page.route('**/data/images/responsive/*.webp', route => {
		requested.push(route.request().url());
		return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="orange"/></svg>' });
	});
	await page.goto('/recipes');
	await page.getByLabel('Filter by diet', { exact: true }).selectOption('vegan');
	await expect(page).toHaveURL(/tag=vegan/);
	await page.getByLabel('Filter by source', { exact: true }).selectOption('www.budgetbytes.com');
	await expect(page).toHaveURL(/source=www.budgetbytes.com/);
	await page.reload();
	await expect(page.getByLabel('Filter by diet', { exact: true })).toHaveValue('vegan');
	await expect(page.getByLabel('Filter by source', { exact: true })).toHaveValue('www.budgetbytes.com');
	await expect(page.locator('.card-hero-img')).toHaveAttribute('srcset', /thumb.webp 320w/);
	await expect.poll(() => requested.length).toBeGreaterThan(0);
	expect(requested.every(url => !url.endsWith('/hero.webp'))).toBe(true);
});
