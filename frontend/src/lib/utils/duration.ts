/**
 * Parses ISO 8601 duration strings (e.g. "PT45M", "PT1H30M") into
 * a human-readable label suitable for display in recipe cards and detail views.
 */
export function formatDuration(iso: string | null | undefined): string {
	if (!iso) return '';
	const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
	if (!m) return iso;
	const h = parseInt(m[1] ?? '0');
	const min = parseInt(m[2] ?? '0');
	if (h && min) return `${h}h ${min}m`;
	if (h) return `${h}h`;
	if (min) return `${min} min`;
	return '';
}
