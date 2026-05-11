/**
 * Discovery feature — shared types
 * Matches the API contract defined in the Phase 1 ADR.
 */

export interface RecipeStub {
	id: string;
	title: string;
	url: string;
	source_site: { slug: string; name: string };
	thumbnail_url: string | null;
	description: string | null;
	published_at: string | null;
	already_in_collection: boolean;
	origin: 'search' | 'feed';
	feed_item_id: string | null;
}

export interface SiteSearchResult {
	slug: string;
	count: number;
	status: 'ok' | 'error' | 'timeout';
	ms: number;
	error: string | null;
}

export interface SearchResponse {
	query: string;
	results: RecipeStub[];
	site_results: SiteSearchResult[];
	cached: boolean;
}

export interface DiscoverySite {
	id: string;
	slug: string;
	name: string;
	home_url: string;
	adapter_kind: string;
	search_enabled: boolean;
	feed_enabled: boolean;
	is_builtin: boolean;
	paywall_note: string | null;
	last_search_ok_at: string | null;
	last_search_error: string | null;
}
