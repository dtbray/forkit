<script lang="ts">
	// SearchBar — debounced keyword input for the Discover page.
	// Fires onSearch after 400ms idle OR on Enter / Search button click.

	interface Props {
		onSearch: (q: string) => void;
		loading: boolean;
	}

	let { onSearch, loading }: Props = $props();

	let query = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inputEl: HTMLInputElement | null = null;

	function scheduleSearch() {
		if (debounceTimer) clearTimeout(debounceTimer);
		if (!query.trim()) {
			onSearch('');
			return;
		}
		debounceTimer = setTimeout(() => {
			onSearch(query.trim());
		}, 400);
	}

	function fireImmediately() {
		if (debounceTimer) clearTimeout(debounceTimer);
		if (query.trim()) {
			onSearch(query.trim());
		} else {
			onSearch('');
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			fireImmediately();
		}
	}

	function handleInput() {
		scheduleSearch();
	}

	function clearQuery() {
		query = '';
		if (debounceTimer) clearTimeout(debounceTimer);
		onSearch('');
		inputEl?.focus();
	}
</script>

<div class="search-bar" role="search" aria-label="Search recipes">
	<div class="search-field-wrap">
		<!-- compass/search icon -->
		<svg
			class="search-icon"
			width="20"
			height="20"
			viewBox="0 0 20 20"
			fill="none"
			aria-hidden="true"
			focusable="false"
		>
			<circle cx="9" cy="9" r="6.5" stroke="var(--color-ink-tertiary)" stroke-width="1.5" />
			<path
				d="M14 14l3.5 3.5"
				stroke="var(--color-ink-tertiary)"
				stroke-width="1.5"
				stroke-linecap="round"
			/>
		</svg>

		<input
			bind:this={inputEl}
			bind:value={query}
			type="search"
			inputmode="search"
			autocomplete="off"
			autocorrect="off"
			autocapitalize="none"
			spellcheck={false}
			enterkeyhint="search"
			placeholder="Search for recipes…"
			class="search-input"
			aria-label="Search recipes by keyword"
			disabled={loading}
			oninput={handleInput}
			onkeydown={handleKeydown}
		/>

		{#if query && !loading}
			<button
				type="button"
				class="clear-btn"
				aria-label="Clear search"
				onclick={clearQuery}
			>
				<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
					<circle cx="9" cy="9" r="9" fill="var(--color-ink-tertiary)" />
					<path
						d="M6 6l6 6M12 6l-6 6"
						stroke="white"
						stroke-width="1.4"
						stroke-linecap="round"
					/>
				</svg>
			</button>
		{/if}

		{#if loading}
			<span class="spinner" aria-hidden="true"></span>
		{/if}
	</div>

	<button
		type="button"
		class="search-btn"
		onclick={fireImmediately}
		disabled={loading || !query.trim()}
		aria-label="Search"
	>
		Search
	</button>
</div>

<style>
	.search-bar {
		display: flex;
		gap: var(--space-3);
		align-items: center;
	}

	.search-field-wrap {
		flex: 1;
		position: relative;
		display: flex;
		align-items: center;
	}

	.search-icon {
		position: absolute;
		left: 14px;
		pointer-events: none;
		flex-shrink: 0;
	}

	.search-input {
		width: 100%;
		height: 48px;
		background: var(--color-surface);
		border: 1.5px solid var(--color-divider);
		border-radius: var(--radius-md);
		padding: 0 44px 0 42px;
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: var(--text-body-sm-weight);
		color: var(--color-ink);
		box-shadow: var(--shadow-sm);
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
		appearance: none;
		-webkit-appearance: none;
	}

	/* hide browser's native search clear button */
	.search-input::-webkit-search-cancel-button {
		display: none;
	}

	.search-input::placeholder {
		color: var(--color-ink-tertiary);
	}

	.search-input:focus {
		outline: none;
		border-color: var(--color-clay);
		box-shadow: var(--shadow-focus);
	}

	.search-input:disabled {
		background: var(--color-bone-dim);
		color: var(--color-ink-tertiary);
		cursor: not-allowed;
	}

	.clear-btn {
		position: absolute;
		right: 10px;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
	}

	/* spinner sits in same slot as clear btn */
	.spinner {
		position: absolute;
		right: 12px;
		width: 18px;
		height: 18px;
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
			border-top-color: var(--color-clay);
		}
	}

	.search-btn {
		flex-shrink: 0;
		height: 48px;
		padding: 0 var(--space-5);
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: background-color var(--transition-fast);
		white-space: nowrap;
	}

	.search-btn:hover:not(:disabled) {
		background: var(--color-clay-dark);
	}

	.search-btn:disabled {
		background: var(--color-clay-dim);
		color: var(--color-ink-tertiary);
		cursor: not-allowed;
	}

	.search-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}
</style>
