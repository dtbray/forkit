<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const { tonight, alternates } = $derived(data);

	function formatTime(minutes: number | null | undefined): string | null {
		if (minutes == null) return null;
		return `${minutes} min`;
	}
</script>

<svelte:head>
	<title>forkit</title>
	<meta name="description" content="Your family recipe vault" />
</svelte:head>

<main>
	{#if tonight}
		<!-- ── Tonight ── -->
		<section class="tonight-section" aria-labelledby="tonight-heading">
			<h1 class="tonight-heading" id="tonight-heading">Tonight</h1>

			<article class="tonight-card" aria-label="Tonight's recipe: {tonight.title}">
				<a href="/recipes/{tonight.id}" class="tonight-card__image-link" tabindex="-1" aria-hidden="true">
					<div class="tonight-card__image-wrap">
						<img
							src={tonight.hero_image_path ?? ''}
							alt={tonight.title}
							class="tonight-card__image"
							loading="eager"
							onerror={(e) => {
								const img = e.currentTarget as HTMLImageElement;
								img.style.display = 'none';
								img.parentElement?.classList.add('tonight-card__image-wrap--fallback');
							}}
						/>
					</div>
				</a>

				<div class="tonight-card__body">
					<div class="tonight-card__meta">
						{#if tonight.cuisine}
							<span class="meta-chip">{tonight.cuisine}</span>
						{/if}
						{#if formatTime(tonight.total_time_minutes)}
							<span class="meta-chip">{formatTime(tonight.total_time_minutes)}</span>
						{/if}
						{#if tonight.cook_count > 0}
							<span class="meta-chip meta-chip--accent">Cooked {tonight.cook_count}×</span>
						{/if}
					</div>

					<h2 class="tonight-card__title">
						<a href="/recipes/{tonight.id}" class="tonight-card__title-link">{tonight.title}</a>
					</h2>

					<div class="tonight-card__actions">
						<a href="/cook/{tonight.id}" class="btn-primary">Start Cooking</a>
						<a href="/recipes/{tonight.id}" class="btn-ghost">View Recipe</a>
					</div>
				</div>
			</article>
		</section>

		<!-- ── Alternates ── -->
		{#if alternates.length > 0}
			<section class="alternates-section" aria-labelledby="alternates-heading">
				<h2 class="alternates-heading" id="alternates-heading">Or try instead</h2>
				<ul class="alternates-list" role="list">
					{#each alternates as recipe (recipe.id)}
						<li>
							<a href="/recipes/{recipe.id}" class="alternate-card" aria-label="{recipe.title}{recipe.cuisine ? ` · ${recipe.cuisine}` : ''}">
								<div class="alternate-card__image-wrap">
									<img
										src={recipe.hero_image_path ?? ''}
										alt={recipe.title}
										class="alternate-card__image"
										loading="lazy"
										onerror={(e) => {
											const img = e.currentTarget as HTMLImageElement;
											img.style.display = 'none';
											img.parentElement?.classList.add('alternate-card__image-wrap--fallback');
										}}
									/>
								</div>
								<div class="alternate-card__body">
									<p class="alternate-card__title">{recipe.title}</p>
									<div class="alternate-card__meta">
										{#if recipe.cuisine}
											<span class="meta-chip meta-chip--sm">{recipe.cuisine}</span>
										{/if}
										{#if formatTime(recipe.total_time_minutes)}
											<span class="meta-chip meta-chip--sm">{formatTime(recipe.total_time_minutes)}</span>
										{/if}
										{#if recipe.cook_count > 0}
											<span class="meta-chip meta-chip--sm meta-chip--accent">Cooked {recipe.cook_count}×</span>
										{/if}
									</div>
								</div>
							</a>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<!-- ── Browse Library ── -->
		<nav class="browse-nav" aria-label="Recipe library">
			<a href="/recipes" class="browse-link">Browse Library</a>
		</nav>
	{:else}
		<!-- ── Empty State ── -->
		<section class="empty-state" aria-labelledby="empty-heading">
			<p class="empty-state__icon" aria-hidden="true">🍴</p>
			<h1 class="empty-state__heading" id="empty-heading">Your recipe vault is empty.</h1>
			<p class="empty-state__body">
				Every great meal starts somewhere — add your first recipe and let forkit remember it for you.
			</p>
			<a href="/ingest" class="btn-primary">Add your first recipe</a>
		</section>
	{/if}
</main>

<style>
	main {
		flex: 1;
		display: flex;
		flex-direction: column;
		background-color: var(--color-bone);
	}

	/* ── Shared meta chips ── */
	.meta-chip {
		display: inline-flex;
		align-items: center;
		padding: 2px var(--space-2);
		border-radius: var(--radius-sm);
		background-color: var(--color-bone-dim);
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size);
		font-weight: var(--text-label-sm-weight);
		letter-spacing: var(--text-label-sm-tracking);
		color: var(--color-text-secondary);
		white-space: nowrap;
	}

	.meta-chip--accent {
		background-color: var(--color-clay-dim);
		color: var(--color-clay-dark);
	}

	.meta-chip--sm {
		font-size: 0.75rem;
	}

	/* ── Shared buttons ── */
	.btn-primary {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: var(--touch-min);
		padding: 0 var(--space-6);
		border-radius: var(--radius-md);
		background-color: var(--color-clay);
		color: var(--color-surface);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		text-decoration: none;
		transition: background-color var(--transition-fast);
	}

	.btn-primary:hover {
		background-color: var(--color-clay-dark);
	}

	.btn-ghost {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: var(--touch-min);
		padding: 0 var(--space-4);
		border-radius: var(--radius-md);
		background-color: transparent;
		color: var(--color-clay);
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		text-decoration: none;
		border: 1px solid var(--color-clay);
		transition: background-color var(--transition-fast), color var(--transition-fast);
	}

	.btn-ghost:hover {
		background-color: var(--color-clay-dim);
	}

	/* ── Tonight section ── */
	.tonight-section {
		padding: var(--space-8) var(--space-6) var(--space-6);
	}

	.tonight-heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-clay);
		margin: 0 0 var(--space-6);
	}

	/* Tonight card */
	.tonight-card {
		background-color: var(--color-bg-surface);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-md);
		overflow: hidden;
	}

	.tonight-card__image-link {
		display: block;
	}

	.tonight-card__image-wrap {
		width: 100%;
		aspect-ratio: 16 / 9;
		background-color: var(--color-bone-dim);
		overflow: hidden;
	}

	.tonight-card__image-wrap--fallback {
		background-color: var(--color-bone-dim);
	}

	.tonight-card__image {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.tonight-card__body {
		padding: var(--space-6);
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.tonight-card__meta {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.tonight-card__title {
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size);
		font-weight: var(--text-heading-md-weight);
		line-height: var(--text-heading-md-lh);
		letter-spacing: var(--text-heading-md-tracking);
		color: var(--color-text-primary);
		margin: 0;
	}

	.tonight-card__title-link {
		color: inherit;
		text-decoration: none;
	}

	.tonight-card__title-link:hover {
		text-decoration: underline;
		text-underline-offset: 3px;
	}

	.tonight-card__actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		align-items: center;
	}

	/* ── Alternates section ── */
	.alternates-section {
		padding: 0 var(--space-6) var(--space-6);
	}

	.alternates-heading {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		letter-spacing: var(--text-label-md-tracking);
		color: var(--color-text-tertiary);
		text-transform: uppercase;
		margin: 0 0 var(--space-4);
	}

	.alternates-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* Alternate card — compact horizontal layout */
	.alternate-card {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		background-color: var(--color-bg-surface);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		overflow: hidden;
		text-decoration: none;
		color: inherit;
		transition: box-shadow var(--transition-fast);
		min-height: var(--touch-min);
	}

	.alternate-card:hover {
		box-shadow: var(--shadow-md);
	}

	.alternate-card__image-wrap {
		flex-shrink: 0;
		width: 72px;
		height: 72px;
		background-color: var(--color-bone-dim);
		overflow: hidden;
	}

	.alternate-card__image-wrap--fallback {
		background-color: var(--color-bone-dim);
	}

	.alternate-card__image {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.alternate-card__body {
		flex: 1;
		padding: var(--space-3) var(--space-4) var(--space-3) 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		min-width: 0;
	}

	.alternate-card__title {
		font-family: var(--font-display);
		font-size: var(--text-body-sm-size);
		font-weight: 600;
		line-height: var(--text-body-sm-lh);
		color: var(--color-text-primary);
		margin: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.alternate-card__meta {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}

	/* ── Browse nav ── */
	.browse-nav {
		padding: 0 var(--space-6) var(--space-10);
		display: flex;
		justify-content: center;
	}

	.browse-link {
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size);
		font-weight: var(--text-ui-sm-weight);
		color: var(--color-text-secondary);
		text-decoration: underline;
		text-underline-offset: 3px;
	}

	.browse-link:hover {
		color: var(--color-clay);
	}

	/* ── Empty state ── */
	.empty-state {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: var(--space-12) var(--space-8);
		gap: var(--space-4);
	}

	.empty-state__icon {
		font-size: 3rem;
		margin: 0;
		line-height: 1;
	}

	.empty-state__heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size);
		font-weight: var(--text-heading-lg-weight);
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-text-primary);
		margin: 0;
	}

	.empty-state__body {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: var(--text-body-md-weight);
		line-height: var(--text-body-md-lh);
		color: var(--color-text-secondary);
		margin: 0;
		max-width: 36ch;
	}

	/* ── Responsive ── */
	@media (min-width: 768px) {
		.tonight-section,
		.alternates-section,
		.browse-nav {
			max-width: 720px;
			margin-inline: auto;
			width: 100%;
		}

		.tonight-section {
			padding-top: var(--space-10);
		}

		.tonight-card__body {
			padding: var(--space-8);
		}

		.tonight-card__title {
			font-size: var(--text-heading-lg-size);
		}
	}
</style>
