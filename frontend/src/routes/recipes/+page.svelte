<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { formatDuration } from '$lib/utils/duration';

	interface Recipe {
		id: string;
		title: string;
		hero_image_path: string | null;
		cuisine: string | null;
		total_time: string | null;
		favorite: boolean;
		cook_count: number;
		tags: string[];
		created_at: string;
	}

	interface PageData {
		recipes: Recipe[];
	}

	let { data }: { data: PageData } = $props();

	// ── Filter state ─────────────────────────────────────────────────────────────
	let searchQuery: string = $state($page.url.searchParams.get('q') ?? '');
	let cuisineFilter: string = $state($page.url.searchParams.get('cuisine') ?? '');
	let favoriteFilter: boolean = $state($page.url.searchParams.get('favorite') === 'true');

	// ── Derived: unique cuisines from current recipe list ────────────────────────
	const cuisines = $derived(
		[...new Set(data.recipes.map((r) => r.cuisine).filter(Boolean) as string[])].sort()
	);

	// ── Apply filters via navigation ─────────────────────────────────────────────
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	function applyFilters() {
		const params = new URLSearchParams();
		if (searchQuery.trim()) params.set('q', searchQuery.trim());
		if (cuisineFilter) params.set('cuisine', cuisineFilter);
		if (favoriteFilter) params.set('favorite', 'true');
		goto(`/recipes?${params}`, { keepFocus: true, noScroll: true });
	}

	function handleSearchInput() {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(applyFilters, 300);
	}

	function handleSelectChange() {
		applyFilters();
	}

	function handleFavoriteToggle() {
		favoriteFilter = !favoriteFilter;
		applyFilters();
	}


</script>

<svelte:head>
	<title>Recipes — forkit</title>
	<meta name="description" content="Browse your saved recipes" />
</svelte:head>

