<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { isValidRecipeUrl, looksLikeUrl, extractDomain } from '$lib/url-validator';

	// ── Types ──────────────────────────────────────────────────────────────────

	type IngestState =
		| 'idle'
		| 'fetching'
		| 'parsing'
		| 'preview'
		| 'error-network'
		| 'error-parse'
		| 'error-parse-llm'
		| 'error-duplicate';

	interface RecipePreview {
		id: string;
		title: string;
		image: string | null;
		ingredientCount: number | null;
		totalTime: string | null;
		serves: number | null;
		sourceUrl: string;
	}

	// ── State ──────────────────────────────────────────────────────────────────

	let inputUrl = $state('');
	let urlError = $state('');
	let ingestState = $state<IngestState>('idle');
	let clipboardUrl = $state('');
	let clipboardDomain = $state('');
	let fromShare = $state(false);
	let preview = $state<RecipePreview | null>(null);
	let duplicateRecipeId = $state<string | null>(null);

	// Preview card editable fields
	let recipeTitle = $state('');
	let tagsInput = $state('');
	let tags = $state<string[]>([]);
	let isFavorite = $state(false);

	// ── Derived ───────────────────────────────────────────────────────────────

	let isValid = $derived(isValidRecipeUrl(inputUrl));
	let hasText = $derived(inputUrl.trim().length > 0);
	let showClipboardStrip = $derived(clipboardUrl !== '' && !fromShare && ingestState === 'idle');
	let isLoading = $derived(ingestState === 'fetching' || ingestState === 'parsing');
	let isReadOnly = $derived(isLoading || ingestState === 'preview');

	// ── URL input element ref ──────────────────────────────────────────────────

	let urlInputEl: HTMLInputElement | null = null;

	// ── Mount ─────────────────────────────────────────────────────────────────

	onMount(() => {
		// Handle ?prefill= from share target
		const prefill = $page.url.searchParams.get('prefill');
		if (prefill && looksLikeUrl(prefill)) {
			inputUrl = prefill;
			fromShare = true;
			// Do NOT auto-focus / open keyboard when URL is pre-filled from share
			return;
		}

		// Passive clipboard detection — no permission prompt on mount.
		// We attempt a read; if denied or unavailable we silently skip.
		if (typeof navigator !== 'undefined' && 'clipboard' in navigator) {
			navigator.clipboard
				.readText()
				.then((text) => {
					if (looksLikeUrl(text)) {
						clipboardUrl = text.trim();
						clipboardDomain = extractDomain(clipboardUrl);
						// Field stays empty — user must explicitly tap "Use this"
					} else {
						focusInput();
					}
				})
				.catch(() => {
					// Permission denied or API unavailable — silent fallback
					focusInput();
				});
		} else {
			focusInput();
		}
	});

	function focusInput() {
		// Defer 150ms for PWA shell animation (spec §13)
		setTimeout(() => {
			urlInputEl?.focus();
		}, 150);
	}

	// ── Input handlers ────────────────────────────────────────────────────────

	function handleUrlInput() {
		urlError = '';
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			handleSubmit();
		}
	}

	function clearInput() {
		inputUrl = '';
		urlError = '';
		clipboardUrl = '';
		clipboardDomain = '';
		fromShare = false;
		focusInput();
	}

	function useClipboardUrl() {
		inputUrl = clipboardUrl;
		clipboardUrl = '';
		clipboardDomain = '';
		handleSubmit();
	}

	function pasteDifferentLink() {
		inputUrl = '';
		clipboardUrl = '';
		clipboardDomain = '';
		fromShare = false;
		focusInput();
	}

	// ── Submit ────────────────────────────────────────────────────────────────

	async function handleSubmit() {
		urlError = '';

		if (!hasText) return;

		if (!isValid) {
			urlError = 'Please enter a valid URL starting with http:// or https://';
			return;
		}

		ingestState = 'fetching';

		// Dismiss keyboard — input becomes read-only during fetch
		urlInputEl?.blur();

		try {
			let data: { recipe_id?: string; status?: string };

			// ── DEV MOCK ───────────────────────────────────────────────────────
			// Toggle: set MOCK_INGEST = false to call the real /api/ingest endpoint.
			// In production (import.meta.env.DEV === false) this block is never entered.
			const MOCK_INGEST = false;

			if (MOCK_INGEST) {
				await new Promise((r) => setTimeout(r, 500));
				ingestState = 'parsing';
				await new Promise((r) => setTimeout(r, 400));

				data = { recipe_id: 'mock-uuid' };

				preview = {
					id: 'mock-uuid',
					title: 'Sheet-Pan Chicken Thighs with Roasted Vegetables',
					image: null,
					ingredientCount: 12,
					totalTime: '45 min',
					serves: 4,
					sourceUrl: inputUrl
				};
				recipeTitle = preview.title;
				ingestState = 'preview';
				return;
			}
			// ── END DEV MOCK ──────────────────────────────────────────────────

			ingestState = 'parsing';

			const response = await fetch('/api/ingest', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl })
			});

			if (!response.ok) {
				if (response.status === 409) {
					const body = await response.json().catch(() => ({}));
					duplicateRecipeId = body?.detail?.recipe_id ?? null;
					ingestState = 'error-duplicate';
					return;
				}
				if (response.status === 422) {
					ingestState = 'error-parse';
					return;
				}
				ingestState = 'error-network';
				return;
			}

			data = await response.json();

			if (data.recipe_id) {
				await goto(`/recipes/${data.recipe_id}`);
			}
		} catch {
			ingestState = 'error-network';
		}
	}

	async function retryWithLlm() {
		ingestState = 'fetching';
		urlInputEl?.blur();

		try {
			if (import.meta.env.DEV) {
				await new Promise((r) => setTimeout(r, 800));
				ingestState = 'error-parse-llm';
				return;
			}

			const response = await fetch('/api/ingest', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl, llm_fallback: true })
			});

			if (!response.ok) {
				ingestState = 'error-parse-llm';
				return;
			}

			const data = await response.json();
			if (data.recipe_id) {
				await goto(`/recipes/${data.recipe_id}`);
			}
		} catch {
			ingestState = 'error-parse-llm';
		}
	}

	function resetToIdle() {
		ingestState = 'idle';
		preview = null;
		recipeTitle = '';
		tags = [];
		tagsInput = '';
		isFavorite = false;
	}

	// ── Tags chip input ───────────────────────────────────────────────────────

	function handleTagKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' || event.key === ',') {
			event.preventDefault();
			addTag();
		}
	}

	function addTag() {
		const raw = tagsInput.trim().replace(/,$/, '');
		if (raw && !tags.includes(raw)) {
			tags = [...tags, raw];
		}
		tagsInput = '';
	}

	function removeTag(tag: string) {
		tags = tags.filter((t) => t !== tag);
	}

	// ── Save recipe ───────────────────────────────────────────────────────────

	async function saveRecipe() {
		if (!preview) return;

		addTag();

		try {
			if (import.meta.env.DEV) {
				await new Promise((r) => setTimeout(r, 300));
				await goto(`/recipes/${preview.id}`);
				return;
			}

			await fetch(`/api/recipes/${preview.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					title: recipeTitle,
					tags,
					favorite: isFavorite
				})
			});

			await goto(`/recipes/${preview.id}`);
		} catch {
			// Non-fatal — navigate anyway; user can edit later
			await goto(`/recipes/${preview.id}`);
		}
	}

	// ── Status strip text ─────────────────────────────────────────────────────

	let statusText = $derived(() => {
		switch (ingestState) {
			case 'fetching':
				return 'Fetching…';
			case 'parsing':
				return 'Reading the recipe…';
			case 'error-network':
				return "Can't reach that link. Check your connection.";
			case 'error-parse':
				return "Couldn't read that one.";
			case 'error-parse-llm':
				return "Still couldn't crack it. Want to add it by hand?";
			case 'error-duplicate':
				return "You've got this one.";
			default:
				return '';
		}
	});

	let sourceDomain = $derived(preview ? extractDomain(preview.sourceUrl) : '');
</script>

<svelte:head>
	<title>forkit — add recipe</title>
</svelte:head>

<main
	class="ingest-screen"
	aria-label="forkit — add recipe"
	data-state={ingestState}
>
	<!-- ── Wordmark ─────────────────────────────────────────────────────────── -->
	<div class="wordmark" aria-hidden="true">forkit</div>

	<!-- ── Hero ─────────────────────────────────────────────────────────────── -->
	<section class="hero">
		<h1 class="hero-question">got a recipe?</h1>
		<p class="hero-supporting">Paste a link to save it to your collection.</p>
	</section>

	<!-- ── Input zone ──────────────────────────────────────────────────────── -->
	<div class="input-zone">
		<!-- URL input -->
		<div class="url-field-wrap">
			<input
				bind:this={urlInputEl}
				bind:value={inputUrl}
				type="url"
				inputmode="url"
				autocomplete="off"
				autocorrect="off"
				autocapitalize="none"
				spellcheck={false}
				enterkeyhint="go"
				aria-label="Recipe URL"
				aria-describedby={urlError ? 'url-error' : undefined}
				aria-invalid={urlError ? 'true' : undefined}
				placeholder="paste a recipe link"
				readonly={isReadOnly}
				class="url-input"
				class:readonly={isReadOnly}
				oninput={handleUrlInput}
				onkeydown={handleKeydown}
			/>
			{#if hasText && !isReadOnly}
				<button
					type="button"
					class="clear-btn"
					aria-label="Clear URL"
					onclick={clearInput}
				>
					<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
						<circle cx="10" cy="10" r="10" fill="var(--color-ink-tertiary)" />
						<path d="M7 7l6 6M13 7l-6 6" stroke="white" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</button>
			{/if}
		</div>

		<!-- URL validation error -->
		{#if urlError}
			<p id="url-error" class="url-error" data-error="url" role="alert">
				{urlError}
			</p>
		{/if}

		<!-- Clipboard affordance strip -->
		{#if showClipboardStrip}
			<button
				type="button"
				class="clipboard-strip"
				onclick={useClipboardUrl}
				aria-label="From clipboard: {clipboardUrl}. Double-tap to use this link."
			>
				<span class="clipboard-strip-left">
					<svg class="clipboard-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
						<rect x="5" y="1" width="6" height="3" rx="1" stroke="var(--color-ink-tertiary)" stroke-width="1.2" />
						<path d="M4 3h-1a1 1 0 00-1 1v9a1 1 0 001 1h10a1 1 0 001-1V4a1 1 0 00-1-1h-1" stroke="var(--color-ink-tertiary)" stroke-width="1.2" stroke-linecap="round" />
					</svg>
					<span class="clipboard-domain">{clipboardDomain}</span>
				</span>
				<span class="clipboard-use">Use this</span>
			</button>

			<button type="button" class="paste-different-link" onclick={pasteDifferentLink}>
				or paste a different link
			</button>
		{/if}

		<!-- Status strip (loading / error) -->
		{#if ingestState !== 'idle' && ingestState !== 'preview'}
			<div
				class="status-strip"
				class:status-error={ingestState.startsWith('error') && ingestState !== 'error-duplicate'}
				class:status-warning={ingestState === 'error-duplicate'}
				role="alert"
				aria-live="assertive"
			>
				{#if isLoading}
					<span class="spinner" aria-hidden="true"></span>
				{:else}
					<svg class="status-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
						<circle
							cx="10" cy="10" r="9"
							stroke={ingestState === 'error-duplicate' ? 'var(--color-warning)' : 'var(--color-error)'}
							stroke-width="1.5"
						/>
						<path
							d="M10 6v5M10 13.5v.5"
							stroke={ingestState === 'error-duplicate' ? 'var(--color-warning)' : 'var(--color-error)'}
							stroke-width="1.5"
							stroke-linecap="round"
						/>
					</svg>
				{/if}
				<span class="status-text">{statusText()}</span>
			</div>
		{/if}

		<!-- Error action buttons -->
		{#if ingestState === 'error-parse'}
			<div class="error-actions">
				<button type="button" class="btn-primary" onclick={retryWithLlm}>Try with AI</button>
				<button type="button" class="btn-text-clay" onclick={resetToIdle}>paste it manually</button>
			</div>
		{/if}

		{#if ingestState === 'error-network'}
			<div class="error-actions">
				<button type="button" class="btn-primary" onclick={() => { ingestState = 'idle'; handleSubmit(); }}>
					Try again
				</button>
			</div>
		{/if}

		{#if ingestState === 'error-duplicate'}
			<div class="error-actions">
				<button type="button" class="btn-primary" onclick={() => goto(duplicateRecipeId ? `/recipes/${duplicateRecipeId}` : '/recipes')}>Open it</button>
				<button type="button" class="btn-text-secondary" onclick={handleSubmit}>Save a copy anyway</button>
			</div>
		{/if}

		{#if ingestState === 'error-parse-llm'}
			<div class="error-actions">
				<button type="button" class="btn-primary" onclick={resetToIdle}>Add manually</button>
				<button type="button" class="btn-text-secondary" onclick={() => goto('/')}>Give up</button>
			</div>
		{/if}

		<!-- Primary CTA — visible in idle state -->
		{#if ingestState === 'idle'}
			<button
				type="submit"
				class="btn-cta"
				class:disabled={!isValid}
				aria-disabled={!isValid}
				disabled={!isValid}
				onclick={handleSubmit}
			>
				save it
			</button>
		{/if}
	</div>

	<!-- Loading state marker for e2e -->
	{#if isLoading}
		<div data-state="loading" aria-hidden="true" style="display:none;"></div>
	{/if}

	<!-- ── Preview Card ─────────────────────────────────────────────────────── -->
	{#if ingestState === 'preview' && preview}
		<div class="preview-card" data-state="preview" role="region" aria-label="Recipe preview">
			<!-- Hero image -->
			<div class="card-hero">
				{#if preview.image}
					<img src={preview.image} alt={preview.title} class="card-hero-img" />
				{:else}
					<div class="card-hero-placeholder" aria-hidden="true"></div>
				{/if}
			</div>

			<!-- Card content -->
			<div class="card-content">
				<!-- Title -->
				<input
					type="text"
					class="card-title-input"
					bind:value={recipeTitle}
					placeholder="Untitled Recipe"
					aria-label="Recipe title"
					maxlength="120"
				/>

				<!-- Metadata row -->
				<div class="card-meta" aria-label="Recipe details">
					<span>
						<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
							<circle cx="7" cy="7" r="6" stroke="var(--color-ink-tertiary)" stroke-width="1.2"/>
							<path d="M7 4v3l2 1.5" stroke="var(--color-ink-tertiary)" stroke-width="1.2" stroke-linecap="round"/>
						</svg>
						{preview.ingredientCount ?? '—'} ingredients
					</span>
					<span class="meta-dot" aria-hidden="true">·</span>
					<span>{preview.totalTime ?? '—'}</span>
					<span class="meta-dot" aria-hidden="true">·</span>
					<span>serves {preview.serves ?? '—'}</span>
				</div>

				<!-- Source URL -->
				<a
					href={preview.sourceUrl}
					class="card-source"
					aria-label={preview.sourceUrl}
					target="_blank"
					rel="noopener noreferrer"
				>
					{sourceDomain}
				</a>

				<!-- Tags -->
				<div class="card-tags-section">
					<label class="tags-label" for="tags-input">tags</label>
					<div class="tags-chips" role="list">
						{#each tags as tag}
							<span class="tag-chip" role="listitem">
								{tag}
								<button
									type="button"
									class="tag-remove"
									onclick={() => removeTag(tag)}
									aria-label="Remove tag {tag}"
								>×</button>
							</span>
						{/each}
					</div>
					<input
						id="tags-input"
						type="text"
						class="tags-input"
						bind:value={tagsInput}
						placeholder="chicken, quick, weeknight"
						autocapitalize="none"
						autocorrect="off"
						enterkeyhint="done"
						onkeydown={handleTagKeydown}
						onblur={addTag}
						aria-label="Add tags — press Enter or comma to add"
					/>
				</div>

				<!-- Favorite toggle -->
				<button
					type="button"
					class="favorite-toggle"
					class:active={isFavorite}
					onclick={() => (isFavorite = !isFavorite)}
					aria-pressed={isFavorite}
					aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
				>
					<svg
						class="heart-icon"
						width="20"
						height="20"
						viewBox="0 0 20 20"
						fill={isFavorite ? 'var(--color-clay)' : 'none'}
						stroke={isFavorite ? 'var(--color-clay)' : 'var(--color-ink-tertiary)'}
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path d="M10 17s-7-4.35-7-9a4 4 0 018 0 4 4 0 018 0c0 4.65-7 9-7 9z" />
					</svg>
					<span class="favorite-label">Add to favorites</span>
				</button>

				<!-- Edit before saving -->
				<button type="button" class="edit-before-save">
					edit details before saving
				</button>

				<!-- Divider -->
				<div class="card-action-divider" aria-hidden="true"></div>

				<!-- Action row -->
				<div class="card-actions">
					<button type="button" class="btn-save-card" onclick={saveRecipe}>save it</button>
					<button type="button" class="btn-cancel-card" onclick={resetToIdle}>cancel</button>
				</div>
			</div>
		</div>
	{/if}
</main>

<style>
	/* ── Screen ──────────────────────────────────────────────────────────────── */
	.ingest-screen {
		min-height: 100dvh;
		background: var(--color-bone);
		display: flex;
		flex-direction: column;
		padding-top: env(safe-area-inset-top, 59px);
		padding-bottom: env(safe-area-inset-bottom, 34px);
		position: relative;
	}

	/* ── Wordmark ────────────────────────────────────────────────────────────── */
	.wordmark {
		position: absolute;
		top: calc(env(safe-area-inset-top, 59px) + 16px);
		left: 24px;
		font-family: var(--font-display);
		font-size: 18px;
		font-weight: 600;
		color: var(--color-ink);
		line-height: 1;
		user-select: none;
	}

	/* ── Hero ────────────────────────────────────────────────────────────────── */
	.hero {
		padding: 0 24px;
		padding-top: calc(35vh - 60px);
		margin-bottom: var(--space-8);
	}

	.hero-question {
		font-family: var(--font-display);
		font-size: 32px;
		font-weight: 600;
		color: var(--color-ink);
		line-height: 1.2;
		margin: 0 0 var(--space-3) 0;
	}

	.hero-supporting {
		font-family: var(--font-body);
		font-size: 18px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		line-height: 1.6;
		margin: 0;
	}

	/* ── Input zone ──────────────────────────────────────────────────────────── */
	.input-zone {
		padding: 0 24px;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.url-field-wrap {
		position: relative;
		display: flex;
		align-items: center;
	}

	.url-input {
		width: 100%;
		height: 56px;
		background: var(--color-surface);
		border: 2px solid var(--color-divider);
		border-radius: var(--radius-md);
		padding: 0 44px 0 16px;
		font-family: var(--font-body);
		font-size: 18px;
		font-weight: 400;
		color: var(--color-ink);
		box-shadow: var(--shadow-sm);
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
		-webkit-appearance: none;
		appearance: none;
	}

	.url-input::placeholder {
		color: var(--color-ink-tertiary);
	}

	.url-input:focus {
		outline: none;
		border-color: var(--color-clay);
		box-shadow: var(--shadow-focus);
	}

	.url-input.readonly {
		background: var(--color-bone-dim);
		pointer-events: none;
		color: var(--color-ink-secondary);
	}

	.clear-btn {
		position: absolute;
		right: 0;
		top: 0;
		width: 44px;
		height: 56px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
	}

	/* ── URL error ───────────────────────────────────────────────────────────── */
	.url-error {
		font-family: var(--font-body);
		font-size: 14px;
		color: var(--color-error);
		margin: 0;
		padding-left: 4px;
	}

	/* ── Clipboard strip ─────────────────────────────────────────────────────── */
	.clipboard-strip {
		display: flex;
		align-items: center;
		justify-content: space-between;
		height: 44px;
		background: var(--color-bone-dim);
		border-radius: var(--radius-md);
		padding: 0 12px;
		border: none;
		cursor: pointer;
		width: 100%;
		text-align: left;
	}

	.clipboard-strip:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
	}

	.clipboard-strip-left {
		display: flex;
		align-items: center;
		gap: 8px;
		overflow: hidden;
	}

	.clipboard-icon { flex-shrink: 0; }

	.clipboard-domain {
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.clipboard-use {
		font-family: var(--font-body);
		font-size: 14px;
		font-weight: 500;
		color: var(--color-clay);
		flex-shrink: 0;
		margin-left: 8px;
	}

	.paste-different-link {
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-tertiary);
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		text-align: left;
		min-height: 44px;
		display: flex;
		align-items: center;
	}

	/* ── Status strip ────────────────────────────────────────────────────────── */
	.status-strip {
		display: flex;
		align-items: center;
		gap: 8px;
		height: 44px;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
	}

	.status-strip.status-error { color: var(--color-error); }
	.status-strip.status-warning { color: var(--color-warning); }

	.status-text { line-height: 1; }

	/* Spinner */
	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--color-clay-dim);
		border-top-color: var(--color-clay);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
		flex-shrink: 0;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
			border-color: var(--color-clay-dim);
			border-top-color: var(--color-clay);
		}
	}

	.status-icon { flex-shrink: 0; }

	/* ── Error actions ───────────────────────────────────────────────────────── */
	.error-actions {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	/* ── Buttons ─────────────────────────────────────────────────────────────── */
	.btn-cta {
		width: 100%;
		height: 56px;
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 500;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		margin-top: var(--space-4);
		transition: background var(--transition-fast);
	}

	.btn-cta.disabled,
	.btn-cta:disabled {
		background: var(--color-clay-dim);
		color: var(--color-ink-tertiary);
		cursor: not-allowed;
	}

	.btn-primary {
		width: 100%;
		height: 48px;
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 500;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}

	.btn-text-clay {
		background: none;
		border: none;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-clay);
		cursor: pointer;
		min-height: 44px;
		padding: 0;
		text-align: left;
	}

	.btn-text-secondary {
		background: none;
		border: none;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		cursor: pointer;
		min-height: 44px;
		padding: 0;
		text-align: left;
	}

	/* ── Preview card ────────────────────────────────────────────────────────── */
	.preview-card {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		max-height: 75vh;
		background: var(--color-surface);
		border-radius: var(--radius-lg) var(--radius-lg) 0 0;
		box-shadow: var(--shadow-md);
		z-index: var(--z-sheet);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: slide-up var(--transition-slow) ease-in-out;
	}

	@keyframes slide-up {
		from { transform: translateY(100%); }
		to   { transform: translateY(0); }
	}

	@media (prefers-reduced-motion: reduce) {
		.preview-card { animation: none; }
	}

	.card-hero {
		flex-shrink: 0;
		height: 180px;
		width: 100%;
		overflow: hidden;
	}

	.card-hero-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.card-hero-placeholder {
		width: 100%;
		height: 100%;
		background: var(--color-bone-dim);
	}

	.card-content {
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: 16px 24px;
		display: flex;
		flex-direction: column;
		padding-bottom: env(safe-area-inset-bottom, 16px);
	}

	.card-title-input {
		font-family: var(--font-display);
		font-size: 24px;
		font-weight: 600;
		color: var(--color-ink);
		border: none;
		background: transparent;
		width: 100%;
		padding: 0;
		margin-bottom: 12px;
		outline: none;
		-webkit-appearance: none;
	}

	.card-title-input::placeholder { color: var(--color-ink-tertiary); }

	.card-title-input:focus {
		border-bottom: 1px solid var(--color-divider);
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: 6px;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		margin-bottom: 8px;
		flex-wrap: wrap;
	}

	.meta-dot { color: var(--color-ink-tertiary); }

	.card-source {
		font-family: var(--font-body);
		font-size: 13px;
		font-weight: 500;
		letter-spacing: 0.06em;
		color: var(--color-ink-tertiary);
		text-decoration: none;
		display: block;
		margin-bottom: 16px;
	}

	.card-source:hover { text-decoration: underline; }

	.card-tags-section { margin-bottom: 12px; }

	.tags-label {
		display: block;
		font-family: var(--font-body);
		font-size: 15px;
		font-weight: 500;
		letter-spacing: 0.05em;
		color: var(--color-ink-secondary);
		text-transform: lowercase;
		margin-bottom: 6px;
	}

	.tags-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 6px;
	}

	.tag-chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		background: var(--color-bone-dim);
		border-radius: var(--radius-sm);
		padding: 2px 8px;
		font-family: var(--font-body);
		font-size: 13px;
		font-weight: 500;
		letter-spacing: 0.06em;
		color: var(--color-ink-secondary);
	}

	.tag-remove {
		background: none;
		border: none;
		padding: 0 2px;
		cursor: pointer;
		color: var(--color-ink-tertiary);
		font-size: 14px;
		line-height: 1;
		min-width: 20px;
		min-height: 20px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.tags-input {
		width: 100%;
		height: 44px;
		background: var(--color-bone-dim);
		border: none;
		border-radius: var(--radius-md);
		padding: 0 12px;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink);
		-webkit-appearance: none;
		appearance: none;
	}

	.tags-input::placeholder { color: var(--color-ink-tertiary); }

	.tags-input:focus {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
	}

	.favorite-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 44px;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		text-align: left;
		margin-bottom: 8px;
	}

	.heart-icon {
		flex-shrink: 0;
		transition: fill var(--transition-fast), stroke var(--transition-fast);
	}

	.edit-before-save {
		background: none;
		border: none;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-clay);
		cursor: pointer;
		padding: 0;
		min-height: 44px;
		text-align: left;
		margin-bottom: 8px;
	}

	.card-action-divider {
		height: 1px;
		background: var(--color-divider);
		margin: 0 -24px;
		margin-bottom: 16px;
	}

	.card-actions {
		display: flex;
		gap: 24px;
		align-items: stretch;
		padding-bottom: 8px;
	}

	.btn-save-card {
		flex: 2;
		height: 56px;
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 500;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}

	.btn-cancel-card {
		flex: 1;
		height: 56px;
		background: none;
		border: none;
		font-family: var(--font-body);
		font-size: 16px;
		font-weight: 400;
		color: var(--color-ink-secondary);
		cursor: pointer;
	}
</style>
