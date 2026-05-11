<script lang="ts">
	// /discover — client-side recipe discovery search.
	// No +page.ts load function — all fetches are interactive.

	import { SearchBar, RecipeStubCard } from '$lib/discovery/index.js';
	import type { RecipeStub, SiteSearchResult, SearchResponse, DiscoverySite } from '$lib/discovery/types.js';

	// ── State ─────────────────────────────────────────────────────────────────────

	let searchLoading = $state(false);
	let sitesLoading = $state(true);
	let results = $state<RecipeStub[]>([]);
	let siteResults = $state<SiteSearchResult[]>([]);
	let sites = $state<DiscoverySite[]>([]);
	let sitesError = $state(false);
	let searchError = $state<string | null>(null);
	let lastQuery = $state('');
	let hasSearched = $state(false);
	let cached = $state(false);

	// Selected site slugs for filtering (empty = all enabled)
	let selectedSites = $state<Set<string>>(new Set());

	// ── Load sites on mount ────────────────────────────────────────────────────────

	async function loadSites() {
		sitesLoading = true;
		sitesError = false;
		try {
			const res = await fetch('/api/discovery/sites');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data: DiscoverySite[] = await res.json();
			sites = data.filter((s) => s.search_enabled);
		} catch {
			sitesError = true;
			// Non-fatal — search works without site chips
		} finally {
			sitesLoading = false;
		}
	}

	// Fire on component mount using Svelte 5 $effect
	$effect(() => {
		loadSites();
	});

	// ── Search ─────────────────────────────────────────────────────────────────────

	async function handleSearch(q: string) {
		if (!q.trim()) {
			results = [];
			siteResults = [];
			searchError = null;
			hasSearched = false;
			lastQuery = '';
			return;
		}

		searchLoading = true;
		searchError = null;
		lastQuery = q;
		hasSearched = true;

		try {
			const body: Record<string, unknown> = { q, limit_per_site: 10 };
			if (selectedSites.size > 0) {
				body.site_slugs = [...selectedSites];
			}

			const res = await fetch('/api/discovery/search', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) throw new Error(`Search failed (HTTP ${res.status})`);

			const data: SearchResponse = await res.json();
			results = data.results;
			siteResults = data.site_results;
			cached = data.cached;
		} catch (err) {
			searchError = err instanceof Error ? err.message : 'Search failed. Please try again.';
			results = [];
			siteResults = [];
		} finally {
			searchLoading = false;
		}
	}

	// ── Site chip toggle ───────────────────────────────────────────────────────────

	function toggleSite(slug: string) {
		const next = new Set(selectedSites);
		if (next.has(slug)) {
			next.delete(slug);
		} else {
			next.add(slug);
		}
		selectedSites = next;
		// Re-fire search with updated filter if there's an active query
		if (lastQuery) {
			handleSearch(lastQuery);
		}
	}

	// ── Derived ────────────────────────────────────────────────────────────────────

	let hasResults = $derived(results.length > 0);
	let showSiteStatus = $derived(hasSearched && siteResults.length > 0);
	let errorSites = $derived(siteResults.filter((s) => s.status !== 'ok'));
</script>

<svelte:head>
	<title>Discover — forkit</title>
	<meta name="description" content="Search recipe sites and add them to your collection" />
</svelte:head>

