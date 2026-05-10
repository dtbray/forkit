import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const res = await fetch(`/api/recipes/${params.uuid}`);
	if (!res.ok) throw error(404, 'Recipe not found');
	return await res.json();
};
