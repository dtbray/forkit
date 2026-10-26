import { test, expect } from '@playwright/test';

test('recipe changes persist after reload and unsuccessful saves retain edits', async ({ page }) => {
	let unavailable = false;
	let deleted = false;
	let recipe = {
		id: 'test-recipe', title: 'Lemon pasta', description: null, source_url: 'https://example.com/pasta',
		hero_image_path: null, cuisine: null, yield_text: '2 servings', prep_time: null, cook_time: null,
		total_time: null, favorite: false, cook_count: 0, last_cooked: null, rating: null as number | null,
		user_notes: null as string | null, meal_type: null, parser_source: 'jsonld', parser_confidence: 1,
		ingredients: [], tags: [], instructions: '["Cook pasta"]'
	};
	await page.route('**/api/recipes/test-recipe', async route => {
		if (route.request().method() === 'PATCH') {
			if (unavailable) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
			recipe = { ...recipe, ...route.request().postDataJSON() };
		} else if (route.request().method() === 'DELETE') {
			if (unavailable) return route.fulfill({ status: 503 });
			deleted = true;
			return route.fulfill({ status: 204 });
		}
		return route.fulfill({ json: recipe });
	});
	await page.route(/\/api\/recipes(\?.*)?$/, route => route.fulfill({ json: { recipes: [], total: 0, limit: 50, offset: 0 } }));
	await page.route('**/api/imports', route => route.fulfill({ json: { sources: [] } }));
	await page.goto('/recipes/test-recipe');
	await page.getByRole('button', { name: 'Add to favorites' }).click();
	await expect(page.getByRole('button', { name: 'Remove from favorites' })).toHaveAttribute('aria-pressed', 'true');
	await page.getByLabel('Your rating').selectOption('4');
	const notes = page.getByLabel('Personal notes about this recipe');
	await notes.fill('Use extra lemon');
	await notes.blur();
	await expect.poll(() => recipe.user_notes).toBe('Use extra lemon');
	await page.reload();
	await expect(notes).toHaveValue('Use extra lemon');
	await expect(page.getByLabel('Your rating')).toHaveValue('4');
	await expect(page.getByRole('button', { name: 'Remove from favorites' })).toHaveAttribute('aria-pressed', 'true');

	unavailable = true;
	await notes.fill('Do not lose this edit');
	await notes.blur();
	await expect(page.getByRole('alert')).toContainText('Notes could not be saved');
	await expect(notes).toHaveValue('Do not lose this edit');
	await page.getByRole('button', { name: 'Remove from favorites' }).click();
	await expect(page.getByRole('alert')).toContainText('Favorite could not be saved');
	await expect(page.getByRole('button', { name: 'Remove from favorites' })).toHaveAttribute('aria-pressed', 'true');
	page.on('dialog', dialog => dialog.accept());
	await page.getByRole('button', { name: 'Delete this recipe permanently' }).click();
	await expect(page.getByRole('alert')).toContainText('Recipe could not be deleted');
	expect(deleted).toBe(false);
	unavailable = false;
	await page.getByRole('button', { name: 'Delete this recipe permanently' }).click();
	await expect(page).toHaveURL('/recipes');
	expect(deleted).toBe(true);
});
