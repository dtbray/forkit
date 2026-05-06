import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
	const params = new URLSearchParams(url.searchParams);
	const res = await fetch(`/api/recipes?${params}`);
	if (!res.ok) return { recipes: [] };
	return await res.json();
};
