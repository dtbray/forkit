<script lang="ts">
	// Discover layout — provides the Search / Inbox tab sub-nav shared between
	// /discover and /discover/inbox.

	import { page } from '$app/stores';

	let { children } = $props();

	let currentPath = $derived($page.url.pathname);
	let isInbox = $derived(currentPath.startsWith('/discover/inbox'));
</script>

<div class="discover-layout">
	<!-- Sub-nav tabs -->
	<nav class="discover-tabs" aria-label="Discover navigation">
		<a
			href="/discover"
			class="discover-tab"
			class:discover-tab--active={!isInbox}
			aria-current={!isInbox ? 'page' : undefined}
		>
			Search
		</a>
		<a
			href="/discover/inbox"
			class="discover-tab"
			class:discover-tab--active={isInbox}
			aria-current={isInbox ? 'page' : undefined}
		>
			Inbox
		</a>
	</nav>

	{@render children()}
</div>

<style>
	.discover-layout {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
	}

	/* ── Tab sub-nav ── */
	.discover-tabs {
		display: flex;
		align-items: center;
		gap: 0;
		padding: 0 var(--space-6);
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-divider);
	}

	.discover-tab {
		display: inline-flex;
		align-items: center;
		height: 40px;
		padding: 0 var(--space-4);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		color: var(--color-ink-secondary);
		text-decoration: none;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px; /* overlap the border-bottom of the nav */
		transition:
			color var(--transition-fast),
			border-color var(--transition-fast);
		white-space: nowrap;
	}

	.discover-tab:hover {
		color: var(--color-ink);
	}

	.discover-tab--active {
		color: var(--color-clay);
		border-bottom-color: var(--color-clay);
		font-weight: 600;
	}

	.discover-tab:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: -2px;
		border-radius: var(--radius-sm);
	}
</style>
