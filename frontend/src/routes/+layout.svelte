<script lang="ts">
	import '@fontsource-variable/inter';
	import '@fontsource-variable/source-serif-4';
	import '$lib/styles/tokens.css';
	import '$lib/styles/breakpoints.css';

	let { children } = $props();
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
</style>
