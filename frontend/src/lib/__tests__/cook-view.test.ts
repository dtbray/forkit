import { describe, it, expect } from 'vitest';
import {
	getStepSize,
	getIngredientSize,
	getSizeMap,
	getIngredientSizeMap,
	TEXT_SIZES,
	DEFAULT_TEXT_SIZE,
	type TextSize
} from '../cook-view-size';

describe('cook-view-size: step size map', () => {
	it('returns correct CSS value for each step size', () => {
		expect(getStepSize('S')).toBe('1.75rem'); // 28px
		expect(getStepSize('M')).toBe('2rem'); // 32px
		expect(getStepSize('L')).toBe('2.25rem'); // 36px
		expect(getStepSize('XL')).toBe('2.625rem'); // 42px
	});

	it('default size is M (32px)', () => {
		expect(DEFAULT_TEXT_SIZE).toBe('M');
		expect(getStepSize(DEFAULT_TEXT_SIZE)).toBe('2rem');
	});

	it('all valid sizes are present in the map', () => {
		const map = getSizeMap();
		TEXT_SIZES.forEach((size) => {
			expect(map).toHaveProperty(size);
			expect(typeof map[size]).toBe('string');
			expect(map[size].length).toBeGreaterThan(0);
		});
	});

	it('getSizeMap returns a copy, not the original reference', () => {
		const a = getSizeMap();
		const b = getSizeMap();
		expect(a).not.toBe(b);
	});
});

describe('cook-view-size: ingredient size map', () => {
	it('returns correct CSS value for each ingredient size', () => {
		expect(getIngredientSize('S')).toBe('1.25rem'); // 20px
		expect(getIngredientSize('M')).toBe('1.375rem'); // 22px
		expect(getIngredientSize('L')).toBe('1.5rem'); // 24px
		expect(getIngredientSize('XL')).toBe('1.75rem'); // 28px
	});

	it('ingredient sizes scale with step sizes (S < M < L < XL)', () => {
		const sizes: TextSize[] = ['S', 'M', 'L', 'XL'];
		const values = sizes.map((s) => parseFloat(getIngredientSize(s)));
		for (let i = 1; i < values.length; i++) {
			expect(values[i]).toBeGreaterThan(values[i - 1]);
		}
	});

	it('all valid sizes are present in ingredient map', () => {
		const map = getIngredientSizeMap();
		TEXT_SIZES.forEach((size) => {
			expect(map).toHaveProperty(size);
		});
	});
});

describe('cook-view-size: step sizes are ordered S < M < L < XL', () => {
	it('step sizes increase monotonically', () => {
		const sizes: TextSize[] = ['S', 'M', 'L', 'XL'];
		const values = sizes.map((s) => parseFloat(getStepSize(s)));
		for (let i = 1; i < values.length; i++) {
			expect(values[i]).toBeGreaterThan(values[i - 1]);
		}
	});
});

describe('cook-view-size: TEXT_SIZES array', () => {
	it('contains exactly S, M, L, XL in order', () => {
		expect(TEXT_SIZES).toEqual(['S', 'M', 'L', 'XL']);
	});
});
