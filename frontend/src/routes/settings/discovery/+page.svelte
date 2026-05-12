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

	// ── Drawer ────────────────────────────────────────────────────────────────────

	let drawerOpen = $state(false);
	let drawerMode = $state<'add' | 'edit'>('add');
	let editingSite = $state<DiscoverySite | null>(null);

	// ── Detect ───────────────────────────────────────────────────────────────────

	interface DetectResult {
		input_url: string;
		site_name: string;
		is_feed: boolean;
		detected_feeds: string[];
		suggested_search_url_template: string | null;
		confidence: 'high' | 'partial' | 'none';
	}

	let detectUrl = $state('');
	let detectLoading = $state(false);
	let detectError = $state<string | null>(null);
	let detectResult = $state<DetectResult | null>(null);

	// ── Form ──────────────────────────────────────────────────────────────────────

	interface SiteForm {
		name: string;
		home_url: string;
		adapter_kind: string;
		feed_url: string;
		search_url_template: string;
		search_enabled: boolean;
		feed_enabled: boolean;
		paywall_note: string;
	}

	function emptyForm(): SiteForm {
		return {
			name: '',
			home_url: '',
			adapter_kind: 'html_scrape',
			feed_url: '',
			search_url_template: '',
			search_enabled: true,
			feed_enabled: false,
			paywall_note: ''
		};
	}

	let form = $state<SiteForm>(emptyForm());
	let formError = $state<string | null>(null);
	let submitPending = $state(false);

	// ── Undo toast ────────────────────────────────────────────────────────────────

	let undoToast = $state<DiscoverySite | null>(null);
	let undoTimer = $state<ReturnType<typeof setTimeout> | null>(null);

	// ── Slug helper ───────────────────────────────────────────────────────────────

	function slugFromUrl(url: string): string {
		try {
			const h = new URL(url).hostname.replace(/^www\./, '');
			return h.replace(/[^a-z0-9]/gi, '_').toLowerCase();
		} catch {
			return 'site_' + Date.now();
		}
	}

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
			playwright: 'Playwright',
			feed_only: 'Feed',
			html_scrape: 'HTML Scrape'
		};
		return labels[kind] ?? kind;
	}

	// ── Drawer open/close ─────────────────────────────────────────────────────────

	function openAdd() {
		drawerMode = 'add';
		editingSite = null;
		form = emptyForm();
		detectUrl = '';
		detectResult = null;
		detectError = null;
		formError = null;
		drawerOpen = true;
	}

	function openEdit(site: DiscoverySite) {
		drawerMode = 'edit';
		editingSite = site;
		form = {
			name: site.name,
			home_url: site.home_url,
			adapter_kind: site.adapter_kind,
			feed_url: '',
			search_url_template: '',
			search_enabled: site.search_enabled,
			feed_enabled: site.feed_enabled,
			paywall_note: site.paywall_note ?? ''
		};
		detectUrl = '';
		detectResult = null;
		detectError = null;
		formError = null;
		drawerOpen = true;
	}

	function closeDrawer() {
		drawerOpen = false;
	}

	// ── Detect ────────────────────────────────────────────────────────────────────

	async function runDetect() {
		const url = detectUrl.trim();
		if (!url) return;
		detectLoading = true;
		detectError = null;
		detectResult = null;
		try {
			const res = await fetch('/api/discovery/sites/detect', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data?.detail ?? `HTTP ${res.status}`);
			detectResult = data as DetectResult;
			if (data.site_name) form.name = data.site_name;
			form.home_url = url;
			if (data.is_feed || data.detected_feeds?.length) {
				form.adapter_kind = 'feed_only';
				if (data.is_feed) form.feed_url = url;
				else if (data.detected_feeds[0]) form.feed_url = data.detected_feeds[0];
			} else if (data.suggested_search_url_template) {
				form.adapter_kind = 'html_scrape';
				form.search_url_template = data.suggested_search_url_template;
			}
		} catch (err) {
			detectError = err instanceof Error ? err.message : 'Detection failed';
		} finally {
			detectLoading = false;
		}
	}

	// ── Submit ────────────────────────────────────────────────────────────────────

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		formError = null;
		submitPending = true;
		try {
			if (drawerMode === 'add') {
				const config: Record<string, string> = {};
				if (form.adapter_kind === 'feed_only' && form.feed_url) config.feed_url = form.feed_url;
				if (form.adapter_kind === 'html_scrape' && form.search_url_template)
					config.search_url_template = form.search_url_template;
				const body = {
					slug: slugFromUrl(form.home_url),
					name: form.name.trim(),
					home_url: form.home_url.trim(),
					adapter_kind: form.adapter_kind,
					adapter_config_json: Object.keys(config).length ? config : undefined,
					search_enabled: form.search_enabled,
					feed_enabled: form.feed_enabled,
					paywall_note: form.paywall_note.trim() || null
				};
				const res = await fetch('/api/discovery/sites', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(body)
				});
				const data = await res.json().catch(() => ({}));
				if (!res.ok) throw new Error(data?.detail ?? `HTTP ${res.status}`);
				sites = [...sites, data as DiscoverySite];
				closeDrawer();
			} else {
				if (!editingSite) return;
				const body: Record<string, unknown> = {
					name: form.name.trim(),
					home_url: form.home_url.trim(),
					search_enabled: form.search_enabled,
					feed_enabled: form.feed_enabled,
					paywall_note: form.paywall_note.trim() || null
				};
				const config: Record<string, string> = {};
				if (form.adapter_kind === 'feed_only' && form.feed_url) config.feed_url = form.feed_url;
				if (form.adapter_kind === 'html_scrape' && form.search_url_template)
					config.search_url_template = form.search_url_template;
				if (Object.keys(config).length) body.adapter_config_json = config;
				const res = await fetch(`/api/discovery/sites/${editingSite.id}`, {
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(body)
				});
				const data = await res.json().catch(() => ({}));
				if (!res.ok) throw new Error(data?.detail ?? `HTTP ${res.status}`);
				sites = sites.map((s) => (s.id === editingSite!.id ? (data as DiscoverySite) : s));
				closeDrawer();
			}
		} catch (err) {
			formError = err instanceof Error ? err.message : 'Save failed';
		} finally {
			submitPending = false;
		}
	}

	// ── Delete ────────────────────────────────────────────────────────────────────

	async function handleDelete() {
		if (!editingSite) return;
		const deleted = editingSite;
		sites = sites.filter((s) => s.id !== deleted.id);
		closeDrawer();
		if (undoTimer) clearTimeout(undoTimer);
		undoToast = deleted;
		undoTimer = setTimeout(() => {
			fetch(`/api/discovery/sites/${deleted.id}`, { method: 'DELETE' }).catch(() => {});
			undoToast = null;
		}, 8000);
	}

	async function handleUndo() {
		if (!undoToast) return;
		const restored = undoToast;
		undoToast = null;
		if (undoTimer) clearTimeout(undoTimer);
		sites = [...sites, restored];
	}
