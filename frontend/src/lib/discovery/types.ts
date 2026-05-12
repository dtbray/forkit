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

export interface FeedItem {
	id: string;
	site_id: string;
	site_name: string;
	entry_guid: string;
	url: string;
	title: string;
	summary: string | null;
	published_at: string | null;
	ingested: boolean;
	ingested_at: string | null;
	recipe_id: string | null;
	dismissed: boolean;
	seen_at: string | null;
	created_at: string;
}

export interface FeedInboxResponse {
	items: FeedItem[];
	total: number;
	page: number;
	pages: number;
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