<main class="discover-page">
	<!-- ── Page header ──────────────────────────────────────────────────────────── -->
	<header class="page-header">
		<h1 class="page-title">
			<svg class="compass-icon" width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true" focusable="false">
				<circle cx="14" cy="14" r="12.5" stroke="var(--color-clay)" stroke-width="1.5" />
				<path
					d="M14 6v2M14 20v2M6 14h2M20 14h2"
					stroke="var(--color-clay)"
					stroke-width="1.5"
					stroke-linecap="round"
				/>
				<path
					d="M17 11l-4.5 3-1.5 4 4.5-3 1.5-4z"
					fill="var(--color-clay)"
				/>
			</svg>
			Discover
		</h1>
		<p class="page-subtitle">Search recipe sites and add anything you find.</p>
	</header>

	<!-- ── Search bar ───────────────────────────────────────────────────────────── -->
	<div class="search-section">
		<SearchBar onSearch={handleSearch} loading={searchLoading} />

		<!-- Site filter chips -->
		{#if !sitesLoading && !sitesError && sites.length > 0}
			<div class="site-chips" role="group" aria-label="Filter by site">
				{#each sites as site (site.slug)}
					<button
						type="button"
						class="site-chip"
						class:site-chip--active={selectedSites.has(site.slug)}
						onclick={() => toggleSite(site.slug)}
						aria-pressed={selectedSites.has(site.slug)}
						aria-label="{site.name} — {selectedSites.has(site.slug) ? 'included' : 'excluded'}"
					>
						{site.name}
					</button>
				{/each}
			</div>
		{:else if sitesLoading}
			<!-- Skeleton chips while loading -->
			<div class="site-chips" aria-hidden="true">
				{#each [1, 2, 3, 4] as i (i)}
					<span class="site-chip-skeleton"></span>
				{/each}
			</div>
		{/if}
	</div>

	<!-- ── Results area ─────────────────────────────────────────────────────────── -->
	<section aria-label="Search results" aria-live="polite">

		{#if searchLoading && !hasResults}
			<!-- Loading skeleton rows -->
			<div class="results-list" aria-busy="true">
				{#each [1, 2, 3] as i (i)}
					<div class="card-skeleton" aria-hidden="true">
						<div class="skeleton-thumb"></div>
						<div class="skeleton-content">
							<div class="skeleton-line skeleton-line--title"></div>
							<div class="skeleton-line skeleton-line--meta"></div>
							<div class="skeleton-line skeleton-line--desc"></div>
						</div>
					</div>
				{/each}
			</div>

		{:else if searchError}
			<!-- Error state -->
			<div class="empty-state" role="alert">
				<div class="empty-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
						<circle cx="12" cy="12" r="10.5" stroke="var(--color-error)" stroke-width="1.5" />
						<path d="M12 7v6M12 15.5v.5" stroke="var(--color-error)" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</div>
				<h2 class="empty-heading">Search failed</h2>
				<p class="empty-body">{searchError}</p>
				<button
					type="button"
					class="btn-retry"
					onclick={() => handleSearch(lastQuery)}
				>
					Try again
				</button>
			</div>

		{:else if hasSearched && !hasResults && !searchLoading}
			<!-- No results -->
			<div class="empty-state" role="status">
				<div class="empty-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
						<circle cx="10" cy="10" r="7" stroke="var(--color-ink-tertiary)" stroke-width="1.5" />
						<path d="M15.5 15.5l5 5" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" />
						<path d="M7.5 10h5M10 7.5v5" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</div>
				<h2 class="empty-heading">No recipes found</h2>
				<p class="empty-body">Try different keywords or remove site filters.</p>
			</div>

		{:else if !hasSearched}
			<!-- Pre-search idle state -->
			<div class="empty-state empty-state--idle" role="status">
				<div class="empty-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
						<circle cx="10.5" cy="10.5" r="7" stroke="var(--color-ink-tertiary)" stroke-width="1.4" />
						<path d="M16 16l5 5" stroke="var(--color-ink-tertiary)" stroke-width="1.4" stroke-linecap="round" />
					</svg>
				</div>
				<p class="empty-body">Search across multiple recipe sites at once.<br />Results show here.</p>
			</div>

		{:else if hasResults}
			<!-- Result count + cache note -->
			<div class="results-header">
				<span class="results-count" aria-live="polite">
					{results.length} result{results.length !== 1 ? 's' : ''} for &ldquo;{lastQuery}&rdquo;
					{#if cached}<span class="cached-badge">cached</span>{/if}
				</span>
			</div>

			<!-- Cards -->
			<ol class="results-list" aria-label="Recipe results">
				{#each results as stub (stub.id)}
					<li>
						<RecipeStubCard {stub} />
					</li>
				{/each}
			</ol>
		{/if}
	</section>

	<!-- ── Per-site status row ──────────────────────────────────────────────────── -->
	{#if showSiteStatus}
		<div class="site-status-row" aria-label="Site search status" role="region">
			<h3 class="site-status-label">Site results</h3>
			<ul class="site-status-list" role="list">
				{#each siteResults as sr (sr.slug)}
					<li class="site-status-item" class:site-status-item--error={sr.status !== 'ok'}>
						<span class="site-status-dot" class:dot--ok={sr.status === 'ok'} class:dot--error={sr.status === 'error'} class:dot--timeout={sr.status === 'timeout'} aria-hidden="true"></span>
						<span class="site-status-name">{sr.slug}</span>
						{#if sr.status === 'ok'}
							<span class="site-status-count">{sr.count} result{sr.count !== 1 ? 's' : ''}</span>
							<span class="site-status-ms" aria-label="{sr.ms}ms">{sr.ms}ms</span>
						{:else}
							<span class="site-status-error-label">
								{sr.status === 'timeout' ? 'timed out' : 'error'}
							</span>
						{/if}
					</li>
				{/each}
			</ul>
			{#if errorSites.length > 0}
				<p class="site-status-note">
					{errorSites.length} site{errorSites.length !== 1 ? 's' : ''} didn't respond. Results from other sites are shown.
				</p>
			{/if}
		</div>
	{/if}
</main>

<style>
	.discover-page {
		flex: 1;
		padding: var(--space-6);
		background: var(--color-bone);
		max-width: 800px;
		margin-inline: auto;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	/* ── Page header ─────────────────────────────────────────────────────────── */
	.page-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.page-title {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-ink);
		margin: 0;
	}

	.compass-icon {
		flex-shrink: 0;
	}

	.page-subtitle {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
		margin: 0;
	}

	/* ── Search section ─────────────────────────────────────────────────────── */
	.search-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* ── Site chips ──────────────────────────────────────────────────────────── */
	.site-chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.site-chip {
		display: inline-flex;
		align-items: center;
		height: 32px;
		padding: 0 var(--space-3);
		border-radius: var(--radius-full);
		border: 1.5px solid var(--color-divider);
		background: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		color: var(--color-ink-secondary);
		cursor: pointer;
		transition: border-color var(--transition-fast), background-color var(--transition-fast), color var(--transition-fast);
		white-space: nowrap;
	}

	.site-chip:hover {
		border-color: var(--color-clay-dim);
		background: var(--color-clay-dim);
		color: var(--color-clay-dark);
	}

	.site-chip--active {
		border-color: var(--color-clay);
		background: var(--color-clay-dim);
		color: var(--color-clay-dark);
	}

	.site-chip:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		box-shadow: var(--shadow-focus);
	}

	.site-chip-skeleton {
		display: inline-block;
		height: 32px;
		width: 80px;
		border-radius: var(--radius-full);
		background: var(--color-bone-dim);
		animation: shimmer 1.4s infinite ease-in-out;
	}

	.site-chip-skeleton:nth-child(2) { width: 96px; }
	.site-chip-skeleton:nth-child(3) { width: 72px; }
	.site-chip-skeleton:nth-child(4) { width: 104px; }

	/* ── Results ──────────────────────────────────────────────────────────────── */
	.results-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
	}

	.results-count {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		color: var(--color-ink-secondary);
	}

	.cached-badge {
		display: inline-block;
		margin-left: var(--space-2);
		padding: 1px 6px;
		border-radius: var(--radius-sm);
		background: var(--color-bone-dim);
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-tertiary);
	}

	.results-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* ── Empty states ────────────────────────────────────────────────────────── */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: var(--space-12) var(--space-6);
		gap: var(--space-4);
	}

	.empty-state--idle {
		padding-top: var(--space-8);
		opacity: 0.7;
	}

	.empty-icon {
		width: 48px;
		height: 48px;
	}

	.empty-icon svg {
		width: 100%;
		height: 100%;
	}

	.empty-heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size);
		font-weight: var(--text-heading-md-weight);
		color: var(--color-ink);
		margin: 0;
	}

	.empty-body {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
		margin: 0;
		max-width: 36ch;
		line-height: var(--text-body-sm-lh);
	}

	.btn-retry {
		height: var(--touch-min);
		padding: 0 var(--space-6);
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: background-color var(--transition-fast);
	}

	.btn-retry:hover {
		background: var(--color-clay-dark);
	}

	.btn-retry:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	/* ── Skeleton cards ──────────────────────────────────────────────────────── */
	.card-skeleton {
		display: flex;
		align-items: flex-start;
		gap: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		padding: var(--space-4);
	}

	.skeleton-thumb {
		flex-shrink: 0;
		width: 60px;
		height: 60px;
		border-radius: var(--radius-md);
		background: var(--color-bone-dim);
		animation: shimmer 1.4s infinite ease-in-out;
	}

	.skeleton-content {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.skeleton-line {
		border-radius: var(--radius-sm);
		background: var(--color-bone-dim);
		animation: shimmer 1.4s infinite ease-in-out;
	}

	.skeleton-line--title { height: 20px; width: 70%; }
	.skeleton-line--meta  { height: 14px; width: 40%; }
	.skeleton-line--desc  { height: 14px; width: 90%; }

	@keyframes shimmer {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}

	@media (prefers-reduced-motion: reduce) {
		.skeleton-line,
		.skeleton-thumb,
		.site-chip-skeleton {
			animation: none;
		}
	}

	/* ── Per-site status row ──────────────────────────────────────────────────── */
	.site-status-row {
		margin-top: var(--space-4);
		padding: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.site-status-label {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		letter-spacing: var(--text-label-md-tracking);
		color: var(--color-ink-tertiary);
		text-transform: uppercase;
		margin: 0;
	}

	.site-status-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.site-status-item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
	}

	.site-status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.dot--ok      { background: var(--color-success); }
	.dot--error   { background: var(--color-error); }
	.dot--timeout { background: var(--color-warning); }

	.site-status-name {
		font-weight: 500;
		flex: 1;
	}

	.site-status-count {
		color: var(--color-ink-secondary);
	}

	.site-status-ms {
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-tertiary);
		font-variant-numeric: tabular-nums;
	}

	.site-status-error-label {
		color: var(--color-error);
		font-size: var(--text-label-sm-size);
	}

	.site-status-note {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-tertiary);
		margin: 0;
	}
</style>
