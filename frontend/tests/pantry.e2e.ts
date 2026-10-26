import { test, expect } from '@playwright/test';

test('dictated text is reviewed, failed saves keep edits, and stock survives reload', async ({ page }) => {
	let items: { id: number; name: string; quantity: string | null; unit: string | null; notes: string | null }[] = [];
	let saves = 0;
	let fail = true;
	await page.route(/\/api\/pantry$/, route => route.fulfill({ json: { items } }));
	await page.route('**/api/pantry/capabilities', route => route.fulfill({ json: { photo_enabled: false, chatgpt_connected: false } }));
	await page.route('**/api/pantry/recipes', route => route.fulfill({ json: { recipes: [] } }));
	await page.route('**/api/pantry/preview/text', async route => {
		expect(route.request().postDataJSON().text).toContain('next item');
		return route.fulfill({ json: { items: [
			{ name: 'eggs', quantity: '2', unit: null, notes: null },
			{ name: 'spinach', quantity: null, unit: null, notes: null }
		] } });
	});
	await page.route('**/api/pantry/items', async route => {
		saves++;
		if (fail) return route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable. Your review is still here.' } });
		items = route.request().postDataJSON().items.map((item: object, index: number) => ({ ...item, id: index + 1 }));
		return route.fulfill({ json: { added: items.length, already_present: 0 } });
	});
	await page.goto('/pantry');
	await expect(page.getByRole('heading', { name: 'What’s on hand?' })).toBeVisible();
	const text = page.getByLabel('Type or dictate your ingredients');
	await text.fill('2 eggs next item spinach');
	await expect(text).toHaveAttribute('inputmode', 'text');
	await page.getByRole('button', { name: 'Review ingredients' }).click();
	await page.getByLabel('Amount', { exact: true }).first().fill('3');
	await page.getByLabel('Include ingredient 2').uncheck();
	expect(saves).toBe(0);
	await page.getByRole('button', { name: 'Add 1 to pantry' }).click();
	await expect(page.getByRole('alert')).toContainText('Your review is still here');
	await expect(page.getByLabel('Amount', { exact: true }).first()).toHaveValue('3');
	fail = false;
	await page.getByRole('button', { name: 'Add 1 to pantry' }).click();
	await expect(page.getByRole('button', { name: 'Remove eggs from pantry' })).toBeVisible();
	expect(items).toEqual([{ id: 1, name: 'eggs', quantity: '3', unit: null, notes: null }]);
	await page.reload();
	await expect(page.getByRole('button', { name: 'Remove eggs from pantry' })).toBeVisible();
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('camera and library photo upload produce editable candidates without saving', async ({ page }) => {
	let previews = 0;
	await page.route(/\/api\/pantry$/, route => route.fulfill({ json: { items: [] } }));
	await page.route('**/api/pantry/recipes', route => route.fulfill({ json: { recipes: [] } }));
	await page.route('**/api/pantry/capabilities', route => route.fulfill({ json: { photo_enabled: true, chatgpt_connected: true, model: 'vision-test' } }));
	await page.route('**/api/pantry/preview/photo', async route => {
		previews++;
		expect(route.request().headers()['content-type']).toBe('image/jpeg');
		return route.fulfill({ json: { items: [{ name: 'tomatoes', quantity: null, unit: null, notes: 'Check variety' }] } });
	});
	await page.goto('/pantry');
	await expect(page.getByLabel('Take a pantry photo')).toHaveAttribute('capture', 'environment');
	const data = await page.evaluate(() => {
		const canvas = document.createElement('canvas'); canvas.width = 2; canvas.height = 2;
		canvas.getContext('2d')!.fillRect(0, 0, 2, 2); return canvas.toDataURL('image/png').split(',')[1];
	});
	await page.getByLabel('Choose a pantry photo').setInputFiles({ name: 'kitchen.png', mimeType: 'image/png', buffer: Buffer.from(data, 'base64') });
	await expect(page.getByLabel('Name', { exact: true })).toHaveValue('tomatoes');
	await page.getByLabel('Name', { exact: true }).fill('cherry tomatoes');
	await expect(page.getByLabel('Notes')).toHaveValue('Check variety');
	expect(previews).toBe(1);
	await page.getByRole('button', { name: 'Discard review' }).click();
	await expect(page.getByText('Your pantry is ready for its first ingredients.')).toBeVisible();
	await page.screenshot({ path: `/tmp/forkit-pantry-${test.info().project.name}.png`, fullPage: true });
    await page.getByLabel('Color theme').selectOption('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.screenshot({ path: `/tmp/forkit-pantry-${test.info().project.name}-dark.png`, fullPage: true });
});
