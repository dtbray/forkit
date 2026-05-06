import { describe, it, expect } from 'vitest';

describe('self-hosted fonts', () => {
	it('font packages are importable', async () => {
		// Verify the imports do not throw — confirms packages are present in the bundle
		await import('@fontsource-variable/inter');
		await import('@fontsource-variable/source-serif-4');
		expect(true).toBe(true);
	});
});
