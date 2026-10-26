<script lang="ts">
	import { onMount } from 'svelte';
	import { invalidateAll } from '$app/navigation';

	type Source = { source_url: string; name: string; stage: string; total: number; counts: Record<string, number>; error: string | null };
	let sources = $state<Source[]>([]);
	onMount(() => {
		let active = true;
		async function refresh() {
			try {
				const response = await fetch('/api/imports');
				if (response.ok && active) sources = (await response.json()).sources;
			} catch { /* Library remains usable when progress is unavailable. */ }
		}
		void refresh();
		const timer = setInterval(refresh, 15000);
		return () => { active = false; clearInterval(timer); };
	});
</script>

{#if sources.length}
	<aside aria-label="Recipe imports" class="imports">
		{#each sources as source (source.source_url)}
			<p><a href={source.source_url} target="_blank" rel="noreferrer">{source.name}</a>:
				{(source.counts.imported ?? 0) + (source.counts.existing ?? 0) + (source.counts.changed ?? 0)} of {source.total} recipes saved
				{#if source.stage === 'paused'} · Import paused
				{:else if source.stage === 'complete'} · Import finished
				{:else if source.stage === 'backoff'} · Waiting before retrying
				{:else if source.stage === 'discovering'} · Finding recipes
				{:else if source.stage === 'importing'} · Importing{/if}
				{#if source.counts.skipped} · {source.counts.skipped} pages without complete recipes{/if}
				{#if source.counts.failed} · {source.counts.failed} failed{/if}
				{#if source.counts.changed} · {source.counts.changed} source updates available for review{/if}
			</p>
		{/each}
		<button onclick={() => invalidateAll()}>Refresh recipes</button>
	</aside>
{/if}

<style>
	.imports { padding: 1rem; margin-bottom: 1.5rem; border: 1px solid var(--color-clay); border-radius: var(--radius-md); }
	p { margin: 0 0 .75rem; line-height: 1.5; }
	a { color: var(--color-clay-dark); text-underline-offset: .2em; }
	button { min-height: 44px; padding: .5rem .75rem; border: 1px solid var(--color-clay); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink); font: inherit; cursor: pointer; }
</style>
