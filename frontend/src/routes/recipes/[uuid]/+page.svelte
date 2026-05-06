<script lang="ts">
	import { goto } from '$app/navigation';

	interface Ingredient {
		amount: string | null;
		unit: string | null;
		name: string;
		notes: string | null;
	}

	interface Instruction {
		step_number: number;
		text: string;
	}

	interface Recipe {
		id: string;
		title: string;
		source_url: string | null;
		hero_image_path: string | null;
		cuisine: string | null;
		yield_servings: number | null;
		prep_time_minutes: number | null;
		cook_time_minutes: number | null;
		total_time_minutes: number | null;
		favorite: boolean;
		cook_count: number;
		last_cooked: string | null;
		rating: number | null;
		user_notes: string | null;
		parser_source: string | null;
		ingredients: Ingredient[];
		tags: { name: string }[];
		instructions: Instruction[];
	}

	interface PageData extends Recipe {}

	let { data }: { data: PageData } = $props();

	// ── Local state (UI-layer; backend stubs noted inline) ────────────────────────
	let isFavorite: boolean = $state(data.favorite);
	let userNotes: string = $state(data.user_notes ?? '');
	let notesChanged: boolean = $state(false);
	let notesSaving: boolean = $state(false);
	let deleteDialogOpen: boolean = $state(false);

	// ── Formatting helpers ────────────────────────────────────────────────────────
	function formatTime(minutes: number | null): string {
		if (!minutes) return '—';
		if (minutes < 60) return `${minutes} min`;
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		return m > 0 ? `${h} hr ${m} min` : `${h} hr`;
	}

	function formatIngredientAmount(ingredient: Ingredient): string {
		const parts: string[] = [];
		if (ingredient.amount) parts.push(ingredient.amount);
		if (ingredient.unit) parts.push(ingredient.unit);
		return parts.join(' ');
	}

	function starLabel(star: number): string {
		const labels = ['', 'Poor', 'Fair', 'Good', 'Great', 'Excellent'];
		return labels[star] ?? '';
	}

	// ── Favorite toggle ──────────────────────────────────────────────────────────
	async function toggleFavorite() {
		isFavorite = !isFavorite;
		try {
			await fetch(`/api/recipes/${data.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ favorite: isFavorite })
			});
		} catch {
			// Stub: silently tolerate network failure; local state reflects intent
		}
	}

	// ── User notes ───────────────────────────────────────────────────────────────
	function handleNotesChange() {
		notesChanged = userNotes !== (data.user_notes ?? '');
	}

	async function saveNotes() {
		if (!notesChanged || notesSaving) return;
		notesSaving = true;
		try {
			await fetch(`/api/recipes/${data.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ user_notes: userNotes })
			});
			notesChanged = false;
		} catch {
			// Stub: silently tolerate network failure
		} finally {
			notesSaving = false;
		}
	}

	// ── Delete ───────────────────────────────────────────────────────────────────
	function requestDelete() {
		const confirmed = window.confirm(
			`Permanently delete "${data.title}"?\n\nThis recipe will be removed from your vault and cannot be recovered.`
		);
		if (confirmed) {
			performDelete();
		}
	}

	async function performDelete() {
		try {
			const res = await fetch(`/api/recipes/${data.id}`, { method: 'DELETE' });
			if (res.ok) {
				goto('/recipes');
			}
		} catch {
			// Network error — stay on page; user can retry
		}
	}
</script>

<svelte:head>
	<title>{data.title} — forkit</title>
	<meta name="description" content="{data.cuisine ? data.cuisine + ' · ' : ''}{data.title}" />
</svelte:head>

