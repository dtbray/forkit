import type { PageLoad } from './$types';
import type { DiscoverySite } from '$lib/discovery/types.js';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const res = await fetch('/api/discovery/sites');
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		const sites: DiscoverySite[] = await res.json();
		return { sites, error: null };
	} catch (err) {
		return {
			sites: [] as DiscoverySite[],
			error: err instanceof Error ? err.message : 'Failed to load sites'
		};
	}
};