<main class="recipes-page">
	<!-- ── Page header ──────────────────────────────────────────────────────────── -->
	<header class="page-header">
		<h1 class="page-title">Recipes</h1>
		<a href="/ingest" class="btn-add" aria-label="Add a new recipe">
			<span aria-hidden="true">+</span> Add recipe
		</a>
	</header>

	<!-- ── Filter bar ───────────────────────────────────────────────────────────── -->
	<div class="filter-bar" role="search" aria-label="Filter recipes">
		<label class="filter-label" for="search-input">
			<span class="sr-only">Search recipes</span>
			<input
				id="search-input"
				type="search"
				class="filter-search"
				placeholder="Search recipes…"
				bind:value={searchQuery}
				oninput={handleSearchInput}
				aria-label="Search recipes by keyword"
			/>
		</label>

		<label class="filter-label" for="cuisine-select">
			<span class="sr-only">Filter by cuisine</span>
			<select
				id="cuisine-select"
				class="filter-select"
				bind:value={cuisineFilter}
				onchange={handleSelectChange}
				aria-label="Filter by cuisine"
			>
				<option value="">All cuisines</option>
				{#each cuisines as cuisine}
					<option value={cuisine}>{cuisine}</option>
				{/each}
			</select>
		</label>

		<button
			class="filter-favorite-btn"
			class:filter-favorite-btn--active={favoriteFilter}
			onclick={handleFavoriteToggle}
			aria-pressed={favoriteFilter}
			aria-label={favoriteFilter ? 'Showing favorites only — click to show all' : 'Show favorites only'}
			title="Favorites only"
		>
			<span aria-hidden="true">{favoriteFilter ? '★' : '☆'}</span>
			<span class="filter-favorite-label">Favorites</span>
		</button>
	</div>

	<!-- ── Recipe grid ──────────────────────────────────────────────────────────── -->
	{#if data.recipes.length > 0}
		<ol class="recipe-grid" aria-label="Recipe list">
			{#each data.recipes as recipe (recipe.id)}
				<li class="recipe-card-item">
					<a href="/recipes/{recipe.id}" class="recipe-card" aria-label="{recipe.title}{recipe.cuisine ? ', ' + recipe.cuisine : ''}">
						<!-- Hero image -->
						<div class="card-hero" aria-hidden="true">
							{#if recipe.hero_image_path}
								<img
									src={recipe.hero_image_path}
									alt=""
									class="card-hero-img"
									loading="lazy"
									decoding="async"
								/>
							{:else}
								<div class="card-hero-placeholder">
									<svg class="placeholder-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
										<path d="M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z" />
									</svg>
								</div>
							{/if}

							<!-- Favorite indicator -->
							{#if recipe.favorite}
								<span class="card-favorite" aria-label="Favorite">★</span>
							{/if}

							<!-- Cook count badge -->
							{#if recipe.cook_count > 0}
								<span class="card-cook-count" aria-label="Cooked {recipe.cook_count} {recipe.cook_count === 1 ? 'time' : 'times'}">
									{recipe.cook_count}×
								</span>
							{/if}
						</div>

						<!-- Card body -->
						<div class="card-body">
							<h2 class="card-title">{recipe.title}</h2>
							<div class="card-meta">
								{#if recipe.cuisine}
									<span class="card-cuisine">{recipe.cuisine}</span>
								{/if}
								{#if formatDuration(recipe.total_time)}
									<span class="card-time" aria-label="{formatDuration(recipe.total_time)} total time">
										{formatDuration(recipe.total_time)}
									</span>
								{/if}
							</div>
						</div>
					</a>
				</li>
			{/each}
		</ol>
	{:else}
		<!-- ── Empty state ──────────────────────────────────────────────────────── -->
		<div class="empty-state" role="status" aria-live="polite">
			<div class="empty-icon" aria-hidden="true">
				<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
					<path d="M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z" />
				</svg>
			</div>
			{#if searchQuery || cuisineFilter || favoriteFilter}
				<h2 class="empty-heading">No recipes match your filters</h2>
				<p class="empty-body">Try clearing your search or removing a filter.</p>
				<a href="/recipes" class="btn-cta">Clear filters</a>
			{:else}
				<h2 class="empty-heading">Your vault is empty</h2>
				<p class="empty-body">Fork a recipe from anywhere on the web — paste a URL and we'll handle the rest.</p>
				<a href="/ingest" class="btn-cta">Add your first recipe</a>
			{/if}
		</div>
	{/if}
</main>

<style>
	/* ── Page root ───────────────────────────────────────────────────────────── */
	.recipes-page {
		flex: 1;
		padding: var(--space-6);
		background-color: var(--color-bone);
		max-width: 1200px;
		margin-inline: auto;
		width: 100%;
	}

	/* ── Screen reader only ─────────────────────────────────────────────────── */
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border-width: 0;
	}

	/* ── Page header ─────────────────────────────────────────────────────────── */
	.page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-4);
		margin-bottom: var(--space-6);
	}

	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-ink);
		margin: 0;
	}

	.btn-add {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		min-height: var(--touch-min);
		padding: 0 var(--space-5);
		background-color: var(--color-clay);
		color: var(--color-surface);
		border-radius: var(--radius-md);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		line-height: var(--text-ui-md-lh);
		transition: background-color var(--transition-fast);
		flex-shrink: 0;
	}

	.btn-add:hover {
		background-color: var(--color-clay-dark);
	}

	.btn-add:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	/* ── Filter bar ──────────────────────────────────────────────────────────── */
	.filter-bar {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		margin-bottom: var(--space-6);
		flex-wrap: wrap;
	}

	.filter-label {
		display: contents;
	}

	.filter-search {
		flex: 1;
		min-width: 180px;
		min-height: var(--touch-min);
		padding: 0 var(--space-4);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-md);
		background-color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: var(--text-body-sm-weight);
		color: var(--color-ink);
		transition: border-color var(--transition-fast);
		appearance: none;
	}

	.filter-search::placeholder {
		color: var(--color-ink-tertiary);
	}

	.filter-search:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 0;
		border-color: var(--color-clay);
		box-shadow: var(--shadow-focus);
	}

	.filter-select {
		min-height: var(--touch-min);
		padding: 0 var(--space-8) 0 var(--space-4);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-md);
		background-color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: var(--text-body-sm-weight);
		color: var(--color-ink);
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%238A837A' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right var(--space-3) center;
		transition: border-color var(--transition-fast);
	}

	.filter-select:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 0;
		border-color: var(--color-clay);
		box-shadow: var(--shadow-focus);
	}

	.filter-favorite-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		min-height: var(--touch-min);
		padding: 0 var(--space-4);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-md);
		background-color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: var(--text-body-sm-weight);
		color: var(--color-ink-secondary);
		cursor: pointer;
		transition: border-color var(--transition-fast), background-color var(--transition-fast), color var(--transition-fast);
		flex-shrink: 0;
	}

	.filter-favorite-btn--active {
		border-color: var(--color-clay);
		background-color: var(--color-clay-dim);
		color: var(--color-clay-dark);
	}

	.filter-favorite-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	.filter-favorite-btn > :first-child {
		font-size: 1.1em;
		color: var(--color-clay);
	}

	.filter-favorite-btn--active > :first-child {
		color: var(--color-clay);
	}

	/* ── Recipe grid ─────────────────────────────────────────────────────────── */
	.recipe-grid {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-5);
	}

	/* 2-col on tablet portrait (768px+) */
	@media (min-width: 768px) {
		.recipe-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	/* 3-col on tablet landscape / desktop (1024px+) */
	@media (min-width: 1024px) {
		.recipe-grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	.recipe-card-item {
		display: contents;
	}

	/* ── Recipe card ─────────────────────────────────────────────────────────── */
	.recipe-card {
		display: flex;
		flex-direction: column;
		background-color: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		overflow: hidden;
		text-decoration: none;
		color: inherit;
		transition: box-shadow var(--transition-base), transform var(--transition-base);
	}

	.recipe-card:hover {
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
	}

	.recipe-card:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	@media (prefers-reduced-motion: reduce) {
		.recipe-card:hover {
			transform: none;
		}
	}

	/* ── Card hero ───────────────────────────────────────────────────────────── */
	.card-hero {
		position: relative;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		background-color: var(--color-bone);
		flex-shrink: 0;
	}

	.card-hero-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
		transition: transform var(--transition-slow);
	}

	.recipe-card:hover .card-hero-img {
		transform: scale(1.03);
	}

	@media (prefers-reduced-motion: reduce) {
		.recipe-card:hover .card-hero-img {
			transform: none;
		}
	}

	.card-hero-placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		background-color: var(--color-bone);
	}

	.placeholder-icon {
		width: 48px;
		height: 48px;
		fill: var(--color-bone-dim);
	}

	/* ── Card badges ─────────────────────────────────────────────────────────── */
	.card-favorite {
		position: absolute;
		top: var(--space-3);
		right: var(--space-3);
		font-size: 1.25rem;
		line-height: 1;
		color: var(--color-clay);
		text-shadow: 0 1px 3px rgba(26, 26, 26, 0.25);
	}

	.card-cook-count {
		position: absolute;
		bottom: var(--space-3);
		right: var(--space-3);
		padding: 2px var(--space-2);
		background-color: rgba(26, 26, 26, 0.65);
		color: #fff;
		border-radius: var(--radius-sm);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: 600;
		line-height: 1.4;
		letter-spacing: 0.02em;
		font-variant-numeric: tabular-nums;
	}

	/* ── Card body ───────────────────────────────────────────────────────────── */
	.card-body {
		padding: var(--space-4) var(--space-5) var(--space-5);
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		flex: 1;
	}

	.card-title {
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size);
		font-weight: var(--text-heading-md-weight);
		line-height: var(--text-heading-md-lh);
		letter-spacing: var(--text-heading-md-tracking);
		color: var(--color-ink);
		margin: 0;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
	}

	.card-cuisine {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-secondary);
		font-variant: small-caps;
	}

	.card-time {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		color: var(--color-ink-tertiary);
	}

	.card-time::before {
		content: '·';
		margin-right: var(--space-3);
		color: var(--color-divider);
	}

	.card-cuisine + .card-time::before {
		display: inline;
	}

	.card-time:first-child::before {
		display: none;
	}

	/* ── Empty state ─────────────────────────────────────────────────────────── */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: var(--space-16) var(--space-6);
		gap: var(--space-4);
	}

	.empty-icon {
		width: 64px;
		height: 64px;
		color: var(--color-bone-dim);
	}

	.empty-icon svg {
		width: 100%;
		height: 100%;
		fill: var(--color-ink-tertiary);
		opacity: 0.4;
	}

	.empty-heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size);
		font-weight: var(--text-heading-md-weight);
		line-height: var(--text-heading-md-lh);
		color: var(--color-ink);
		margin: 0;
	}

	.empty-body {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: var(--text-body-md-weight);
		line-height: var(--text-body-md-lh);
		color: var(--color-ink-secondary);
		margin: 0;
		max-width: 36ch;
	}

	.btn-cta {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: var(--touch-min);
		padding: 0 var(--space-8);
		background-color: var(--color-clay);
		color: var(--color-surface);
		border-radius: var(--radius-md);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		line-height: var(--text-ui-md-lh);
		margin-top: var(--space-2);
		transition: background-color var(--transition-fast);
	}

	.btn-cta:hover {
		background-color: var(--color-clay-dark);
	}

	.btn-cta:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}
</style>
