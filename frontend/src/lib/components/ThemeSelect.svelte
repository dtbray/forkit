<script lang="ts">
	import { onMount } from 'svelte';
	type Theme = 'system' | 'light' | 'dark';
	let theme = $state<Theme>('system');
	function update() {
		document.documentElement.dataset.theme = theme;
		try { localStorage.setItem('forkit.theme', theme); } catch { /* Private browsing may deny storage. */ }
	}
	onMount(() => {
		const initial = document.documentElement.dataset.theme;
		if (initial === 'light' || initial === 'dark') theme = initial;
		function sync(event: StorageEvent) {
			if (event.key !== 'forkit.theme' && event.key !== null) return;
			theme = event.newValue === 'light' || event.newValue === 'dark' ? event.newValue : 'system';
			document.documentElement.dataset.theme = theme;
		}
		window.addEventListener('storage', sync);
		return () => window.removeEventListener('storage', sync);
	});
</script>

<label class="theme-control">
	<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
		{#if theme === 'dark'}
			<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
		{:else if theme === 'light'}
			<circle cx="12" cy="12" r="4" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2" />
		{:else}
			<rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" />
		{/if}
	</svg>
	<select aria-label="Color theme" bind:value={theme} onchange={update}>
		<option value="system">System</option>
		<option value="light">Light</option>
		<option value="dark">Dark</option>
	</select>
</label>

<style>
	.theme-control { display: inline-flex; align-items: center; gap: .25rem; color: var(--color-ink-secondary); }
	select { min-height: 44px; max-width: 100px; padding: .4rem; border: 1px solid var(--color-divider); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-ink); font: inherit; font-size: .875rem; cursor: pointer; }
	@media (max-width: 480px) { svg { display: none; } }
</style>
