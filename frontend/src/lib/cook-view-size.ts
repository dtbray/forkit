/**
 * Cook view type-size system
 * Source: tokens-2026-05-03.md § Cook View Type-Size Toggle Scale
 *
 * S/M/L/XL controls step body text and ingredient text.
 * Step number is always 48px regardless of toggle.
 *
 * localStorage key: forkit.cook.textSize
 */

export type TextSize = 'S' | 'M' | 'L' | 'XL';

/** Step body size map: toggle value → CSS px value */
const STEP_SIZE_MAP: Record<TextSize, string> = {
	S: '1.75rem', // 28px
	M: '2rem', // 32px
	L: '2.25rem', // 36px
	XL: '2.625rem' // 42px
} as const;

/** Ingredient row size map: toggle value → CSS px value */
const INGREDIENT_SIZE_MAP: Record<TextSize, string> = {
	S: '1.25rem', // 20px
	M: '1.375rem', // 22px
	L: '1.5rem', // 24px
	XL: '1.75rem' // 28px
} as const;

/**
 * Returns the step body CSS size value for a given toggle size.
 * Applied to --cook-step-size custom property.
 */
export function getStepSize(size: TextSize): string {
	return STEP_SIZE_MAP[size];
}

/**
 * Returns the ingredient row CSS size value for a given toggle size.
 * Applied to --cook-ingredient-size custom property.
 */
export function getIngredientSize(size: TextSize): string {
	return INGREDIENT_SIZE_MAP[size];
}

/**
 * Returns the full step size map.
 */
export function getSizeMap(): Record<TextSize, string> {
	return { ...STEP_SIZE_MAP };
}

/**
 * Returns the full ingredient size map.
 */
export function getIngredientSizeMap(): Record<TextSize, string> {
	return { ...INGREDIENT_SIZE_MAP };
}

/**
 * All valid text size values.
 */
export const TEXT_SIZES: TextSize[] = ['S', 'M', 'L', 'XL'];

/**
 * Default text size.
 */
export const DEFAULT_TEXT_SIZE: TextSize = 'M';

/**
 * localStorage key for text size persistence.
 */
export const COOK_TEXT_SIZE_KEY = 'forkit.cook.textSize';

/**
 * Reads the persisted text size from localStorage.
 * Falls back to DEFAULT_TEXT_SIZE if not set or invalid.
 */
export function readPersistedSize(): TextSize {
	try {
		const saved = localStorage.getItem(COOK_TEXT_SIZE_KEY);
		if (saved && (TEXT_SIZES as string[]).includes(saved)) {
			return saved as TextSize;
		}
	} catch {
		// localStorage unavailable (private browsing, etc.) — non-fatal
	}
	return DEFAULT_TEXT_SIZE;
}

/**
 * Persists the text size to localStorage.
 */
export function persistSize(size: TextSize): void {
	try {
		localStorage.setItem(COOK_TEXT_SIZE_KEY, size);
	} catch {
		// localStorage unavailable — non-fatal
	}
}
