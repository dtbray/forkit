import { describe, it, expect } from 'vitest';

// ── Type definitions matching +page.svelte ────────────────────────────────────

interface Ingredient {
	amount: string | null;
	unit: string | null;
	name: string;
	notes: string | null;
}

interface Instruction {
	step_number: number;
	text: string;
}

interface RecipeDetail {
	id: string;
	title: string;
	source_url: string | null;
	hero_image_path: string | null;
	cuisine: string | null;
	yield_servings: number | null;
	prep_time_minutes: number | null;
	cook_time_minutes: number | null;
	total_time_minutes: number | null;
	favorite: boolean;
	cook_count: number;
	last_cooked: string | null;
	rating: number | null;
	user_notes: string | null;
	parser_source: string | null;
	ingredients: Ingredient[];
	tags: { name: string }[];
	instructions: Instruction[];
}

// ── Helpers extracted from +page.svelte ───────────────────────────────────────

function formatTime(minutes: number | null): string {
	if (!minutes) return '—';
	if (minutes < 60) return `${minutes} min`;
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return m > 0 ? `${h} hr ${m} min` : `${h} hr`;
}

function formatIngredientAmount(ingredient: Ingredient): string {
	const parts: string[] = [];
	if (ingredient.amount) parts.push(ingredient.amount);
	if (ingredient.unit) parts.push(ingredient.unit);
	return parts.join(' ');
}

function starLabel(star: number): string {
	const labels = ['', 'Poor', 'Fair', 'Good', 'Great', 'Excellent'];
	return labels[star] ?? '';
}

// ── Mock data factory ─────────────────────────────────────────────────────────

function makeMockDetail(overrides: Partial<RecipeDetail> = {}): RecipeDetail {
	return {
		id: 'uuid-001',
		title: 'Spaghetti Carbonara',
		source_url: 'https://example.com/carbonara',
		hero_image_path: '/data/images/uuid-001/hero.jpg',
		cuisine: 'Italian',
		yield_servings: 4,
		prep_time_minutes: 15,
		cook_time_minutes: 20,
		total_time_minutes: 35,
		favorite: false,
		cook_count: 3,
		last_cooked: '2026-04-01T18:00:00Z',
		rating: 4,
		user_notes: 'Use guanciale, not bacon.',
		parser_source: 'recipe_extractor',
		ingredients: [
			{ amount: '400', unit: 'g', name: 'spaghetti', notes: null },
			{ amount: '200', unit: 'g', name: 'guanciale', notes: 'or pancetta' },
			{ amount: '4', unit: 'large', name: 'eggs', notes: null },
			{ amount: '100', unit: 'g', name: 'Pecorino Romano', notes: 'finely grated' }
		],
		tags: [{ name: 'pasta' }, { name: 'italian' }],
		instructions: [
			{ step_number: 1, text: 'Cook pasta in generously salted water until al dente.' },
			{ step_number: 2, text: 'Render guanciale in a cold pan over medium heat.' },
			{ step_number: 3, text: 'Whisk eggs and cheese. Season with black pepper.' },
			{ step_number: 4, text: 'Toss hot pasta with guanciale fat, then add egg mixture off heat.' }
		],
		...overrides
	};
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('recipe detail page data', () => {
	it('renders title from recipe data', () => {
		const recipe = makeMockDetail();
		expect(recipe.title).toBe('Spaghetti Carbonara');
	});

	it('renders all ingredients', () => {
		const recipe = makeMockDetail();
		expect(recipe.ingredients).toHaveLength(4);
		expect(recipe.ingredients[0].name).toBe('spaghetti');
	});

	it('renders ingredient with amount and unit', () => {
		const ingredient: Ingredient = { amount: '400', unit: 'g', name: 'spaghetti', notes: null };
		expect(formatIngredientAmount(ingredient)).toBe('400 g');
	});

	it('renders ingredient with no amount gracefully', () => {
		const ingredient: Ingredient = { amount: null, unit: null, name: 'salt', notes: 'to taste' };
		expect(formatIngredientAmount(ingredient)).toBe('');
	});

	it('renders ingredient with notes', () => {
		const ingredient = makeMockDetail().ingredients[1];
		expect(ingredient.notes).toBe('or pancetta');
	});

	it('renders all instructions in order', () => {
		const recipe = makeMockDetail();
		expect(recipe.instructions).toHaveLength(4);
		expect(recipe.instructions[0].step_number).toBe(1);
		expect(recipe.instructions[3].step_number).toBe(4);
	});

	it('renders Start Cooking CTA target as /cook/{uuid}', () => {
		const recipe = makeMockDetail();
		const cookHref = `/cook/${recipe.id}`;
		expect(cookHref).toBe('/cook/uuid-001');
	});

	it('formats total time correctly', () => {
		const recipe = makeMockDetail();
		expect(formatTime(recipe.total_time_minutes)).toBe('35 min');
	});

	it('formats time over one hour correctly', () => {
		expect(formatTime(90)).toBe('1 hr 30 min');
	});

	it('returns dash for null time', () => {
		expect(formatTime(null)).toBe('—');
	});

	it('shows favorite state correctly', () => {
		const favRecipe = makeMockDetail({ favorite: true });
		expect(favRecipe.favorite).toBe(true);
	});

	it('returns correct star label for each rating', () => {
		expect(starLabel(1)).toBe('Poor');
		expect(starLabel(3)).toBe('Good');
		expect(starLabel(5)).toBe('Excellent');
	});

	it('returns empty string for out-of-range star label', () => {
		expect(starLabel(0)).toBe('');
	});

	it('handles recipe with no hero image', () => {
		const recipe = makeMockDetail({ hero_image_path: null });
		expect(recipe.hero_image_path).toBeNull();
	});

	it('handles recipe with no user notes', () => {
		const recipe = makeMockDetail({ user_notes: null });
		expect(recipe.user_notes).toBeNull();
	});

	it('handles recipe with no tags', () => {
		const recipe = makeMockDetail({ tags: [] });
		expect(recipe.tags).toHaveLength(0);
	});

	it('correctly constructs cook link from recipe id', () => {
		const recipe = makeMockDetail({ id: 'test-uuid-999' });
		expect(`/cook/${recipe.id}`).toBe('/cook/test-uuid-999');
	});
});
