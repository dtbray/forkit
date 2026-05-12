<script lang="ts">
	// /discover/inbox — feed inbox, lists FeedItems from subscribed sites.
	// No {@html} anywhere; all user-supplied text is plain text.

	import { FeedItemCard } from '$lib/discovery/index.js';
	import type { FeedItem, FeedInboxResponse } from '$lib/discovery/types.js';

	// ── State ────────────────────────────────────────────────────────────────────

	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let items = $state<FeedItem[]>([]);
	let currentPage = $state(1);
	let totalPages = $state(1);
	let total = $state(0);

	const PAGE_SIZE = 50;

	// ── Fetch ────────────────────────────────────────────────────────────────────

	async function loadPage(p: number) {
		loading = true;
		loadError = null;

		try {
			const res = await fetch(`/api/feed/inbox?page=${p}&limit=${PAGE_SIZE}`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data: FeedInboxResponse = await res.json();
			items = data.items;
			currentPage = data.page;
			totalPages = data.pages;
			total = data.total;
		} catch (err) {
			loadError = err instanceof Error ? err.message : 'Failed to load feed inbox.';
		} finally {
			loading = false;
		}
	}

	// Load on mount
	$effect(() => {
		loadPage(1);
	});

	// ── Dismiss handler ──────────────────────────────────────────────────────────

	function handleDismiss(id: string) {
		items = items.filter((item) => item.id !== id);
	}

	// ── Pagination ───────────────────────────────────────────────────────────────

	function goToPrev() {
		if (currentPage > 1) loadPage(currentPage - 1);
	}

	function goToNext() {
		if (currentPage < totalPages) loadPage(currentPage + 1);
	}
</script>

<svelte:head>
	<title>Feed Inbox — forkit</title>
	<meta name="description" content="New recipes from your subscribed feeds" />
</svelte:head>

<main class="inbox-page">
	<!-- ── Page header ── -->
	<header class="page-header">
		<h1 class="page-title">Feed Inbox</h1>
		<p class="page-subtitle">New recipes from your subscribed feeds.</p>
	</header>

	<!-- ── Content area ── -->
	<section aria-label="Feed inbox items" aria-live="polite">

		{#if loading}
			<!-- Loading skeletons -->
			<div class="items-list" aria-busy="true" aria-label="Loading feed items">
				{#each [1, 2, 3] as i (i)}
					<div class="card-skeleton" aria-hidden="true">
						<div class="skeleton-badge"></div>
						<div class="skeleton-content">
							<div class="skeleton-line skeleton-line--title"></div>
							<div class="skeleton-line skeleton-line--meta"></div>
							<div class="skeleton-line skeleton-line--desc"></div>
						</div>
					</div>
				{/each}
			</div>

		{:else if loadError}
			<!-- Error state -->
			<div class="empty-state" role="alert">
				<div class="empty-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
						<circle cx="12" cy="12" r="10.5" stroke="var(--color-error)" stroke-width="1.5" />
						<path d="M12 7v6M12 15.5v.5" stroke="var(--color-error)" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</div>
				<h2 class="empty-heading">Failed to load inbox</h2>
				<p class="empty-body">{loadError}</p>
				<button type="button" class="btn-retry" onclick={() => loadPage(currentPage)}>
					Try again
				</button>
			</div>

		{:else if items.length === 0}
			<!-- Empty state -->
			<div class="empty-state" role="status">
				<div class="empty-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
						<rect x="3" y="3" width="18" height="18" rx="2" stroke="var(--color-ink-tertiary)" stroke-width="1.5" />
						<path d="M3 9h18" stroke="var(--color-ink-tertiary)" stroke-width="1.5" />
						<path d="M9 15h6" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</div>
				<h2 class="empty-heading">No new items</h2>
				<p class="empty-body">
					Enable feeds in <a href="/settings/discovery" class="inline-link">Settings &rarr; Discovery</a> to subscribe to sites.
				</p>
			</div>

		{:else}
			<!-- Result count -->
			<div class="inbox-header">
				<span class="inbox-count" aria-live="polite">
					{total} item{total !== 1 ? 's' : ''}
					{#if totalPages > 1}
						&nbsp;&mdash;&nbsp;page {currentPage} of {totalPages}
					{/if}
				</span>
			</div>

			<!-- Cards -->
			<ol class="items-list" aria-label="Feed inbox items">
				{#each items as item (item.id)}
					<li>
						<FeedItemCard {item} onDismiss={handleDismiss} />
					</li>
				{/each}
			</ol>

			<!-- Pagination -->
			{#if totalPages > 1}
				<nav class="pagination" aria-label="Inbox pagination">
					<button
						type="button"
						class="page-btn"
						disabled={currentPage <= 1}
						onclick={goToPrev}
						aria-label="Previous page"
					>
						&larr; Prev
					</button>
					<span class="page-indicator" aria-current="page">
						{currentPage} / {totalPages}
					</span>
					<button
						type="button"
						class="page-btn"
						disabled={currentPage >= totalPages}
						onclick={goToNext}
						aria-label="Next page"
					>
						Next &rarr;
					</button>
				</nav>
			{/if}
		{/if}

	</section>
</main>

<style>
	.inbox-page {
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

	/* ── Page header ── */
	.page-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
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

	.page-subtitle {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
		margin: 0;
	}

	/* ── Inbox header ── */
	.inbox-header {
		display: flex;
		align-items: center;
	}

	.inbox-count {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		color: var(--color-ink-secondary);
	}

	/* ── Items list ── */
	.items-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* ── Empty / error states ── */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: var(--space-12) var(--space-6);
		gap: var(--space-4);
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

	.inline-link {
		color: var(--color-clay);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.inline-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: 2px;
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

	/* ── Skeleton cards ── */
	.card-skeleton {
		display: flex;
		align-items: flex-start;
		gap: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		padding: var(--space-4);
	}

	.skeleton-badge {
		flex-shrink: 0;
		width: 40px;
		height: 40px;
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
		.skeleton-badge {
			animation: none;
		}
	}

	/* ── Pagination ── */
	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-4);
		padding-top: var(--space-2);
	}

	.page-btn {
		height: var(--touch-min);
		padding: 0 var(--space-4);
		background: var(--color-surface);
		color: var(--color-clay);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		border: 1.5px solid var(--color-clay);
		border-radius: var(--radius-md);
		cursor: pointer;
		transition:
			background-color var(--transition-fast),
			color var(--transition-fast);
	}

	.page-btn:hover:not(:disabled) {
		background: var(--color-clay-dim);
	}

	.page-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.page-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	.page-indicator {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		color: var(--color-ink-secondary);
		font-variant-numeric: tabular-nums;
	}
</style>
