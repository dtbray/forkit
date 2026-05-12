<script lang="ts">
	// RecipeStubCard — horizontal card for discovery search results.
	// CRITICAL: description is always rendered as plain text — never {@html}.

	import type { RecipeStub } from './types.js';

	interface Props {
		stub: RecipeStub;
		onAdd?: (() => Promise<void>) | null;
	}

	let { stub, onAdd = null }: Props = $props();

	type AddState = 'idle' | 'loading' | 'success' | 'error';

	let addState = $state<AddState>('idle');
	let addedRecipeId = $state<string | null>(null);
	let errorMessage = $state('');

	// Derived site initial for thumbnail fallback
	let siteInitial = $derived(stub.source_site.name.charAt(0).toUpperCase());

	// internal:// URLs must never be rendered as navigable anchors (security condition Q3.3)
	let isInternalUrl = $derived(stub.url.startsWith('internal://'));

	// Derive a clean display domain
	let displayDomain = $derived(() => {
		if (isInternalUrl) return 'Local Collection';
		try {
			return new URL(stub.url).hostname.replace(/^www\./, '');
		} catch {
			return stub.source_site.slug;
		}
	});

	async function handleAdd() {
		if (addState !== 'idle') return;

		addState = 'loading';
		errorMessage = '';

		try {
			// If a custom onAdd was injected, delegate to it
			if (onAdd) {
				await onAdd();
				addState = 'success';
				return;
			}

			// Default: call POST /api/ingest directly
			const response = await fetch('/api/ingest', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: stub.url })
			});

			if (!response.ok) {
				if (response.status === 409) {
					// Already in collection — treat as success
					const body = await response.json().catch(() => ({}));
					addedRecipeId = body?.detail?.recipe_id ?? null;
					addState = 'success';
					return;
				}
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();
			addedRecipeId = data?.recipe_id ?? null;
			addState = 'success';
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'Something went wrong';
			addState = 'error';
		}
	}

	function retryAdd() {
		addState = 'idle';
		errorMessage = '';
	}
</script>

<article class="stub-card" aria-label={stub.title}>
	<!-- Thumbnail -->
	<div class="stub-thumbnail" aria-hidden="true">
		{#if stub.thumbnail_url}
			<img
				src={stub.thumbnail_url}
				alt=""
				class="stub-thumb-img"
				loading="lazy"
				decoding="async"
				onerror={(e) => {
					const img = e.currentTarget as HTMLImageElement;
					img.style.display = 'none';
					const parent = img.parentElement;
					if (parent) parent.classList.add('stub-thumbnail--fallback');
				}}
			/>
		{/if}
		<span class="stub-thumb-initial" aria-hidden="true">{siteInitial}</span>
	</div>

	<!-- Content -->
	<div class="stub-content">
		<div class="stub-header">
			<!-- Title — external link for http(s); plain text for internal:// (Q3.3) -->
			{#if isInternalUrl}
				<span class="stub-title stub-title--local" aria-label="{stub.title} — from Local Collection">
					{stub.title}
				</span>
			{:else}
				<a
					href={stub.url}
					class="stub-title"
					target="_blank"
					rel="noopener noreferrer"
					aria-label="{stub.title} — opens {displayDomain()} in new tab"
				>
					{stub.title}
				</a>
			{/if}

			<!-- Site + domain badge -->
			<div class="stub-meta" aria-label="Source: {stub.source_site.name}">
				<span class="stub-site-name">{stub.source_site.name}</span>
				<span class="stub-domain-badge" aria-hidden="true">{displayDomain()}</span>
			</div>
		</div>

		<!-- Description — plain text only, never @html -->
		{#if stub.description}
			<p class="stub-description">{stub.description}</p>
		{/if}
	</div>

	<!-- Action -->
	<div class="stub-action">
		{#if stub.already_in_collection || addState === 'success'}
			<div class="already-saved-badge" role="status" aria-live="polite">
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
				<span>Already saved</span>
				{#if addedRecipeId}
					<a href="/recipes/{addedRecipeId}" class="view-link">View</a>
				{/if}
			</div>
		{:else if addState === 'error'}
			<div class="add-error" role="alert">
				<span class="add-error-text">Failed to add</span>
				<button type="button" class="retry-btn" onclick={retryAdd} aria-label="Retry adding {stub.title}">
					Retry
				</button>
			</div>
		{:else}
			<button
				type="button"
				class="add-btn"
				class:add-btn--loading={addState === 'loading'}
				disabled={addState === 'loading'}
				onclick={handleAdd}
				aria-label="Add {stub.title} to Forkit"
				aria-busy={addState === 'loading'}
			>
				{#if addState === 'loading'}
					<span class="btn-spinner" aria-hidden="true"></span>
					<span>Adding…</span>
				{:else}
					Add to Forkit
				{/if}
			</button>
		{/if}
	</div>
</article>

<style>
	.stub-card {
		display: flex;
		align-items: flex-start;
		gap: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		padding: var(--space-4);
		transition: box-shadow var(--transition-base);
	}

	.stub-card:hover {
		box-shadow: var(--shadow-md);
	}

	/* ── Thumbnail ── */
	.stub-thumbnail {
		position: relative;
		flex-shrink: 0;
		width: 60px;
		height: 60px;
		border-radius: var(--radius-md);
		background: var(--color-bone-dim);
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.stub-thumb-img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
		/* hide initial once image loads */
	}

	/* When image has loaded, the initial letter is visually obscured by the image */
	.stub-thumbnail:has(.stub-thumb-img) .stub-thumb-initial {
		opacity: 0;
	}

	/* Fallback class applied on img onerror */
	:global(.stub-thumbnail--fallback) .stub-thumb-initial {
		opacity: 1;
	}

	.stub-thumb-initial {
		font-family: var(--font-display);
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--color-ink-tertiary);
		user-select: none;
		position: relative;
		z-index: 0;
	}

	/* ── Content ── */
	.stub-content {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.stub-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.stub-title {
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

	.stub-title:hover {
		text-decoration: underline;
		text-underline-offset: 2px;
		color: var(--color-clay);
	}

	.stub-title--local {
		cursor: default;
		color: var(--color-ink);
	}

	.stub-title--local:hover {
		text-decoration: none;
		color: var(--color-ink);
	}

	.stub-title:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: 2px;
	}

	.stub-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}

	.stub-site-name {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-secondary);
	}

	.stub-domain-badge {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: 400;
		color: var(--color-ink-tertiary);
		background: var(--color-bone-dim);
		padding: 1px 6px;
		border-radius: var(--radius-sm);
	}

	.stub-description {
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

	/* ── Action column ── */
	.stub-action {
		flex-shrink: 0;
		display: flex;
		align-items: center;
	}

	/* Already-saved badge */
	.already-saved-badge {
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

	/* Error row */
	.add-error {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--space-1);
	}

	.add-error-text {
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

	/* ── Mobile: stack content vertically, action below ── */
	@media (max-width: 479px) {
		.stub-card {
			flex-wrap: wrap;
		}

		.stub-action {
			width: 100%;
			padding-left: calc(60px + var(--space-4));
		}

		.add-btn {
			width: 100%;
			justify-content: center;
		}

		.already-saved-badge {
			width: 100%;
		}
	}
</style>
