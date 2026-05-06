import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const res = await fetch('/api/suggestions/tonight');
		if (!res.ok) return { tonight: null, alternates: [] };
		return await res.json();
	} catch {
		return { tonight: null, alternates: [] };
	}
};
