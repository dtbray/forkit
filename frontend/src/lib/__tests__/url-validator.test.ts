import { isValidRecipeUrl, looksLikeUrl } from '../url-validator';
import { describe, it, expect } from 'vitest';

describe('isValidRecipeUrl', () => {
	it('accepts https', () =>
		expect(isValidRecipeUrl('https://example.com/recipe')).toBe(true));
	it('accepts http', () =>
		expect(isValidRecipeUrl('http://example.com/recipe')).toBe(true));
	it('rejects ftp', () =>
		expect(isValidRecipeUrl('ftp://example.com')).toBe(false));
	it('rejects bare word', () =>
		expect(isValidRecipeUrl('notaurl')).toBe(false));
	it('rejects empty string', () =>
		expect(isValidRecipeUrl('')).toBe(false));
	it('rejects javascript: protocol', () =>
		expect(isValidRecipeUrl('javascript:alert(1)')).toBe(false));
});

describe('looksLikeUrl', () => {
	it('detects http url', () =>
		expect(looksLikeUrl('http://example.com')).toBe(true));
	it('detects https url', () =>
		expect(looksLikeUrl('https://www.allrecipes.com/recipe/123')).toBe(true));
	it('rejects plain text', () =>
		expect(looksLikeUrl('pasta recipe')).toBe(false));
	it('handles leading whitespace', () =>
		expect(looksLikeUrl('  https://example.com')).toBe(true));
	it('rejects ftp', () =>
		expect(looksLikeUrl('ftp://example.com')).toBe(false));
});
