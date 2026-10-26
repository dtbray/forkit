<script lang="ts">
	import '@fontsource-variable/inter';
	import '@fontsource-variable/source-serif-4';
	import '$lib/styles/tokens.css';
	import '$lib/styles/breakpoints.css';
	import '$lib/styles/themes.css';
	import ThemeSelect from '$lib/components/ThemeSelect.svelte';
	import { page } from '$app/stores';

	let { children } = $props();

	// Derive active nav item from current path
	let currentPath = $derived($page.url.pathname);
</script>

<svelte:head>
	<!-- Viewport: user-scalable=yes globally; cook view route overrides to no with in-app type controls -->
	<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />

	<!-- Apple PWA meta tags — ADR-001 §3g -->
	<meta name="apple-mobile-web-app-capable" content="yes" />
	<meta name="apple-mobile-web-app-status-bar-style" content="default" />
	<meta name="apple-mobile-web-app-title" content="forkit" />
	<link rel="apple-touch-icon" href="/icons/apple-touch-icon-180.png" />

	<!-- App favicon -->
	<link rel="icon" href="/icons/icon-192.png" type="image/png" />

	<!-- Fonts are self-hosted via @fontsource-variable — no external requests (LAN-safe) -->
</svelte:head>

<div class="app-shell">
	<!-- Primary navigation — hidden on ingest/cook views which manage their own chrome -->
	{#if !currentPath.startsWith('/ingest') && !currentPath.startsWith('/cook')}
		<nav class="app-nav" aria-label="Main navigation">
			<a
				href="/"
				class="nav-wordmark"
				aria-label="forkit — home"
				aria-current={currentPath === '/' ? 'page' : undefined}
			>
				forkit
			</a>

			<ul class="nav-links" role="list">
				<li>
					<a
						href="/recipes"
						aria-label="Library"
						class="nav-link"
						class:nav-link--active={currentPath.startsWith('/recipes')}
						aria-current={currentPath.startsWith('/recipes') ? 'page' : undefined}
					>
						<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" focusable="false">
							<path d="M9 2L3 7v9h12V7L9 2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" />
							<path d="M7 18v-6h4v6" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" />
						</svg>
						<span>Library</span>
					</a>
				</li>
				<li>
					<a
						href="/discover"
						aria-label="Discover"
						class="nav-link"
						class:nav-link--active={currentPath.startsWith('/discover')}
						aria-current={currentPath.startsWith('/discover') ? 'page' : undefined}
					>
						<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" focusable="false">
							<circle cx="9" cy="9" r="7.5" stroke="currentColor" stroke-width="1.4" />
							<path
								d="M9 3v1.5M9 13.5V15M3 9h1.5M13.5 9H15"
								stroke="currentColor"
								stroke-width="1.4"
								stroke-linecap="round"
							/>
							<path
								d="M11 7l-3 2-1 3 3-2 1-3z"
								fill="currentColor"
							/>
						</svg>
						<span>Discover</span>
					</a>
				</li>
				<li>
					<a
						href="/ingest"
						class="nav-link nav-link--add"
						aria-label="Add a recipe"
					>
						<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" focusable="false">
							<circle cx="9" cy="9" r="7.5" stroke="currentColor" stroke-width="1.4" />
							<path d="M9 5.5v7M5.5 9h7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
						</svg>
						<span>Add</span>
					</a>
				</li>
                <li><a href="/pantry" class="nav-link" class:nav-link--active={currentPath.startsWith('/pantry')} aria-current={currentPath.startsWith('/pantry') ? 'page' : undefined}>Pantry</a></li>
				<li><ThemeSelect /></li>
			</ul>
		</nav>
	{/if}

	{@render children()}
</div>

<style>
	:global(html, body) {
		margin: 0;
		padding: 0;
		background-color: var(--color-bg-primary);
		color: var(--color-text-primary);
		font-family: var(--font-body);
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	:global(*) {
		box-sizing: border-box;
	}

	:global(:focus-visible) {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	/* Never suppress focus rings — mock-spec §10 */
	:global(:focus:not(:focus-visible)) {
		outline: none;
	}

	.app-shell {
		min-height: 100dvh;
		display: flex;
		flex-direction: column;
	}

	/* ── App nav ─────────────────────────────────────────────────────────────── */
	.app-nav {
		display: flex;
		align-items: center;
		justify-content: space-between;
		height: 52px;
		padding: 0 var(--space-6);
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-divider);
		position: sticky;
		top: 0;
		z-index: var(--z-header);
	}

	.nav-wordmark {
		font-family: var(--font-display);
		font-size: 18px;
		font-weight: 600;
		color: var(--color-ink);
		text-decoration: none;
		line-height: 1;
		user-select: none;
	}

	.nav-wordmark:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		border-radius: var(--radius-sm);
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.nav-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: 36px;
		padding: 0 var(--space-3);
		border-radius: var(--radius-md);
		color: var(--color-ink-secondary);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		transition: color var(--transition-fast), background-color var(--transition-fast);
		white-space: nowrap;
	}

	.nav-link:hover {
		color: var(--color-ink);
		background: var(--color-bone);
	}

	.nav-link--active {
		color: var(--color-clay);
		background: var(--color-clay-dim);
	}

	.nav-link--active:hover {
		color: var(--color-clay-dark);
		background: var(--color-clay-dim);
	}

	.nav-link--add {
		background: var(--color-clay);
		color: var(--color-surface);
	}

	.nav-link--add:hover {
		background: var(--color-clay-dark);
		color: var(--color-surface);
	}

	.nav-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		box-shadow: var(--shadow-focus);
	}

	/* Hide text labels at narrow width; icons remain */
	@media (max-width: 480px) {
		.app-nav { padding: 0 var(--space-3); }
		.nav-link span { display: none; }
		.nav-link { padding: 0 var(--space-2); }
	}
</style>
