<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	onMount(() => {
		const params = $page.url.searchParams;
		const url = params.get('url') || params.get('text') || '';
		if (url) {
			goto(`/ingest?prefill=${encodeURIComponent(url)}`);
		} else {
			goto('/ingest');
		}
	});
</script>

<p>Opening forkit…</p>
