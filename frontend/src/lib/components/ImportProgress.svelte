<script lang="ts">
	import { onMount } from 'svelte';
	import { invalidate } from '$app/navigation';

	type Source = { source_url: string; name: string; stage: string; total: number; counts: Record<string, number>; error: string | null; images?: Record<string, number> };
	let sources = $state<Source[]>([]);
	let connection = $state<'live' | 'reconnecting'>('live');
	let refreshNow = () => {};
	const saved = (s: Source) => (s.counts.imported ?? 0) + (s.counts.existing ?? 0) + (s.counts.changed ?? 0);
	const processed = (s: Source) => saved(s) + (s.counts.skipped ?? 0) + (s.counts.failed ?? 0);

	onMount(() => {
		let active = true;
		let busy = false;
		let snapshot = '';
		let timer: ReturnType<typeof setTimeout>;
		let controller: AbortController;
		async function refresh() {
			clearTimeout(timer);
			if (!active || busy || document.hidden) return;
			busy = true;
			controller = new AbortController();
			try {
				const response = await fetch('/api/imports', { cache: 'no-store', signal: controller.signal });
				if (!response.ok) throw new Error('Progress unavailable');
				const next: Source[] = (await response.json()).sources;
				if (!active) return;
				connection = 'live';
				sources = next;
				const nextSnapshot = JSON.stringify(next.map(({ source_url, total, counts, stage, images }) => ({ source_url, total, counts, stage, images })));
				if (nextSnapshot !== snapshot) {
					snapshot = nextSnapshot;
					await invalidate('forkit:library');
				}
			} catch {
				if (active) connection = 'reconnecting';
			} finally {
				busy = false;
				if (active) timer = setTimeout(refresh, connection === 'live' ? 3000 : 10000);
			}
		}
		refreshNow = () => { void refresh(); };
		void refresh();
		document.addEventListener('visibilitychange', refreshNow);
		window.addEventListener('online', refreshNow);
		return () => {
			active = false;
			clearTimeout(timer);
			controller?.abort();
			document.removeEventListener('visibilitychange', refreshNow);
			window.removeEventListener('online', refreshNow);
		};
	});
</script>

{#if sources.length}
	<aside aria-label="Recipe imports" class="imports">
		<div class="imports-header">
			<span class="connection" aria-live="polite"><span class:offline={connection !== 'live'} class="dot"></span>{connection === 'live' ? 'Live updates' : 'Reconnecting · showing last update'}</span>
			<button onclick={refreshNow}>Refresh now</button>
		</div>
		{#each sources as source (source.source_url)}
			<div class="source">
				<p><a href={source.source_url} target="_blank" rel="noreferrer">{source.name}</a>:
					{saved(source)} of {source.total} recipes saved
					{#if source.stage === 'paused'} · Import paused
					{:else if source.stage === 'complete'} · Import finished
					{:else if source.stage === 'backoff'} · Waiting before retrying
					{:else if source.stage === 'discovering'} · Finding recipes
					{:else if source.stage === 'images'} · Adding photos
					{:else if source.stage === 'importing'} · Importing
					{:else if source.counts.pending} · Queued{/if}
					{#if source.images} · {(source.images.saved ?? 0) + (source.images.existing ?? 0)} photos{/if}
					{#if source.counts.skipped} · {source.counts.skipped} pages without complete recipes{/if}
					{#if source.counts.failed} · {source.counts.failed} failed{/if}
					{#if source.counts.changed} · {source.counts.changed} source updates available for review{/if}
				</p>
				<progress aria-label={`${source.name} import progress`} max={Math.max(1, source.total)} value={processed(source)}></progress>
			</div>
		{/each}
	</aside>
{/if}

<style>
	.imports { padding: 1rem; margin-bottom: 1.5rem; border: 1px solid var(--color-divider); background: var(--color-surface); border-radius: var(--radius-md); }
	.imports-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; margin-bottom: .75rem; }
	.connection { display: inline-flex; align-items: center; gap: .5rem; color: var(--color-ink-secondary); font-size: .875rem; }
	.dot { width: .5rem; height: .5rem; border-radius: 50%; background: var(--color-success); flex-shrink: 0; }
	.dot.offline { background: var(--color-warning); }
	.source + .source { margin-top: 1rem; }
	p { margin: 0 0 .5rem; line-height: 1.5; }
	progress { display: block; width: 100%; height: .5rem; accent-color: var(--color-clay); }
	a { color: var(--color-clay-dark); text-underline-offset: .2em; }
	button { min-height: 44px; padding: .5rem .75rem; border: 1px solid var(--color-divider); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink); font: inherit; cursor: pointer; }
</style>
