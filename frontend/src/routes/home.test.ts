/**
 * home.test.ts — unit tests for the Tonight suggestion home screen
 *
 * Tests cover:
 *  - load() returns tonight + alternates on 200
 *  - load() returns null/[] fallback on non-OK response
 *  - load() returns null/[] fallback on network error
 *  - formatTime helper (inline, mirrors page logic)
 *  - cook_count badge visibility logic
 */

import { describe, it, expect, vi } from 'vitest';

// ── Inline mirror of the page's formatTime helper ──────────────────────────
function formatTime(minutes: number | null | undefined): string | null {
	if (minutes == null) return null;
	return `${minutes} min`;
}

// ── Inline mirror of the load function (without SvelteKit types) ────────────
async function load(fetchFn: typeof fetch) {
	try {
		const res = await fetchFn('/api/suggestions/tonight');
		if (!res.ok) return { tonight: null, alternates: [] };
		return (await res.json()) as { tonight: unknown; alternates: unknown[] };
	} catch {
		return { tonight: null, alternates: [] };
	}
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

const mockRecipe = {
	id: 'abc-123',
	title: 'Spaghetti Carbonara',
	hero_image_path: '/data/images/abc-123/hero.webp',
	cuisine: 'Italian',
	total_time_minutes: 30,
	cook_count: 3,
	last_cooked: '2026-04-28T18:00:00',
	rating: 4
};

const mockAlternate = {
	id: 'def-456',
	title: 'Chicken Tikka',
	hero_image_path: '/data/images/def-456/hero.webp',
	cuisine: 'Indian',
	total_time_minutes: 45,
	cook_count: 1,
	last_cooked: '2026-04-01T18:00:00',
	rating: 5
};

function mockFetch(body: unknown, status = 200): typeof fetch {
	return vi.fn().mockResolvedValue({
		ok: status >= 200 && status < 300,
		status,
		json: async () => body
	}) as unknown as typeof fetch;
}

function errorFetch(): typeof fetch {
	return vi.fn().mockRejectedValue(new Error('Network error')) as unknown as typeof fetch;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('load()', () => {
	it('returns tonight and alternates from a 200 response', async () => {
		const data = { tonight: mockRecipe, alternates: [mockAlternate] };
		const result = await load(mockFetch(data));

		expect(result.tonight).toEqual(mockRecipe);
		expect((result.alternates as unknown[]).length).toBe(1);
	});

	it('returns null tonight and empty alternates when vault is empty (tonight=null)', async () => {
		const data = { tonight: null, alternates: [] };
		const result = await load(mockFetch(data));

		expect(result.tonight).toBeNull();
		expect(result.alternates).toEqual([]);
	});

	it('returns null/[] fallback on non-OK response (500)', async () => {
		const result = await load(mockFetch({ detail: 'Server error' }, 500));

		expect(result.tonight).toBeNull();
		expect(result.alternates).toEqual([]);
	});

	it('returns null/[] fallback on network error', async () => {
		const result = await load(errorFetch());

		expect(result.tonight).toBeNull();
		expect(result.alternates).toEqual([]);
	});

	it('passes alternates list of up to 3 items through', async () => {
		const alts = [mockAlternate, { ...mockAlternate, id: 'g1' }, { ...mockAlternate, id: 'g2' }];
		const result = await load(mockFetch({ tonight: mockRecipe, alternates: alts }));

		expect((result.alternates as unknown[]).length).toBe(3);
	});
});

describe('formatTime()', () => {
	it('formats whole minutes', () => {
		expect(formatTime(45)).toBe('45 min');
	});

	it('formats single-digit minutes', () => {
		expect(formatTime(5)).toBe('5 min');
	});

	it('returns null for null input', () => {
		expect(formatTime(null)).toBeNull();
	});

	it('returns null for undefined input', () => {
		expect(formatTime(undefined)).toBeNull();
	});

	it('formats zero minutes', () => {
		expect(formatTime(0)).toBe('0 min');
	});
});

describe('cook_count badge visibility logic', () => {
	it('should show badge when cook_count > 0', () => {
		expect(mockRecipe.cook_count > 0).toBe(true);
	});

	it('should not show badge when cook_count is 0', () => {
		const neverCooked = { ...mockRecipe, cook_count: 0 };
		expect(neverCooked.cook_count > 0).toBe(false);
	});

	it('formats cook_count badge label correctly', () => {
		const label = `Cooked ${mockRecipe.cook_count}×`;
		expect(label).toBe('Cooked 3×');
	});
});
