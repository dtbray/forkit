<script lang="ts">
	import { onMount } from 'svelte';
	import { preparePantryPhoto } from '$lib/pantry-photo';

	type Ingredient = { name: string; quantity: string | null; unit: string | null; notes: string | null };
	type Stored = Ingredient & { id: number };
	type Draft = Ingredient & { key: number; selected: boolean };
	type Match = { id: string; title: string; matched: string[]; missing: string[] };
	let text = $state('');
	let source = $state<'text' | 'photo'>('text');
	let draft = $state<Draft[]>([]);
	let pantry = $state<Stored[]>([]);
	let recipes = $state<Match[]>([]);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let message = $state('');
	let photoEnabled = $state(false);
	let connected = $state(false);
	let model = $state('');
	let models = $state<{ slug: string; display_name: string }[]>([]);
	let showSetup = $state(false);
	const chosen = $derived(draft.filter(item => item.selected));

	async function request(url: string, init?: RequestInit) {
		const response = await fetch(url, { cache: 'no-store', ...init });
		if (!response.ok) {
			let detail = 'Could not complete this request. Please try again.';
			try { const body = await response.json(); if (typeof body.detail === 'string') detail = body.detail; } catch { /* generic error */ }
			throw new Error(detail);
		}
		return response.status === 204 ? null : response.json();
	}

	async function refresh() {
		const [stock, matches] = await Promise.all([request('/api/pantry'), request('/api/pantry/recipes')]);
		pantry = stock.items;
		recipes = matches.recipes;
	}

	async function connectionStatus() {
		const status = await request('/api/pantry/capabilities');
		photoEnabled = status.photo_enabled;
		connected = status.chatgpt_connected;
		model = status.model || '';
	}

	onMount(() => {
		Promise.all([refresh(), connectionStatus()])
			.catch(e => error = e.message).finally(() => loading = false);
	});

	function candidates(items: Ingredient[], origin: 'text' | 'photo') {
		source = origin;
		draft = items.map((item, key) => ({ ...item, key, selected: true }));
		if (!items.length) message = 'No ingredients found. Try a clearer photo or type a list.';
	}

	async function previewText() {
		busy = true; error = ''; message = '';
		try {
			const data = await request('/api/pantry/preview/text', { method: 'POST',
				headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
			candidates(data.items, 'text');
		} catch (e) { error = e instanceof Error ? e.message : 'Could not review ingredients.'; }
		finally { busy = false; }
	}

	async function previewPhoto(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		busy = true; error = ''; message = '';
		try {
			const photo = await preparePantryPhoto(file);
			const data = await request('/api/pantry/preview/photo', { method: 'POST',
				headers: { 'Content-Type': photo.type }, body: photo });
			candidates(data.items, 'photo');
		} catch (e) { error = e instanceof Error ? e.message : 'Could not recognize this photo.'; }
		finally { busy = false; input.value = ''; }
	}

	async function save() {
		busy = true; error = ''; message = '';
		try {
			const result = await request('/api/pantry/items', { method: 'POST',
				headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source,
					items: chosen.map(({ name, quantity, unit, notes }) => ({ name, quantity: quantity || null, unit: unit || null, notes: notes || null })) }) });
			// Clear only after commit succeeds; failed saves preserve every edit.
			draft = []; text = '';
			message = `Added ${result.added} ingredients.${result.already_present ? ` ${result.already_present} already in your pantry; existing amounts kept.` : ''}`;
			await refresh();
		} catch (e) { error = e instanceof Error ? e.message : 'Could not save. Your edits are still here.'; }
		finally { busy = false; }
	}

	async function remove(item: Stored) {
		busy = true; error = '';
		try { await request(`/api/pantry/items/${item.id}`, { method: 'DELETE' }); await refresh(); }
		catch (e) { error = e instanceof Error ? e.message : 'Could not remove ingredient.'; }
		finally { busy = false; }
	}

    async function checkConnection() {
        error = '';
        try { await connectionStatus(); }
        catch { error = 'Could not check ChatGPT connection. Try again.'; }
    }

    async function disconnect() {
        busy = true; error = '';
        try { await request('/api/pantry/chatgpt', { method: 'DELETE' }); models = []; await connectionStatus(); }
        catch { error = 'Could not disconnect ChatGPT. Try again.'; }
        finally { busy = false; }
    }

	async function chooseModel() {
		busy = true; error = '';
		try {
			if (!models.length) { models = (await request('/api/pantry/chatgpt/models')).models; return; }
			await request('/api/pantry/chatgpt/model', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }) });
			await connectionStatus(); message = 'ChatGPT is ready for photos.';
		} catch (e) { error = e instanceof Error ? e.message : 'Could not select model.'; }
		finally { busy = false; }
	}
</script>

<svelte:head><title>Pantry · Forkit</title><meta name="description" content="Add kitchen ingredients by photo, typing or keyboard dictation, then find recipes from your library." /></svelte:head>

