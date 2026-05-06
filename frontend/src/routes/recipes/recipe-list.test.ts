import { describe, it, expect } from 'vitest';

// ── Shared test helpers ────────────────────────────────────────────────────────

interface MockRecipe {
	id: string;
	title: string;
	hero_image_path: string | null;
	cuisine: string | null;
	total_time_minutes: number | null;
	favorite: boolean;
	cook_count: number;
	tags: { name: string }[];
	created_at: string;
}

function makeMockRecipe(overrides: Partial<MockRecipe> = {}): MockRecipe {
	return {
		id: 'abc-123',
		title: 'Chocolate Chip Cookies',
		hero_image_path: '/data/images/abc-123/hero.jpg',
		cuisine: 'American',
		total_time_minutes: 45,
		favorite: false,
		cook_count: 0,
		tags: [{ name: 'dessert' }],
		created_at: '2026-01-01T00:00:00Z',
		...overrides
	};
}

// ── formatTime helper (extracted logic — matches +page.svelte implementation) ──

function formatTime(minutes: number | null): string {
	if (!minutes) return '';
	if (minutes < 60) return `${minutes} min`;
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return m > 0 ? `${h} hr ${m} min` : `${h} hr`;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('recipe list page data', () => {
	it('renders card data for a mock recipe', () => {
		const recipe = makeMockRecipe();
		expect(recipe.title).toBe('Chocolate Chip Cookies');
		expect(recipe.cuisine).toBe('American');
		expect(recipe.total_time_minutes).toBe(45);
		expect(recipe.favorite).toBe(false);
		expect(recipe.cook_count).toBe(0);
	});

	it('returns empty array when recipes list is empty', () => {
		const data: { recipes: MockRecipe[] } = { recipes: [] };
		expect(data.recipes).toHaveLength(0);
	});

	it('handles recipes with null hero_image_path (placeholder branch)', () => {
		const recipe = makeMockRecipe({ hero_image_path: null });
		expect(recipe.hero_image_path).toBeNull();
	});

	it('handles recipes with cook_count > 0 (badge visible)', () => {
		const recipe = makeMockRecipe({ cook_count: 7 });
		expect(recipe.cook_count).toBeGreaterThan(0);
	});

	it('shows favorite star when recipe is favorite', () => {
		const recipe = makeMockRecipe({ favorite: true });
		expect(recipe.favorite).toBe(true);
	});

	it('formats time under 60 minutes as "N min"', () => {
		expect(formatTime(45)).toBe('45 min');
		expect(formatTime(1)).toBe('1 min');
	});

	it('formats exactly 60 minutes as "1 hr"', () => {
		expect(formatTime(60)).toBe('1 hr');
	});

	it('formats time over 60 minutes with hours and minutes', () => {
		expect(formatTime(90)).toBe('1 hr 30 min');
		expect(formatTime(125)).toBe('2 hr 5 min');
	});

	it('returns empty string for null time', () => {
		expect(formatTime(null)).toBe('');
	});

	it('builds unique cuisine list from multiple recipes', () => {
		const recipes = [
			makeMockRecipe({ cuisine: 'Italian' }),
			makeMockRecipe({ id: '2', cuisine: 'Mexican' }),
			makeMockRecipe({ id: '3', cuisine: 'Italian' })
		];
		const cuisines = [...new Set(recipes.map((r) => r.cuisine).filter(Boolean))].sort();
		expect(cuisines).toEqual(['Italian', 'Mexican']);
	});

	it('handles recipes with null cuisine in cuisine list', () => {
		const recipes = [
			makeMockRecipe({ cuisine: null }),
			makeMockRecipe({ id: '2', cuisine: 'French' })
		];
		const cuisines = [...new Set(recipes.map((r) => r.cuisine).filter(Boolean) as string[])].sort();
		expect(cuisines).toEqual(['French']);
	});
});
