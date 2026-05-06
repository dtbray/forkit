import { describe, it, expect } from 'vitest';
import { isWakeLockActive } from '../wake-lock';

describe('wake-lock', () => {
	it('isWakeLockActive returns false when no lock held', () => {
		expect(isWakeLockActive()).toBe(false);
	});
});