<main>
	<header><p class="eyebrow">YOUR KITCHEN, TONIGHT</p><h1>What’s on hand?</h1><p>Add what you have. Find a little inspiration in your recipe library.</p></header>
	{#if error}<div role="alert" class="notice error">{error}</div>{/if}
	{#if message}<div role="status" class="notice">{message}</div>{/if}
	<div class="columns">
		<section class="card" aria-labelledby="add-heading">
			<h2 id="add-heading">Add ingredients</h2>
			{#if !draft.length}
				<label for="ingredients">Type or dictate your ingredients</label>
				<p id="dictation-tip" class="hint">Tap the field, then your keyboard’s microphone. Say “next item” between ingredients, or separate them with commas or new lines.</p>
				<textarea id="ingredients" bind:value={text} rows="6" maxlength="12000" disabled={busy} inputmode="text" spellcheck="true" aria-describedby="dictation-tip" placeholder={'2 eggs\n1 bag spinach\n400 g canned tomatoes'}></textarea>
				<button class="primary" onclick={previewText} disabled={busy || !text.trim()}>Review ingredients</button>
				<div class="photo-section"><span class="divider">or add a photo</span>
					{#if photoEnabled}
                        <p class="hint">ChatGPT connected · {model} · <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noreferrer">Usage &amp; access</a></p>
                        <button onclick={disconnect} disabled={busy}>Disconnect ChatGPT</button>
						<p class="hint">Photos are sent to ChatGPT for recognition. Forkit does not save the photo. Review everything before adding it.</p>
						<div class="actions">
							<label class="file-button" class:disabled={busy}>Take a photo<input aria-label="Take a pantry photo" type="file" accept="image/*" capture="environment" onchange={previewPhoto} disabled={busy} /></label>
							<label class="file-button" class:disabled={busy}>Choose photo<input aria-label="Choose a pantry photo" type="file" accept="image/*" onchange={previewPhoto} disabled={busy} /></label>
						</div>
					{:else if connected}
						<p class="hint">Choose a model from your ChatGPT account that supports photos.</p>
						{#if models.length}<label for="photo-model">ChatGPT model</label><select id="photo-model" bind:value={model} disabled={busy}><option value="" disabled>Choose a model</option>{#each models as option}<option value={option.slug}>{option.display_name}</option>{/each}</select>{/if}
						<button onclick={chooseModel} disabled={busy || (models.length > 0 && !model)}>{models.length ? 'Use this model' : 'Choose ChatGPT model'}</button>
					{:else}
						<p class="hint">Connect your ChatGPT account once to recognize ingredients in photos.</p>
						<button onclick={() => showSetup = !showSetup}>Connect ChatGPT</button>
						{#if showSetup}<div class="notice"><p>On a computer, use Forkit’s connection helper to Continue with ChatGPT, then securely install the connection on your lab server. This is a one-time household setup.</p><p>After connecting, <button onclick={checkConnection}>Check connection</button>.</p></div>{/if}
					{/if}
				</div>
			{:else}
				<p class="hint">Keep what’s right, edit names and amounts, and uncheck anything you don’t have. Blank amounts mean unknown.</p>
				<form onsubmit={(event) => { event.preventDefault(); save(); }}>
					{#each draft as item, index (item.key)}
						<fieldset disabled={busy} class:unselected={!item.selected}>
							<legend>Ingredient {index + 1}</legend>
							<label class="keep"><input type="checkbox" bind:checked={item.selected} /> Include ingredient {index + 1}</label>
							<label for={`name-${item.key}`}>Name</label><input id={`name-${item.key}`} bind:value={item.name} required={item.selected} maxlength="200" />
							<div class="amount"><div><label for={`quantity-${item.key}`}>Amount</label><input id={`quantity-${item.key}`} bind:value={item.quantity} maxlength="80" placeholder="Unknown" /></div><div><label for={`unit-${item.key}`}>Unit</label><input id={`unit-${item.key}`} bind:value={item.unit} maxlength="80" placeholder="Optional" /></div></div>
							<label for={`notes-${item.key}`}>Notes</label><input id={`notes-${item.key}`} bind:value={item.notes} maxlength="500" placeholder="Optional" />
						</fieldset>
					{/each}
					<div class="actions"><button class="primary" type="submit" disabled={busy || !chosen.length}>Add {chosen.length} to pantry</button><button type="button" onclick={() => draft = []} disabled={busy}>Discard review</button></div>
				</form>
			{/if}
			{#if busy}<p role="status">Working…</p>{/if}
		</section>
		<section class="card" aria-labelledby="pantry-heading">
			<h2 id="pantry-heading">On hand <span class="count">{pantry.length}</span></h2>
			{#if loading}<p>Loading your pantry…</p>{:else if !pantry.length}<p class="hint">Your pantry is ready for its first ingredients. Only reviewed ingredients appear here.</p>{:else}
				<ul class="stock">{#each pantry as item (item.id)}<li><div><strong>{item.name}</strong><span class="hint">{[item.quantity, item.unit].filter(Boolean).join(' ') || 'Amount unknown'}</span>{#if item.notes}<span class="hint">{item.notes}</span>{/if}</div><button class="remove" aria-label={`Remove ${item.name} from pantry`} onclick={() => remove(item)} disabled={busy}>Remove</button></li>{/each}</ul>
			{/if}
		</section>
	</div>
	<section class="matches" aria-labelledby="matches-heading"><h2 id="matches-heading">From your pantry to your plate</h2><p class="hint">Matches use ingredient names, not quantities. Check amounts and any substitutions before cooking. No staples are assumed.</p>
		{#if !recipes.length}<p class="empty">Add ingredients to find matching recipes from your library.</p>{:else}<div class="recipe-grid">{#each recipes as recipe (recipe.id)}<article class="card"><p class="eyebrow">{recipe.missing.length ? `${recipe.missing.length} ingredients missing` : 'All ingredient names matched'}</p><h3><a href={`/recipes/${recipe.id}`}>{recipe.title}</a></h3><p class="hint">On hand: {recipe.matched.join(', ')}</p>{#if recipe.missing.length}<p>Missing: {recipe.missing.join(', ')}</p>{/if}</article>{/each}</div>{/if}
	</section>
</main>

<style>
	main { max-width: 1120px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
	header { margin-bottom: 2rem; } h1 { font: 600 clamp(2rem, 5vw, 3.5rem)/1.1 var(--font-display); margin: .5rem 0; } h2 { font: 600 1.5rem var(--font-display); margin: 0 0 1rem; } h3 { font: 600 1.3rem var(--font-display); margin: .5rem 0; }
	.eyebrow { color: var(--color-text-accent); font-size: .75rem; font-weight: 700; letter-spacing: .1em; }
	.columns { display: grid; grid-template-columns: 1.1fr 1fr; gap: 1.5rem; align-items: start; }
	.card { border: 1px solid var(--color-border); background: var(--color-bg-surface); border-radius: 16px; padding: 1.5rem; }
	.hint, header > p:last-child { color: var(--color-text-secondary); font-size: .9rem; line-height: 1.6; }
	label { display: block; font-size: .85rem; font-weight: 600; margin: .65rem 0 .4rem; }
	textarea, input:not([type=checkbox]), select { box-sizing: border-box; width: 100%; border: 1px solid var(--color-border); border-radius: 8px; padding: .8rem; background: var(--color-bg-primary); color: var(--color-text-primary); font: inherit; font-size: 1rem; }
	textarea { resize: vertical; } button, .file-button { font: inherit; font-size: .9rem; border: 1px solid var(--color-border); background: var(--color-bg-primary); color: var(--color-text-primary); border-radius: 8px; min-height: 44px; padding: .65rem 1rem; cursor: pointer; box-sizing: border-box; }
	button.primary { background: var(--color-text-accent); color: var(--color-bg-surface); border-color: transparent; margin-top: 1rem; } button:disabled, .disabled { opacity: .5; cursor: wait; }
	:global(.file-button:focus-within), button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 3px; }
	.actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; margin-top: .75rem; } .actions .primary { margin-top: 0; }
	.photo-section { margin-top: 1.75rem; padding-top: 1rem; border-top: 1px solid var(--color-border); } .divider { font-size: .85rem; color: var(--color-text-tertiary); }
	.file-button { position: relative; display: inline-flex; align-items: center; margin: 0; font-weight: 400; overflow: hidden; } .file-button input { position: absolute; opacity: 0; inset: 0; width: 100%; cursor: pointer; }
	.notice { margin: 1rem 0; padding: .8rem 1rem; border-radius: 8px; background: var(--color-bg-secondary); line-height: 1.5; } .error { color: var(--color-error); border: 1px solid var(--color-error); }
	fieldset { margin: 1rem 0; padding: 1rem; border: 1px solid var(--color-border); border-radius: 10px; min-width: 0; } legend { font-size: .8rem; color: var(--color-text-secondary); } .keep { display: flex; align-items: center; gap: .6rem; } input[type=checkbox] { width: 20px; height: 20px; } .unselected { opacity: .6; }
	.amount { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; } .count { font: 400 .9rem var(--font-body); color: var(--color-text-secondary); }
	.stock { list-style: none; padding: 0; margin: 0; } .stock li { display: flex; justify-content: space-between; align-items: start; gap: 1rem; border-top: 1px solid var(--color-border); padding: 1rem 0; } .stock li:first-child { border-top: 0; } .stock strong, .stock span { display: block; overflow-wrap: anywhere; } .stock div { min-width: 0; } .remove { font-size: .8rem; padding: .5rem; flex-shrink: 0; }
	.matches { margin-top: 2.5rem; } .recipe-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 1rem; margin-top: 1.25rem; } a { color: var(--color-text-primary); } .empty { border: 1px dashed var(--color-border); padding: 2rem; border-radius: 12px; text-align: center; color: var(--color-text-secondary); }
	@media (max-width: 700px) { .columns { grid-template-columns: 1fr; } main { padding: 1.5rem 1rem 3rem; } .card { padding: 1.1rem; } }
</style>
