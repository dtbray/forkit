/**
 * Wake Lock helper — ADR-001 §3g
 *
 * Keeps the screen on during cook view.
 * Feature-detected: no-op on iOS <16.4 or any unsupported browser.
 * Non-fatal: denial or hardware refusal is silently swallowed.
 */

let wakeLock: WakeLockSentinel | null = null;

/**
 * Request a screen wake lock.
 * Safe to call multiple times; subsequent calls are no-ops if a lock is already held.
 */
export async function requestWakeLock(): Promise<void> {
	if (!('wakeLock' in navigator)) return; // iOS <16.4 or unsupported — non-fatal
	if (wakeLock !== null && !wakeLock.released) return; // already active

	try {
		wakeLock = await navigator.wakeLock.request('screen');
	} catch {
		// Device may have denied (low battery, display off, permission denied) — non-fatal.
		// Cook view continues without it; user sees no error.
		wakeLock = null;
	}
}

/**
 * Release the screen wake lock.
 * Safe to call when no lock is held.
 */
export async function releaseWakeLock(): Promise<void> {
	if (wakeLock !== null) {
		await wakeLock.release();
		wakeLock = null;
	}
}

/**
 * Returns true only when the wake lock is currently active and not yet released.
 * Use this to drive the cook-view wake lock indicator (ADR-001 §3g, mock-spec §12).
 */
export function isWakeLockActive(): boolean {
	return wakeLock !== null && !wakeLock.released;
}
