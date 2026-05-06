<script lang="ts">
	let activeTab: 'tonight' | 'library' = $state('tonight');
</script>

<svelte:head>
	<title>forkit</title>
	<meta name="description" content="Your family recipe vault" />
</svelte:head>

<main>
	<!-- Tab bar — ADR-001 §3d: "Tonight" is suggestion-first home screen default -->
	<!-- Using <div role="tablist"> — ARIA tablist is not a native HTML role; <nav> would conflict -->
	<div class="tab-bar" role="tablist" aria-label="App navigation">
		<button
			role="tab"
			aria-selected={activeTab === 'tonight'}
			aria-controls="panel-tonight"
			id="tab-tonight"
			class="tab-btn"
			class:tab-btn--active={activeTab === 'tonight'}
			onclick={() => (activeTab = 'tonight')}
		>
			Tonight
		</button>
		<button
			role="tab"
			aria-selected={activeTab === 'library'}
			aria-controls="panel-library"
			id="tab-library"
			class="tab-btn"
			class:tab-btn--active={activeTab === 'library'}
			onclick={() => (activeTab = 'library')}
		>
			Library
		</button>
	</div>

	<!-- Tonight panel — suggestion-first per ADR-001 §3d -->
	<!-- Using <div role="tabpanel"> — tabpanel is a widget role, not a landmark; <section> would conflict -->
	<div
		id="panel-tonight"
		role="tabpanel"
		aria-labelledby="tab-tonight"
		hidden={activeTab !== 'tonight'}
		class="panel"
	>
		<h1 class="panel__heading">Tonight</h1>
		<p class="panel__placeholder">
			Recipe suggestions will appear here once your vault has recipes and cook history.
		</p>
	</div>

	<!-- Library panel — browseable recipe collection -->
	<div
		id="panel-library"
		role="tabpanel"
		aria-labelledby="tab-library"
		hidden={activeTab !== 'library'}
		class="panel"
	>
		<h1 class="panel__heading">Library</h1>
		<p class="panel__placeholder">Your saved recipes will appear here.</p>
	</div>
</main>

<style>
	main {
		flex: 1;
		display: flex;
		flex-direction: column;
	}

	/* ── Tab bar ── */
	.tab-bar {
		display: flex;
		border-bottom: 1px solid var(--color-border);
		background-color: var(--color-bg-primary);
		position: sticky;
		top: 0;
		z-index: var(--z-header);
	}

	.tab-btn {
		flex: 1;
		min-height: var(--touch-min); /* 44px WCAG minimum */
		padding: 0 var(--space-4);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		line-height: var(--text-ui-md-lh);
		color: var(--color-text-secondary);
		cursor: pointer;
		transition: color var(--transition-fast), border-color var(--transition-fast);
	}

	.tab-btn--active {
		color: var(--color-text-accent);
		border-bottom-color: var(--color-clay);
	}

	.tab-btn:hover:not(.tab-btn--active) {
		color: var(--color-text-primary);
	}

	/* ── Panels ── */
	.panel {
		flex: 1;
		padding: var(--space-8) var(--space-6);
	}

	.panel__heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-text-primary);
		margin: 0 0 var(--space-4);
	}

	.panel__placeholder {
		font-size: var(--text-body-md-size);
		font-weight: var(--text-body-md-weight);
		line-height: var(--text-body-md-lh);
		color: var(--color-text-secondary);
		margin: 0;
	}

	/* Tablet-up: constrain panel width for readability */
	@media (min-width: 768px) {
		.panel {
			padding: var(--space-10) var(--space-8);
			max-width: 960px;
			margin-inline: auto;
			width: 100%;
		}
	}
</style>
