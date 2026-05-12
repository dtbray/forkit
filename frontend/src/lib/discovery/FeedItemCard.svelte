<script lang="ts">
	// FeedItemCard — horizontal card for feed inbox items.
	// CRITICAL: summary is always rendered as plain text — never {@html}.

	import type { FeedItem } from './types.js';

	interface Props {
		item: FeedItem;
		onDismiss?: ((id: string) => void) | null;
	}

	let { item, onDismiss = null }: Props = $props();

	type PromoteState = 'idle' | 'loading' | 'success' | 'error';
	type DismissState = 'idle' | 'loading' | 'dismissed';

	// Use $derived.by to initialize from props without capturing warnings
	let promoteState = $state<PromoteState>('idle');
	let dismissState = $state<DismissState>('idle');
	let recipeId = $state<string | null>(null);

	// Seed mutable state from props on first render
	$effect.pre(() => {
		if (item.ingested && promoteState === 'idle') {
			promoteState = 'success';
		}
		if (recipeId === null && item.recipe_id !== null) {
			recipeId = item.recipe_id;
		}
	});
	let promoteError = $state('');
	let visible = $state(true);

	// Relative time formatting — no external deps
	function relativeTime(iso: string | null): string {
		if (!iso) return '';
		const diff = Date.now() - new Date(iso).getTime();
		const minutes = Math.floor(diff / 60_000);
		if (minutes < 2) return 'just now';
		if (minutes < 60) return `${minutes} minutes ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
		const days = Math.floor(hours / 24);
		if (days < 30) return `${days} day${days !== 1 ? 's' : ''} ago`;
		const months = Math.floor(days / 30);
		return `${months} month${months !== 1 ? 's' : ''} ago`;
	}

	let timeLabel = $derived(relativeTime(item.published_at));

	// Site initial for the left badge
	let siteInitial = $derived(item.site_name.charAt(0).toUpperCase());

	async function handlePromote() {
		if (promoteState !== 'idle') return;
		promoteState = 'loading';
		promoteError = '';

		try {
			const res = await fetch('/api/feed/promote', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ feed_item_id: item.id })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			recipeId = data?.recipe_id ?? null;
			promoteState = 'success';
		} catch (err) {
			promoteError = err instanceof Error ? err.message : 'Failed to add';
			promoteState = 'error';
		}
	}

	function retryPromote() {
		promoteState = 'idle';
		promoteError = '';
	}

	async function handleDismiss() {
		if (dismissState !== 'idle') return;
		dismissState = 'loading';

		try {
			const res = await fetch('/api/feed/dismiss', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ feed_item_id: item.id })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			dismissState = 'dismissed';
			// Give the fade animation time to complete before notifying parent
			setTimeout(() => {
				visible = false;
				onDismiss?.(item.id);
			}, 250);
		} catch {
			// Non-fatal — reset silently
			dismissState = 'idle';
		}
	}
</script>

{#if visible}
	<article
		class="feed-card"
		class:feed-card--dismissing={dismissState === 'dismissed'}
		aria-label={item.title}
	>
		<!-- Left: site initial badge -->
		<div class="feed-site-badge" aria-hidden="true">
			<span class="feed-site-initial">{siteInitial}</span>
		</div>

		<!-- Content -->
		<div class="feed-content">
			<div class="feed-header">
				<!-- Title — external link -->
				<a
					href={item.url}
					class="feed-title"
					target="_blank"
					rel="noopener noreferrer"
					aria-label="{item.title} — opens in new tab"
				>
					{item.title}
				</a>

				<!-- Meta row: site name + time -->
				<div class="feed-meta">
					<span class="feed-site-name">{item.site_name}</span>
					{#if timeLabel}
						<span class="feed-time" aria-label="Published {timeLabel}">{timeLabel}</span>
					{/if}
				</div>
			</div>

			<!-- Summary — plain text only, never @html -->
			{#if item.summary}
				<p class="feed-summary">{item.summary}</p>
			{/if}
		</div>

		<!-- Actions -->
		<div class="feed-actions">
			<!-- Promote / saved state -->
			{#if promoteState === 'success'}
				<div class="saved-badge" role="status" aria-live="polite">
					<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
						<circle cx="7" cy="7" r="6.5" stroke="var(--color-success)" stroke-width="1.2" />
						<path
							d="M4.5 7l2 2 3-3"
							stroke="var(--color-success)"
							stroke-width="1.4"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
					</svg>
					<span>{item.ingested && promoteState === 'success' && recipeId === item.recipe_id ? 'Already saved' : 'Saved'}</span>
					{#if recipeId}
						<a href="/recipes/{recipeId}" class="view-link">View</a>
					{/if}
				</div>
			{:else if promoteState === 'error'}
				<div class="promote-error" role="alert">
					<span class="promote-error-text">Failed to add</span>
					<button
						type="button"
						class="retry-btn"
						onclick={retryPromote}
						aria-label="Retry adding {item.title}"
					>
						Retry
					</button>
				</div>
			{:else}
				<button
					type="button"
					class="add-btn"
					class:add-btn--loading={promoteState === 'loading'}
					disabled={promoteState === 'loading'}
					onclick={handlePromote}
					aria-label="Add {item.title} to Forkit"
					aria-busy={promoteState === 'loading'}
				>
					{#if promoteState === 'loading'}
						<span class="btn-spinner" aria-hidden="true"></span>
						<span>Adding…</span>
					{:else}
						Add to Forkit
					{/if}
				</button>
			{/if}

			<!-- Dismiss button — hidden once promoted -->
			{#if promoteState !== 'success'}
				<button
					type="button"
					class="dismiss-btn"
					class:dismiss-btn--loading={dismissState === 'loading'}
					disabled={dismissState !== 'idle'}
					onclick={handleDismiss}
					aria-label="Dismiss {item.title}"
				>
					{dismissState === 'loading' ? 'Dismissing…' : 'Dismiss'}
				</button>
			{/if}
		</div>
	</article>
{/if}

<style>
	.feed-card {
		display: flex;
		align-items: flex-start;
		gap: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		padding: var(--space-4);
		transition:
			box-shadow var(--transition-base),
			opacity 0.25s ease,
			transform 0.25s ease;
	}

	.feed-card:hover {
		box-shadow: var(--shadow-md);
	}

	.feed-card--dismissing {
		opacity: 0;
		transform: translateX(8px);
	}

	@media (prefers-reduced-motion: reduce) {
		.feed-card {
			transition: box-shadow var(--transition-base);
		}
		.feed-card--dismissing {
			opacity: 0;
			transform: none;
		}
	}

	/* ── Site badge ── */
	.feed-site-badge {
		flex-shrink: 0;
		width: 40px;
		height: 40px;
		border-radius: var(--radius-md);
		background: var(--color-bone-dim);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.feed-site-initial {
		font-family: var(--font-display);
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--color-ink-tertiary);
		user-select: none;
	}

	/* ── Content ── */
	.feed-content {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.feed-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.feed-title {
		font-family: var(--font-display);
		font-size: var(--text-heading-sm-size);
		font-weight: var(--text-heading-sm-weight);
		line-height: var(--text-heading-sm-lh);
		color: var(--color-ink);
		text-decoration: none;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.feed-title:hover {
		text-decoration: underline;
		text-underline-offset: 2px;
		color: var(--color-clay);
	}

	.feed-title:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: 2px;
	}

	.feed-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}

	.feed-site-name {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-secondary);
	}

	.feed-time {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: 400;
		color: var(--color-ink-tertiary);
		background: var(--color-bone-dim);
		padding: 1px 6px;
		border-radius: var(--radius-sm);
	}

	.feed-summary {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: var(--text-body-sm-weight);
		line-height: var(--text-body-sm-lh);
		color: var(--color-ink-secondary);
		margin: 0;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	/* ── Actions column ── */
	.feed-actions {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--space-2);
	}

	/* Saved badge */
	.saved-badge {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		color: var(--color-success);
		white-space: nowrap;
	}

	.view-link {
		color: var(--color-clay);
		text-decoration: underline;
		text-underline-offset: 2px;
		font-size: var(--text-label-sm-size);
	}

	.view-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: 2px;
	}

	/* Error */
	.promote-error {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--space-1);
	}

	.promote-error-text {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-error);
		white-space: nowrap;
	}

	.retry-btn {
		background: none;
		border: none;
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: 500;
		color: var(--color-clay);
		cursor: pointer;
		padding: 0;
		min-height: 32px;
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	/* Add button */
	.add-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: var(--touch-min);
		padding: 0 var(--space-4);
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		white-space: nowrap;
		transition: background-color var(--transition-fast);
	}

	.add-btn:hover:not(:disabled) {
		background: var(--color-clay-dark);
	}

	.add-btn:disabled {
		background: var(--color-clay-dim);
		cursor: not-allowed;
	}

	.add-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	/* Dismiss button */
	.dismiss-btn {
		display: inline-flex;
		align-items: center;
		height: 32px;
		padding: 0 var(--space-3);
		background: none;
		color: var(--color-ink-tertiary);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		border: 1.5px solid var(--color-divider);
		border-radius: var(--radius-md);
		cursor: pointer;
		white-space: nowrap;
		transition:
			border-color var(--transition-fast),
			color var(--transition-fast),
			background-color var(--transition-fast);
	}

	.dismiss-btn:hover:not(:disabled) {
		border-color: var(--color-ink-tertiary);
		color: var(--color-ink-secondary);
		background: var(--color-bone);
	}

	.dismiss-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.dismiss-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		box-shadow: var(--shadow-focus);
	}

	/* Spinner */
	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid rgba(255, 255, 255, 0.4);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
		flex-shrink: 0;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@media (prefers-reduced-motion: reduce) {
		.btn-spinner {
			animation: none;
		}
	}

	/* ── Mobile ── */
	@media (max-width: 479px) {
		.feed-card {
			flex-wrap: wrap;
		}

		.feed-actions {
			width: 100%;
			flex-direction: row;
			flex-wrap: wrap;
			padding-left: calc(40px + var(--space-4));
		}

		.add-btn {
			flex: 1;
			justify-content: center;
		}
	}
</style>