</script>

<svelte:head>
	<title>Discovery Settings — forkit</title>
	<meta name="description" content="Manage which sites are searched in Discover" />
</svelte:head>

<main class="settings-page">
	<!-- ── Page header ──────────────────────────────────────────────────────────── -->
	<header class="page-header">
		<div class="page-header-top">
			<div class="page-header-text">
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
			</div>
			<button type="button" class="btn-add-site" onclick={openAdd}>Add site</button>
		</div>
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
					<!-- Site info — clickable to open edit drawer -->
					<button type="button" class="site-row-btn" onclick={() => openEdit(site)} aria-label="Edit {site.name}">
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
							<span class="site-url">
								{site.home_url.replace(/^https?:\/\//, '')}
							</span>

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
					</button>

					<!-- Controls (outside clickable area) -->
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

	<!-- ── Drawer ──────────────────────────────────────────────────────────────── -->
	{#if drawerOpen}
		<div class="drawer-backdrop" onclick={closeDrawer} aria-hidden="true"></div>

		<aside class="drawer" aria-label="Site settings" role="dialog" aria-modal="true">
			<header class="drawer-header">
				<h2 class="drawer-title">{drawerMode === 'add' ? 'Add site' : 'Edit site'}</h2>
				<button type="button" class="drawer-close" onclick={closeDrawer} aria-label="Close">
					<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
						<path d="M4 4l10 10M14 4L4 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
					</svg>
				</button>
			</header>

			<!-- ADD MODE: detect bar -->
			{#if drawerMode === 'add'}
				<div class="detect-bar">
					<input
						type="url"
						bind:value={detectUrl}
						placeholder="https://..."
						class="detect-input"
					/>
					<button type="button" class="btn-detect" onclick={runDetect} disabled={detectLoading}>
						{detectLoading ? 'Detecting…' : 'Detect'}
					</button>
				</div>
				{#if detectError}
					<p class="detect-error" role="alert">{detectError}</p>
				{/if}
				{#if detectResult}
					{#if detectResult.confidence === 'high'}
						<div class="detect-banner detect-banner--high">Feed detected</div>
					{:else if detectResult.confidence === 'partial'}
						<div class="detect-banner detect-banner--partial">Search pattern detected — verify below</div>
					{/if}
				{/if}
			{/if}

			<!-- Form (both modes) -->
			<form class="drawer-form" onsubmit={handleSubmit}>
				<label class="field-label" for="field-name">Name</label>
				<input id="field-name" type="text" bind:value={form.name} class="field-input" required />

				<label class="field-label" for="field-url">Home URL</label>
				<input id="field-url" type="url" bind:value={form.home_url} class="field-input" required />

				<label class="field-label" for="field-adapter">Adapter type</label>
				{#if drawerMode === 'add'}
					<select id="field-adapter" bind:value={form.adapter_kind} class="field-select">
						<option value="html_scrape">HTML Scrape</option>
						<option value="feed_only">Feed Only</option>
					</select>
				{:else}
					<p class="field-readonly" id="field-adapter">{adapterLabel(form.adapter_kind)}</p>
				{/if}

				{#if form.adapter_kind === 'feed_only'}
					<label class="field-label" for="field-feed-url">Feed URL</label>
					<input id="field-feed-url" type="url" bind:value={form.feed_url} class="field-input" />
				{/if}

				{#if form.adapter_kind === 'html_scrape'}
					<label class="field-label" for="field-search-tpl">
						Search URL template <span class="field-hint">(optional)</span>
					</label>
					<input
						id="field-search-tpl"
						type="text"
						bind:value={form.search_url_template}
						class="field-input"
						placeholder="https://example.com/search?q={'{query}'}"
					/>
				{/if}

				<label class="field-label" for="field-paywall">
					Paywall note <span class="field-hint">(optional)</span>
				</label>
				<input
					id="field-paywall"
					type="text"
					bind:value={form.paywall_note}
					class="field-input"
					placeholder="Subscription required for full recipes"
				/>

				<div class="form-toggles">
					<label class="form-toggle-label">
						<input type="checkbox" bind:checked={form.search_enabled} class="sr-only" />
						<span class="toggle-track" class:toggle-track--on={form.search_enabled} aria-hidden="true">
							<span class="toggle-thumb"></span>
						</span>
						Search
					</label>
					<label class="form-toggle-label">
						<input type="checkbox" bind:checked={form.feed_enabled} class="sr-only" />
						<span class="toggle-track" class:toggle-track--on={form.feed_enabled} aria-hidden="true">
							<span class="toggle-thumb"></span>
						</span>
						Feed
					</label>
				</div>

				{#if formError}
					<p class="form-error" role="alert">{formError}</p>
				{/if}

				<button type="submit" class="btn-submit" disabled={submitPending}>
					{submitPending ? 'Saving…' : drawerMode === 'add' ? 'Add site' : 'Save changes'}
				</button>
			</form>

			<!-- Delete (edit mode, non-builtin only) -->
			{#if drawerMode === 'edit' && editingSite && !editingSite.is_builtin}
				<div class="drawer-delete-zone">
					<button type="button" class="btn-delete-link" onclick={handleDelete}>
						Remove site
					</button>
				</div>
			{/if}
		</aside>
	{/if}

	<!-- ── Undo toast ─────────────────────────────────────────────────────────── -->
	{#if undoToast}
		<div class="undo-toast" role="status" aria-live="polite">
			<span>Site removed.</span>
			<button type="button" class="btn-undo" onclick={handleUndo}>Undo</button>
		</div>
	{/if}
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

	.page-header-top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-4);
	}

	.page-header-text {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		flex: 1;
		min-width: 0;
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

	/* ── Site row button wrapper ── */
	.site-row-btn {
		flex: 1;
		min-width: 0;
		background: none;
		border: none;
		padding: 0;
		text-align: left;
		cursor: pointer;
	}

	.site-row-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
		border-radius: var(--radius-sm);
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
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		display: block;
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

	/* ── Add button ── */
	.btn-add-site {
		height: var(--touch-min);
		padding: 0 var(--space-5);
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		white-space: nowrap;
		flex-shrink: 0;
		transition: background-color var(--transition-fast);
	}
	.btn-add-site:hover { background: var(--color-clay-dark); }
	.btn-add-site:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 3px; }

	/* ── Drawer backdrop ── */
	.drawer-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.3);
		z-index: 100;
	}

	/* ── Drawer panel ── */
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(440px, 100vw);
		background: var(--color-surface);
		box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
		z-index: 101;
		display: flex;
		flex-direction: column;
		overflow-y: auto;
	}

	/* ── Drawer header ── */
	.drawer-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-5) var(--space-6);
		border-bottom: 1px solid var(--color-divider);
		flex-shrink: 0;
	}
	.drawer-title {
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size);
		font-weight: var(--text-heading-md-weight);
		color: var(--color-ink);
		margin: 0;
	}
	.drawer-close {
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		background: none;
		border: none;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--color-ink-tertiary);
		transition: color var(--transition-fast), background-color var(--transition-fast);
	}
	.drawer-close:hover { background: var(--color-bone); color: var(--color-ink); }
	.drawer-close:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 2px; }

	/* ── Detect bar ── */
	.detect-bar {
		display: flex;
		gap: var(--space-2);
		padding: var(--space-4) var(--space-6) 0;
	}
	.detect-input {
		flex: 1;
		height: 40px;
		padding: 0 var(--space-3);
		border: 1.5px solid var(--color-divider);
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink);
		background: var(--color-bone);
		transition: border-color var(--transition-fast);
	}
	.detect-input:focus { outline: none; border-color: var(--color-clay); }
	.btn-detect {
		height: 40px;
		padding: 0 var(--space-4);
		flex-shrink: 0;
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: background-color var(--transition-fast);
	}
	.btn-detect:hover:not(:disabled) { background: var(--color-clay-dark); }
	.btn-detect:disabled { opacity: 0.6; cursor: not-allowed; }
	.btn-detect:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 2px; }
	.detect-error {
		margin: var(--space-2) var(--space-6) 0;
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-error);
	}

	/* ── Detect banner ── */
	.detect-banner {
		margin: var(--space-3) var(--space-6) 0;
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: 500;
	}
	.detect-banner--high { background: rgba(0, 140, 60, 0.1); color: #007a38; }
	.detect-banner--partial { background: rgba(140, 106, 31, 0.1); color: var(--color-warning); }

	/* ── Form ── */
	.drawer-form {
		flex: 1;
		padding: var(--space-5) var(--space-6);
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.field-label {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		color: var(--color-ink-secondary);
		display: block;
		margin-bottom: -var(--space-2);
	}
	.field-hint {
		font-weight: 400;
		color: var(--color-ink-tertiary);
	}
	.field-input,
	.field-select {
		width: 100%;
		height: 40px;
		padding: 0 var(--space-3);
		border: 1.5px solid var(--color-divider);
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink);
		background: var(--color-bone);
		transition: border-color var(--transition-fast);
		box-sizing: border-box;
	}
	.field-input:focus,
	.field-select:focus { outline: none; border-color: var(--color-clay); }
	.field-readonly {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink-secondary);
		margin: 0;
		padding: var(--space-2) 0;
	}

	/* Form toggles */
	.form-toggles {
		display: flex;
		gap: var(--space-5);
	}
	.form-toggle-label {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-ink);
		cursor: pointer;
	}

	.form-error {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		color: var(--color-error);
		margin: 0;
	}

	.btn-submit {
		height: var(--touch-min);
		background: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: background-color var(--transition-fast);
		margin-top: var(--space-2);
	}
	.btn-submit:hover:not(:disabled) { background: var(--color-clay-dark); }
	.btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }
	.btn-submit:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 3px; }

	/* ── Delete zone ── */
	.drawer-delete-zone {
		padding: var(--space-4) var(--space-6) var(--space-6);
		border-top: 1px solid var(--color-divider);
		display: flex;
		justify-content: center;
	}
	.btn-delete-link {
		background: none;
		border: none;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-error);
		text-decoration: underline;
		text-underline-offset: 2px;
		padding: var(--space-2);
	}
	.btn-delete-link:hover { opacity: 0.8; }
	.btn-delete-link:focus-visible { outline: 2px solid var(--color-error); outline-offset: 2px; border-radius: 2px; }

	/* ── Undo toast ── */
	.undo-toast {
		position: fixed;
		bottom: var(--space-6);
		left: 50%;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		gap: var(--space-4);
		background: var(--color-ink);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		padding: var(--space-3) var(--space-5);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		z-index: 200;
		white-space: nowrap;
	}
	.btn-undo {
		background: none;
		border: 1px solid rgba(255, 255, 255, 0.4);
		border-radius: var(--radius-sm);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		padding: 2px var(--space-3);
		cursor: pointer;
		transition: background-color var(--transition-fast);
	}
	.btn-undo:hover { background: rgba(255, 255, 255, 0.15); }
	.btn-undo:focus-visible { outline: 2px solid white; outline-offset: 2px; }
</style>
