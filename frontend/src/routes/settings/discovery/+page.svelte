<script lang="ts">
	// /settings/discovery — manage which sites are searched during discovery.

	import type { DiscoverySite } from '$lib/discovery/types.js';

	interface PageData {
		sites: DiscoverySite[];
		error: string | null;
	}

	let { data }: { data: PageData } = $props();

	// Snapshot page data into local state for optimistic UI mutations.
	// The state_referenced_locally warning is expected and intentional here.
	let sites: DiscoverySite[] = $state([...data.sites]);
	let loadError: string | null = $state(data.error);

	// Per-site test states
	type TestState = 'idle' | 'testing' | 'ok' | 'error';
	let testStates = $state<Record<string, TestState>>({});
	let testMessages = $state<Record<string, string>>({});

	// Per-site toggle pending states
	let togglePending = $state<Record<string, boolean>>({});

	// ── Toggle search_enabled ─────────────────────────────────────────────────────

	async function handleToggle(site: DiscoverySite) {
		if (togglePending[site.id]) return;

		togglePending = { ...togglePending, [site.id]: true };

		// Optimistic update
		const prevValue = site.search_enabled;
		sites = sites.map((s) =>
			s.id === site.id ? { ...s, search_enabled: !s.search_enabled } : s
		);

		try {
			const res = await fetch(`/api/discovery/sites/${site.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ search_enabled: !prevValue })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch {
			// Revert on failure
			sites = sites.map((s) =>
				s.id === site.id ? { ...s, search_enabled: prevValue } : s
			);
		} finally {
			togglePending = { ...togglePending, [site.id]: false };
		}
	}

	// ── Toggle feed_enabled ───────────────────────────────────────────────────────

	async function handleFeedToggle(site: DiscoverySite) {
		if (togglePending[site.id]) return;

		togglePending = { ...togglePending, [site.id]: true };

		const prevValue = site.feed_enabled;
		sites = sites.map((s) =>
			s.id === site.id ? { ...s, feed_enabled: !s.feed_enabled } : s
		);

		try {
			const res = await fetch(`/api/discovery/sites/${site.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ feed_enabled: !prevValue })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch {
			sites = sites.map((s) =>
				s.id === site.id ? { ...s, feed_enabled: prevValue } : s
			);
		} finally {
			togglePending = { ...togglePending, [site.id]: false };
		}
	}

	// ── Test site ──────────────────────────────────────────────────────────────────

	async function handleTest(site: DiscoverySite) {
		if (testStates[site.id] === 'testing') return;
		testStates = { ...testStates, [site.id]: 'testing' };
		testMessages = { ...testMessages, [site.id]: '' };

		try {
			const res = await fetch(`/api/discovery/sites/${site.id}/test`, {
				method: 'POST'
			});
			const body = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
			testStates = { ...testStates, [site.id]: 'ok' };
			testMessages = {
				...testMessages,
				[site.id]: body?.message ?? 'Site responded OK'
			};
		} catch (err) {
			testStates = { ...testStates, [site.id]: 'error' };
			testMessages = {
				...testMessages,
				[site.id]: err instanceof Error ? err.message : 'Test failed'
			};
		}
	}

	// ── Adapter kind display ──────────────────────────────────────────────────────

	function adapterLabel(kind: string): string {
		const labels: Record<string, string> = {
			rss: 'RSS',
			html: 'HTML',
			api: 'API',
			playwright: 'Playwright'
		};
		return labels[kind] ?? kind;
	}
</script>

<svelte:head>
	<title>Discovery Settings — forkit</title>
	<meta name="description" content="Manage which sites are searched in Discover" />
</svelte:head>

<main class="settings-page">
	<!-- ── Page header ──────────────────────────────────────────────────────────── -->
	<header class="page-header">
		<a href="/discover" class="back-link" aria-label="Back to Discover">
			<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
				<path d="M11 4L6 9l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
			Discover
		</a>
		<h1 class="page-title">Discovery Sites</h1>
		<p class="page-subtitle">
			Enable or disable sites searched when you use Discover. Toggle to include a site; test to verify it's responding.
		</p>
	</header>

	{#if loadError}
		<!-- Error loading sites -->
		<div class="load-error" role="alert">
			<p class="load-error-text">Could not load sites: {loadError}</p>
			<a href="/settings/discovery" class="btn-retry-link">Reload</a>
		</div>
	{:else if sites.length === 0}
		<div class="empty-state" role="status">
			<p class="empty-body">No discovery sites configured yet.</p>
		</div>
	{:else}
		<!-- ── Site list ──────────────────────────────────────────────────────────── -->
		<ul class="site-list" role="list" aria-label="Discovery sites">
			{#each sites as site (site.id)}
				<li class="site-row">
					<!-- Site info -->
					<div class="site-info">
						<div class="site-name-row">
							<span class="site-name">{site.name}</span>
							<span class="adapter-badge" aria-label="Adapter: {adapterLabel(site.adapter_kind)}">
								{adapterLabel(site.adapter_kind)}
							</span>
							{#if site.paywall_note}
								<span
									class="paywall-badge"
									title={site.paywall_note}
									aria-label="Paywall warning: {site.paywall_note}"
								>
									<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
										<circle cx="6" cy="6" r="5.5" stroke="var(--color-warning)" stroke-width="1" />
										<path d="M6 3.5v3M6 8v.5" stroke="var(--color-warning)" stroke-width="1.2" stroke-linecap="round" />
									</svg>
									Paywall
								</span>
							{/if}
						</div>
						<a
							href={site.home_url}
							class="site-url"
							target="_blank"
							rel="noopener noreferrer"
							aria-label="{site.name} website — opens in new tab"
						>
							{site.home_url.replace(/^https?:\/\//, '')}
						</a>

						<!-- Test result inline -->
						{#if testStates[site.id] && testStates[site.id] !== 'idle'}
							<div
								class="test-result"
								class:test-result--ok={testStates[site.id] === 'ok'}
								class:test-result--error={testStates[site.id] === 'error'}
								role="status"
								aria-live="polite"
							>
								{#if testStates[site.id] === 'testing'}
									<span class="inline-spinner" aria-hidden="true"></span>
									<span>Testing…</span>
								{:else if testStates[site.id] === 'ok'}
									<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
										<circle cx="6" cy="6" r="5.5" stroke="var(--color-success)" stroke-width="1" />
										<path d="M3.5 6l2 2 3-3" stroke="var(--color-success)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
									</svg>
									<span>{testMessages[site.id]}</span>
								{:else}
									<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
										<circle cx="6" cy="6" r="5.5" stroke="var(--color-error)" stroke-width="1" />
										<path d="M6 3.5v3M6 8v.5" stroke="var(--color-error)" stroke-width="1.2" stroke-linecap="round" />
									</svg>
									<span>{testMessages[site.id]}</span>
								{/if}
							</div>
						{/if}
					</div>

					<!-- Controls -->
					<div class="site-controls">
						<!-- Test button -->
						<button
							type="button"
							class="btn-test"
							onclick={() => handleTest(site)}
							disabled={testStates[site.id] === 'testing'}
							aria-label="Test {site.name}"
							aria-busy={testStates[site.id] === 'testing'}
						>
							Test
						</button>

						<!-- search_enabled toggle -->
						<div class="toggle-group">
							<span class="toggle-caption">Search</span>
							<label class="toggle-label" aria-label="Enable {site.name} in search">
								<input
									type="checkbox"
									class="sr-only"
									checked={site.search_enabled}
									disabled={togglePending[site.id]}
									onchange={() => handleToggle(site)}
									aria-label="{site.search_enabled ? 'Disable' : 'Enable'} {site.name} in search"
								/>
								<span
									class="toggle-track"
									class:toggle-track--on={site.search_enabled}
									aria-hidden="true"
								>
									<span class="toggle-thumb"></span>
								</span>
							</label>
						</div>

						<!-- feed_enabled toggle -->
						<div class="toggle-group">
							<span class="toggle-caption">Feed</span>
							<label class="toggle-label" aria-label="Enable {site.name} feed">
								<input
									type="checkbox"
									class="sr-only"
									checked={site.feed_enabled}
									disabled={togglePending[site.id]}
									onchange={() => handleFeedToggle(site)}
									aria-label="{site.feed_enabled ? 'Disable' : 'Enable'} {site.name} feed"
								/>
								<span
									class="toggle-track"
									class:toggle-track--on={site.feed_enabled}
									aria-hidden="true"
								>
									<span class="toggle-thumb"></span>
								</span>
							</label>
						</div>
					</div>
				</li>
			{/each}
		</ul>
	{/if}

	<!-- ── Legend ────────────────────────────────────────────────────────────── -->
	<div class="legend" aria-label="Legend">
		<div class="legend-item">
			<span class="adapter-badge">RSS</span> — RSS/Atom feed adapter
		</div>
		<div class="legend-item">
			<span class="adapter-badge">HTML</span> — structured markup parser
		</div>
		<div class="legend-item">
			<span class="paywall-badge">
				<svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true">
					<circle cx="6" cy="6" r="5.5" stroke="var(--color-warning)" stroke-width="1" />
					<path d="M6 3.5v3M6 8v.5" stroke="var(--color-warning)" stroke-width="1.2" stroke-linecap="round" />
				</svg>
				Paywall
			</span> — some content may be gated
		</div>
	</div>
</main>

<style>
	.settings-page {
		flex: 1;
		padding: var(--space-6);
		background: var(--color-bone);
		max-width: 720px;
		margin-inline: auto;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	/* Screen reader only */
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
		flex-direction: column;
		gap: var(--space-2);
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		color: var(--color-clay);
		text-decoration: none;
		min-height: var(--touch-min);
		align-self: flex-start;
	}

	.back-link:hover {
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.back-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: var(--radius-sm);
	}

	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		color: var(--color-ink);
		margin: 0;
	}

	.page-subtitle {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		line-height: var(--text-body-sm-lh);
		color: var(--color-ink-secondary);
		margin: 0;
		max-width: 52ch;
	}

	/* ── Error / empty ───────────────────────────────────────────────────────── */
	.load-error {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		border-left: 3px solid var(--color-error);
	}

	.load-error-text {
		flex: 1;
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-error);
		margin: 0;
	}

	.btn-retry-link {
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: 500;
		color: var(--color-clay);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.empty-state {
		text-align: center;
		padding: var(--space-12);
	}

	.empty-body {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
		margin: 0;
	}

	/* ── Site list ────────────────────────────────────────────────────────────── */
	.site-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.site-row {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		padding: var(--space-4) var(--space-5);
		transition: box-shadow var(--transition-fast);
	}

	.site-row:hover {
		box-shadow: var(--shadow-md);
	}

	/* ── Site info ───────────────────────────────────────────────────────────── */
	.site-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.site-name-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}

	.site-name {
		font-family: var(--font-display);
		font-size: var(--text-heading-sm-size);
		font-weight: var(--text-heading-sm-weight);
		color: var(--color-ink);
	}

	.adapter-badge {
		display: inline-flex;
		align-items: center;
		height: 20px;
		padding: 0 6px;
		border-radius: var(--radius-sm);
		background: var(--color-bone-dim);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-secondary);
		white-space: nowrap;
	}

	.paywall-badge {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		height: 20px;
		padding: 0 6px;
		border-radius: var(--radius-sm);
		background: rgba(140, 106, 31, 0.12);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		color: var(--color-warning);
		white-space: nowrap;
	}

	.site-url {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-tertiary);
		text-decoration: none;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.site-url:hover {
		color: var(--color-clay);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.site-url:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: 2px;
	}

	/* ── Test result inline ──────────────────────────────────────────────────── */
	.test-result {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-secondary);
		margin-top: var(--space-1);
	}

	.test-result--ok  { color: var(--color-success); }
	.test-result--error { color: var(--color-error); }

	.inline-spinner {
		width: 12px;
		height: 12px;
		border: 1.5px solid var(--color-clay-dim);
		border-top-color: var(--color-clay);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
		flex-shrink: 0;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@media (prefers-reduced-motion: reduce) {
		.inline-spinner { animation: none; }
	}

	/* ── Controls ────────────────────────────────────────────────────────────── */
	.site-controls {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		flex-shrink: 0;
	}

	.toggle-group {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}

	.toggle-caption {
		font-family: var(--font-body);
		font-size: 10px;
		color: var(--color-ink-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.btn-test {
		height: 32px;
		padding: 0 var(--space-3);
		background: none;
		border: 1.5px solid var(--color-divider);
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		color: var(--color-ink-secondary);
		cursor: pointer;
		transition: border-color var(--transition-fast), color var(--transition-fast);
		min-height: 32px;
		white-space: nowrap;
	}

	.btn-test:hover:not(:disabled) {
		border-color: var(--color-clay);
		color: var(--color-clay);
	}

	.btn-test:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-test:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		box-shadow: var(--shadow-focus);
	}

	/* ── Toggle switch ───────────────────────────────────────────────────────── */
	.toggle-label {
		display: inline-flex;
		align-items: center;
		cursor: pointer;
	}

	.toggle-track {
		display: flex;
		align-items: center;
		width: 44px;
		height: 26px;
		border-radius: var(--radius-full);
		background: var(--color-divider);
		padding: 3px;
		transition: background-color var(--transition-fast);
		position: relative;
	}

	.toggle-track--on {
		background: var(--color-clay);
	}

	.toggle-thumb {
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: white;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
		transition: transform var(--transition-fast);
		flex-shrink: 0;
	}

	.toggle-track--on .toggle-thumb {
		transform: translateX(18px);
	}

	/* Connect native checkbox focus ring to track */
	.toggle-label:has(input:focus-visible) .toggle-track {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		box-shadow: var(--shadow-focus);
	}

	@media (prefers-reduced-motion: reduce) {
		.toggle-thumb,
		.toggle-track {
			transition: none;
		}
	}

	/* ── Legend ──────────────────────────────────────────────────────────────── */
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
	}

	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-ink-secondary);
	}

	/* ── Mobile adjustments ──────────────────────────────────────────────────── */
	@media (max-width: 479px) {
		.site-row {
			flex-wrap: wrap;
		}

		.site-controls {
			width: 100%;
			justify-content: flex-end;
		}
	}
</style>