<main class="detail-page">
	<!-- ── Back nav ──────────────────────────────────────────────────────────────── -->
	<a href="/recipes" class="back-link" aria-label="Back to all recipes">
		<span class="back-chevron" aria-hidden="true">‹</span>
		<span>Recipes</span>
	</a>

	<!-- ── Hero image ────────────────────────────────────────────────────────────── -->
	<div class="hero-wrap">
		{#if data.hero_image_path}
			<img
				src={data.hero_image_path}
				alt="{data.title} hero image"
				class="hero-img"
				loading="eager"
				decoding="async"
			/>
		{:else}
			<div class="hero-placeholder" aria-hidden="true">
				<svg viewBox="0 0 24 24" class="hero-placeholder-icon" aria-hidden="true" focusable="false">
					<path d="M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z" />
				</svg>
			</div>
		{/if}
	</div>

	<!-- ── Detail content ────────────────────────────────────────────────────────── -->
	<article class="detail-content" aria-label="Recipe details">

		<!-- ── Title + actions row ──────────────────────────────────────────────── -->
		<div class="title-row">
			<h1 class="recipe-title">{data.title}</h1>

			<button
				class="favorite-btn"
				class:favorite-btn--active={isFavorite}
				onclick={toggleFavorite}
				aria-pressed={isFavorite}
				aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
				title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
			>
				<span aria-hidden="true">{isFavorite ? '★' : '☆'}</span>
			</button>
		</div>

		<!-- ── Meta row ─────────────────────────────────────────────────────────── -->
		<div class="meta-row" aria-label="Recipe details">
			{#if data.cuisine}
				<span class="meta-item meta-cuisine">{data.cuisine}</span>
			{/if}
			{#if data.yield_servings}
				<span class="meta-item" aria-label="{data.yield_servings} servings">
					{data.yield_servings} servings
				</span>
			{/if}
		</div>

		<!-- ── Time breakdown ───────────────────────────────────────────────────── -->
		<div class="time-grid" aria-label="Timing">
			<div class="time-cell">
				<span class="time-label">Prep</span>
				<span class="time-value">{formatTime(data.prep_time_minutes)}</span>
			</div>
			<div class="time-cell">
				<span class="time-label">Cook</span>
				<span class="time-value">{formatTime(data.cook_time_minutes)}</span>
			</div>
			<div class="time-cell time-cell--total">
				<span class="time-label">Total</span>
				<span class="time-value">{formatTime(data.total_time_minutes)}</span>
			</div>
		</div>

		<!-- ── Rating (read-only) ───────────────────────────────────────────────── -->
		{#if data.rating !== null && data.rating > 0}
			<div class="rating-row" aria-label="Rating: {data.rating} out of 5, {starLabel(data.rating)}">
				<span class="rating-label">Rating</span>
				<div class="stars" aria-hidden="true">
					{#each [1, 2, 3, 4, 5] as star}
						<span class="star" class:star--filled={star <= (data.rating ?? 0)}>★</span>
					{/each}
				</div>
				<span class="sr-only">{data.rating} out of 5 — {starLabel(data.rating)}</span>
			</div>
		{/if}

		<!-- ── Tags ─────────────────────────────────────────────────────────────── -->
		{#if data.tags.length > 0}
			<div class="tags-row" aria-label="Tags">
				{#each data.tags as tag}
					<span class="tag">{tag.name}</span>
				{/each}
			</div>
		{/if}

		<!-- ── Ingredients ──────────────────────────────────────────────────────── -->
		<section class="recipe-section" aria-labelledby="ingredients-heading">
			<h2 class="section-heading" id="ingredients-heading">Ingredients</h2>
			<ul class="ingredient-list" aria-label="Ingredients">
				{#each data.ingredients as ingredient}
					<li class="ingredient-row">
						{#if ingredient.amount || ingredient.unit}
							<span class="ingredient-amount">
								{formatIngredientAmount(ingredient)}
							</span>
						{/if}
						<span class="ingredient-name">{ingredient.name}</span>
						{#if ingredient.notes}
							<span class="ingredient-notes">{ingredient.notes}</span>
						{/if}
					</li>
				{/each}
			</ul>
		</section>

		<!-- ── Instructions ─────────────────────────────────────────────────────── -->
		<section class="recipe-section" aria-labelledby="instructions-heading">
			<h2 class="section-heading" id="instructions-heading">Instructions</h2>
			<ol class="instruction-list" aria-label="Instructions">
				{#each data.instructions as instruction}
					<li class="instruction-step" value={instruction.step_number}>
						<span class="step-number" aria-hidden="true">{instruction.step_number}</span>
						<p class="step-text">{instruction.text}</p>
					</li>
				{/each}
			</ol>
		</section>

		<!-- ── User notes ───────────────────────────────────────────────────────── -->
		<section class="recipe-section" aria-labelledby="notes-heading">
			<h2 class="section-heading" id="notes-heading">
				My Notes
				{#if notesSaving}
					<span class="notes-saving-indicator" aria-live="polite">saving…</span>
				{/if}
			</h2>
			<textarea
				class="notes-textarea"
				bind:value={userNotes}
				oninput={handleNotesChange}
				onblur={saveNotes}
				placeholder="Add your personal notes, substitutions, or tweaks here…"
				aria-label="Personal notes about this recipe"
				rows="4"
			></textarea>
		</section>

		<!-- ── Source attribution ───────────────────────────────────────────────── -->
		{#if data.source_url}
			<p class="source-link-wrap">
				<a
					href={data.source_url}
					class="source-link"
					target="_blank"
					rel="noopener noreferrer"
					aria-label="View original recipe (opens in new tab)"
				>
					View original recipe ↗
				</a>
			</p>
		{/if}

		<!-- ── CTA: Start Cooking ────────────────────────────────────────────────── -->
		<div class="cta-row">
			<a href="/cook/{data.id}" class="btn-cook">
				Start Cooking
			</a>
		</div>

		<!-- ── Danger zone: Delete ──────────────────────────────────────────────── -->
		<div class="danger-zone" aria-label="Danger zone">
			<button class="btn-delete" onclick={requestDelete} aria-label="Delete this recipe permanently">
				Delete recipe
			</button>
		</div>
	</article>
</main>

<style>
	/* ── Page root ───────────────────────────────────────────────────────────── */
	.detail-page {
		flex: 1;
		background-color: var(--color-bone);
		padding-bottom: var(--space-16);
	}

	/* ── Screen reader only ─────────────────────────────────────────────────── */
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

	/* ── Back link ───────────────────────────────────────────────────────────── */
	.back-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		min-height: var(--touch-min);
		padding: var(--space-3) var(--space-5);
		color: var(--color-clay);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		line-height: var(--text-ui-md-lh);
		position: sticky;
		top: 0;
		z-index: var(--z-header);
		background-color: var(--color-bone);
		border-bottom: 1px solid var(--color-divider);
		width: 100%;
	}

	.back-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
	}

	.back-chevron {
		font-size: 1.25rem;
		line-height: 1;
	}

	/* ── Hero ────────────────────────────────────────────────────────────────── */
	.hero-wrap {
		width: 100%;
		aspect-ratio: 16 / 7;
		overflow: hidden;
		background-color: var(--color-bone-dim);
	}

	@media (min-width: 768px) {
		.hero-wrap {
			aspect-ratio: 21 / 7;
		}
	}

	.hero-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.hero-placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		background-color: var(--color-bone-dim);
	}

	.hero-placeholder-icon {
		width: 64px;
		height: 64px;
		fill: var(--color-ink-tertiary);
		opacity: 0.3;
	}

	/* ── Detail content ──────────────────────────────────────────────────────── */
	.detail-content {
		max-width: 720px;
		margin-inline: auto;
		padding: var(--space-8) var(--space-6);
	}

	/* ── Title row ───────────────────────────────────────────────────────────── */
	.title-row {
		display: flex;
		align-items: flex-start;
		gap: var(--space-4);
		margin-bottom: var(--space-4);
	}

	.recipe-title {
		flex: 1;
		font-family: var(--font-display);
		font-size: var(--text-display-md-size);
		font-weight: var(--text-display-md-weight);
		line-height: var(--text-display-md-lh);
		letter-spacing: var(--text-display-md-tracking);
		color: var(--color-ink);
		margin: 0;
	}

	@media (max-width: 767px) {
		.recipe-title {
			font-size: var(--text-heading-lg-size);
		}
	}

	/* ── Favorite button ─────────────────────────────────────────────────────── */
	.favorite-btn {
		flex-shrink: 0;
		width: var(--touch-min);
		height: var(--touch-min);
		display: flex;
		align-items: center;
		justify-content: center;
		background: none;
		border: none;
		cursor: pointer;
		font-size: 1.75rem;
		line-height: 1;
		color: var(--color-ink-tertiary);
		transition: color var(--transition-fast), transform var(--transition-fast);
		border-radius: var(--radius-full);
		margin-top: -4px;
	}

	.favorite-btn--active {
		color: var(--color-clay);
	}

	.favorite-btn:hover {
		color: var(--color-clay);
		transform: scale(1.1);
	}

	.favorite-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	@media (prefers-reduced-motion: reduce) {
		.favorite-btn:hover {
			transform: none;
		}
	}

	/* ── Meta row ────────────────────────────────────────────────────────────── */
	.meta-row {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		flex-wrap: wrap;
		margin-bottom: var(--space-6);
	}

	.meta-item {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		letter-spacing: var(--text-label-md-tracking);
		color: var(--color-ink-secondary);
	}

	.meta-cuisine {
		font-variant: small-caps;
		color: var(--color-clay);
	}

	/* ── Time grid ───────────────────────────────────────────────────────────── */
	.time-grid {
		display: flex;
		gap: var(--space-1);
		margin-bottom: var(--space-6);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-md);
		overflow: hidden;
		background-color: var(--color-surface);
	}

	.time-cell {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: var(--space-4) var(--space-2);
		gap: var(--space-1);
		border-right: 1px solid var(--color-divider);
	}

	.time-cell:last-child {
		border-right: none;
	}

	.time-cell--total {
		background-color: var(--color-bone-dim);
	}

	.time-label {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-tertiary);
		text-transform: uppercase;
	}

	.time-value {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: 600;
		color: var(--color-ink);
		font-variant-numeric: tabular-nums;
	}

	/* ── Rating ──────────────────────────────────────────────────────────────── */
	.rating-row {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		margin-bottom: var(--space-4);
	}

	.rating-label {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-tertiary);
		text-transform: uppercase;
	}

	.stars {
		display: flex;
		gap: 2px;
	}

	.star {
		font-size: 1.25rem;
		line-height: 1;
		color: var(--color-ink-tertiary);
		opacity: 0.3;
	}

	.star--filled {
		color: var(--color-clay);
		opacity: 1;
	}

	/* ── Tags ────────────────────────────────────────────────────────────────── */
	.tags-row {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
		margin-bottom: var(--space-6);
	}

	.tag {
		display: inline-block;
		padding: 2px var(--space-3);
		background-color: var(--color-bone-dim);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-ink-secondary);
	}

	/* ── Recipe sections ─────────────────────────────────────────────────────── */
	.recipe-section {
		margin-top: var(--space-10);
	}

	.section-heading {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		line-height: var(--text-label-md-lh);
		letter-spacing: var(--text-label-md-tracking);
		color: var(--color-ink-secondary);
		text-transform: uppercase;
		font-variant: small-caps;
		margin: 0 0 var(--space-5);
		padding-bottom: var(--space-3);
		border-bottom: 1px solid var(--color-divider);
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.notes-saving-indicator {
		font-size: var(--text-label-sm-size);
		font-variant: normal;
		text-transform: none;
		letter-spacing: 0;
		color: var(--color-ink-tertiary);
		font-weight: 400;
	}

	/* ── Ingredients ─────────────────────────────────────────────────────────── */
	.ingredient-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.ingredient-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		padding: var(--space-4) 0;
		border-bottom: 1px solid var(--color-divider);
		flex-wrap: wrap;
	}

	.ingredient-row:last-child {
		border-bottom: none;
	}

	.ingredient-amount {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: 600;
		color: var(--color-ink);
		flex-shrink: 0;
		min-width: 4rem;
		font-variant-numeric: tabular-nums;
	}

	.ingredient-name {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: 400;
		color: var(--color-ink);
		flex: 1;
	}

	.ingredient-notes {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		font-weight: 400;
		color: var(--color-ink-tertiary);
		font-style: italic;
		flex-basis: 100%;
		padding-left: calc(4rem + var(--space-3));
	}

	/* ── Instructions ────────────────────────────────────────────────────────── */
	.instruction-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-8);
	}

	.instruction-step {
		display: grid;
		grid-template-columns: 2.5rem 1fr;
		gap: var(--space-4);
		align-items: start;
	}

	.step-number {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: 700;
		line-height: 1;
		color: var(--color-clay);
		text-align: right;
		padding-top: 0.1em;
	}

	.step-text {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: 400;
		line-height: var(--text-body-md-lh);
		color: var(--color-ink);
		margin: 0;
	}

	/* ── Notes textarea ──────────────────────────────────────────────────────── */
	.notes-textarea {
		width: 100%;
		padding: var(--space-4);
		border: 1px solid var(--color-divider);
		border-radius: var(--radius-md);
		background-color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: 400;
		line-height: var(--text-body-md-lh);
		color: var(--color-ink);
		resize: vertical;
		min-height: 6rem;
		transition: border-color var(--transition-fast);
	}

	.notes-textarea::placeholder {
		color: var(--color-ink-tertiary);
	}

	.notes-textarea:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 0;
		border-color: var(--color-clay);
		box-shadow: var(--shadow-focus);
	}

	/* ── Source link ─────────────────────────────────────────────────────────── */
	.source-link-wrap {
		margin-top: var(--space-6);
	}

	.source-link {
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size);
		color: var(--color-clay);
		text-decoration: underline;
		text-underline-offset: 3px;
	}

	.source-link:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		border-radius: var(--radius-sm);
	}

	/* ── CTA row ─────────────────────────────────────────────────────────────── */
	.cta-row {
		margin-top: var(--space-10);
	}

	.btn-cook {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		min-height: 56px;
		background-color: var(--color-clay);
		color: var(--color-surface);
		border-radius: var(--radius-md);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: 600;
		line-height: var(--text-ui-md-lh);
		transition: background-color var(--transition-fast);
	}

	.btn-cook:hover {
		background-color: var(--color-clay-dark);
	}

	.btn-cook:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	@media (min-width: 768px) {
		.btn-cook {
			width: auto;
			padding: 0 var(--space-12);
		}
	}

	/* ── Danger zone ─────────────────────────────────────────────────────────── */
	.danger-zone {
		margin-top: var(--space-16);
		padding-top: var(--space-8);
		border-top: 1px solid var(--color-divider);
	}

	.btn-delete {
		min-height: var(--touch-min);
		padding: 0 var(--space-5);
		background: none;
		border: 1px solid var(--color-error);
		border-radius: var(--radius-md);
		color: var(--color-error);
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		transition: background-color var(--transition-fast), color var(--transition-fast);
	}

	.btn-delete:hover {
		background-color: var(--color-error);
		color: var(--color-surface);
	}

	.btn-delete:focus-visible {
		outline: 2px solid var(--color-error);
		outline-offset: 3px;
	}
</style>
