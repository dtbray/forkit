<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { requestWakeLock, releaseWakeLock, isWakeLockActive } from '$lib/wake-lock';
	import { getSizeMap, getIngredientSizeMap, type TextSize } from '$lib/cook-view-size';
	import type { PageData } from './$types';

	// ── Props ─────────────────────────────────────────────────────────────────────
	let { data }: { data: PageData } = $props();

	// ── Parse steps once from load data ──────────────────────────────────────────
	const steps = (() => {
		try {
			const parsed = JSON.parse(data.instructions ?? '[]');
			return Array.isArray(parsed)
				? parsed
						.map((s: { text?: string } | string) => (typeof s === 'string' ? s : (s.text ?? '')))
						.filter(Boolean)
				: [];
		} catch {
			return [];
		}
	})();

	// ── State ────────────────────────────────────────────────────────────────────
	const STORAGE_KEY = 'forkit.cook.textSize';
	const SIZE_LABELS: Record<TextSize, string> = {
		S: 'Small',
		M: 'Medium',
		L: 'Large',
		XL: 'Extra large'
	};

	let textSize: TextSize = $state('M');
	let currentStep: number = $state(0); // 0-indexed
	let wakeLockActive: boolean = $state(false);
	let checkedIngredients: Set<string> = $state(new Set());
	let allCheckedCelebration: boolean = $state(false);
	let showSheet: boolean = $state(false);
	let showGestureHint: boolean = $state(false);
	let gestureHintVisible: boolean = $state(false);
	let portraitMode: boolean = $state(false);
	let ingredientPanelOpen: boolean = $state(false);

	// ── Confirmation sheet state ─────────────────────────────────────────────────
	let confirmationState: 'prompt' | 'success' | 'error' = $state('prompt');
	let newCookCount = $state<number | null>(null);

	// ── Derived ──────────────────────────────────────────────────────────────────
	const ingredients = $derived(data.ingredients ?? []);
	const stepCount = $derived(steps.length);
	const isFirstStep = $derived(currentStep === 0);
	const isLastStep = $derived(currentStep === stepCount - 1);
	const checkedCount = $derived(checkedIngredients.size);
	const allChecked = $derived(checkedCount === ingredients.length && ingredients.length > 0);
	const showPips = $derived(stepCount <= 12);

	const stepSizeMap = getSizeMap();
	const ingredientSizeMap = getIngredientSizeMap();

	// ── Wake Lock polling (reactive indicator) ───────────────────────────────────
	let wakePollInterval: ReturnType<typeof setInterval> | null = null;

	function updateWakeLockState() {
		wakeLockActive = isWakeLockActive();
	}

	// ── Lifecycle ────────────────────────────────────────────────────────────────
	onMount(() => {
		// Restore persisted text size
		const saved = localStorage.getItem(STORAGE_KEY) as TextSize | null;
		if (saved && saved in stepSizeMap) {
			textSize = saved;
		}
		applyTextSize(textSize);

		// Request wake lock
		requestWakeLock().then(() => {
			wakeLockActive = isWakeLockActive();
		});

		// Poll wake lock state (it can be released by the OS)
		wakePollInterval = setInterval(updateWakeLockState, 2000);

		// Gesture hint — show on first visit, hide after 3 seconds
		const hintSeen = sessionStorage.getItem('forkit.cook.hintSeen');
		if (!hintSeen) {
			showGestureHint = true;
			gestureHintVisible = true;
			setTimeout(
				() => {
					gestureHintVisible = false;
					setTimeout(() => {
						showGestureHint = false;
					}, 350);
					sessionStorage.setItem('forkit.cook.hintSeen', '1');
				},
				3000
			);
		}

		// Visibility change — release wake lock when hidden
		document.addEventListener('visibilitychange', handleVisibilityChange);

		// Keyboard navigation
		window.addEventListener('keydown', handleKeyDown);

		// Portrait detection
		const mq = window.matchMedia('(orientation: portrait), (max-width: 767px)');
		portraitMode = mq.matches;
		mq.addEventListener('change', (e) => {
			portraitMode = e.matches;
		});
	});

	onDestroy(() => {
		releaseWakeLock();
		if (wakePollInterval) clearInterval(wakePollInterval);
		document.removeEventListener('visibilitychange', handleVisibilityChange);
		window.removeEventListener('keydown', handleKeyDown);
	});

	// ── Handlers ─────────────────────────────────────────────────────────────────
	function handleVisibilityChange() {
		if (document.hidden) {
			releaseWakeLock().then(() => {
				wakeLockActive = false;
			});
		} else {
			requestWakeLock().then(() => {
				wakeLockActive = isWakeLockActive();
			});
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		// Don't intercept when focus is on a form element (e.g., ingredient label)
		const tag = (e.target as HTMLElement).tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

		switch (e.key) {
			case 'ArrowRight':
				advanceStep();
				break;
			case ' ':
				e.preventDefault();
				toggleWakeLock();
				break;
			case 'ArrowLeft':
				retreatStep();
				break;
			case 'Home':
				currentStep = 0;
				break;
			case 'End':
				currentStep = stepCount - 1;
				break;
			case 'Escape':
				openSheet();
				break;
		}
	}

	async function toggleWakeLock() {
		if (isWakeLockActive()) {
			await releaseWakeLock();
		} else {
			await requestWakeLock();
		}
		wakeLockActive = isWakeLockActive();
	}

	function advanceStep() {
		if (isLastStep) {
			openSheet();
		} else {
			currentStep += 1;
			dismissGestureHint();
		}
	}

	function retreatStep() {
		if (!isFirstStep) {
			currentStep -= 1;
		}
	}

	function dismissGestureHint() {
		if (showGestureHint) {
			gestureHintVisible = false;
			setTimeout(() => {
				showGestureHint = false;
			}, 350);
			sessionStorage.setItem('forkit.cook.hintSeen', '1');
		}
	}

	function openSheet() {
		showSheet = true;
	}

	function closeSheet() {
		showSheet = false;
		confirmationState = 'prompt';
		newCookCount = null;
	}

	async function markCooked() {
		try {
			const res = await fetch(`/api/recipes/${data.id}/cook`, { method: 'POST' });
			if (!res.ok) throw new Error('failed');
			const body = await res.json();
			newCookCount = body.cook_count;
			confirmationState = 'success';
		} catch {
			confirmationState = 'error';
		}
	}

	function toggleIngredient(id: string) {
		const next = new Set(checkedIngredients);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		checkedIngredients = next;

		// All-checked celebration
		if (next.size === ingredients.length && ingredients.length > 0) {
			allCheckedCelebration = true;
			setTimeout(() => {
				allCheckedCelebration = false;
			}, 1850); // 350ms in + 1150ms hold + 350ms out
		}
	}

	function applyTextSize(size: TextSize) {
		document.documentElement.style.setProperty('--cook-step-size', stepSizeMap[size]);
		document.documentElement.style.setProperty('--cook-ingredient-size', ingredientSizeMap[size]);
	}

	function setTextSize(size: TextSize) {
		textSize = size;
		applyTextSize(size);
		localStorage.setItem(STORAGE_KEY, size);
	}

	// Roving tabindex helpers for radiogroup
	function handleSizeKeyDown(e: KeyboardEvent, size: TextSize) {
		const sizes: TextSize[] = ['S', 'M', 'L', 'XL'];
		const idx = sizes.indexOf(size);
		if (e.key === 'ArrowRight' && idx < sizes.length - 1) {
			setTextSize(sizes[idx + 1]);
		} else if (e.key === 'ArrowLeft' && idx > 0) {
			setTextSize(sizes[idx - 1]);
		}
	}
</script>

<svelte:head>
	<title>{data.title ?? 'Cook'} — Cook — forkit</title>
	<!-- Override viewport for cook view only: disable pinch-zoom per Q17 decision.
	     Mandatory mitigation: in-app S/M/L/XL type-size control is present in header. -->
	<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
</svelte:head>

<main class="cook-view">
	<!-- ── Header ──────────────────────────────────────────────────────────────── -->
	<header class="cook-header" aria-label="Cook view controls">
		<!-- Back -->
		<a href="/recipes/{data.id}" class="header-back" aria-label="Back to recipe">
			<span class="back-chevron" aria-hidden="true">‹</span>
			<span class="back-label">Back</span>
		</a>

		<!-- Title (absolute center) -->
		<h1 class="header-title" title={data.title ?? ''}>{data.title ?? ''}</h1>

		<!-- Right zone: type-size, wake lock, done -->
		<div class="header-right">
			<!-- Type-size toggle -->
			<div
				class="size-toggle"
				role="radiogroup"
				aria-label="Step text size"
			>
				{#each (['S', 'M', 'L', 'XL'] as TextSize[]) as size}
					<button
						class="size-btn"
						class:size-btn--active={textSize === size}
						role="radio"
						aria-checked={textSize === size}
						aria-label={SIZE_LABELS[size]}
						data-size={size}
						tabindex={textSize === size ? 0 : -1}
						onclick={() => setTextSize(size)}
						onkeydown={(e) => handleSizeKeyDown(e, size)}
					>
						{size}
					</button>
				{/each}
			</div>

			<!-- Wake Lock indicator -->
			{#if wakeLockActive}
				<span
					class="wake-indicator"
					aria-label="Screen stay-on active"
					title="Screen stay-on active"
					role="img"
				></span>
			{/if}

			<!-- Done button -->
			<button class="done-btn" onclick={openSheet} aria-label="Done cooking">
				done
			</button>
		</div>
	</header>

	<!-- ── Portrait: ingredient pull-down chip ────────────────────────────────── -->
	{#if portraitMode}
		<div class="portrait-ingredient-chip">
			<button
				class="ingredient-chip-btn"
				aria-expanded={ingredientPanelOpen}
				aria-controls="portrait-ingredient-panel"
				onclick={() => (ingredientPanelOpen = !ingredientPanelOpen)}
			>
				<span>Ingredients · {checkedCount} of {ingredients.length} done</span>
				<span class="chip-chevron" class:chip-chevron--open={ingredientPanelOpen} aria-hidden="true">›</span>
			</button>

			{#if ingredientPanelOpen}
				<div
					id="portrait-ingredient-panel"
					class="portrait-ingredient-panel"
					aria-label="Ingredients"
				>
					<ul class="ingredient-list" aria-label="Ingredients">
						{#each ingredients as ing (ing.id)}
							<li class="ingredient-row" class:ingredient-row--checked={checkedIngredients.has(ing.id)}>
								<label class="ingredient-label">
									<input
										type="checkbox"
										class="ingredient-checkbox"
										checked={checkedIngredients.has(ing.id)}
										onchange={() => toggleIngredient(ing.id)}
										aria-label="{ing.qty} {ing.unit} {ing.item}"
									/>
									<span class="ingredient-text">
										<span class="ingredient-qty">{ing.qty}&nbsp;{ing.unit}</span>
										<span class="ingredient-name">{ing.item}</span>
										{#if ing.notes}
											<span class="ingredient-note">{ing.notes}</span>
										{/if}
									</span>
								</label>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		</div>
	{/if}

	<!-- ── Main split layout ──────────────────────────────────────────────────── -->
	<div class="cook-layout" class:cook-layout--portrait={portraitMode}>
		<!-- Left pane: ingredients -->
		{#if !portraitMode}
			<section class="ingredient-pane" aria-label="Ingredients">
				<div class="ingredient-pane-inner">
					<!-- Sticky section header -->
					<h2
						class="ingredient-section-header"
						class:ingredient-section-header--celebration={allCheckedCelebration}
					>
						Ingredients · serves {data.yield_text ?? ''}
					</h2>

					<!-- Ingredient list -->
					<ul class="ingredient-list" aria-label="Ingredients">
						{#each ingredients as ing (ing.id)}
							<li
								class="ingredient-row"
								class:ingredient-row--checked={checkedIngredients.has(ing.id)}
							>
								<label class="ingredient-label">
									<input
										type="checkbox"
										class="ingredient-checkbox"
										checked={checkedIngredients.has(ing.id)}
										onchange={() => toggleIngredient(ing.id)}
										aria-label="{ing.qty} {ing.unit} {ing.item}{ing.notes ? ', ' + ing.notes : ''}"
									/>
									<span class="ingredient-text">
										<span class="ingredient-qty">{ing.qty}&nbsp;{ing.unit}</span>
										<span class="ingredient-name">{ing.item}</span>
										{#if ing.notes}
											<span class="ingredient-note">{ing.notes}</span>
										{/if}
									</span>
								</label>
							</li>
						{/each}
					</ul>
				</div>

				<!-- Bottom-anchored scale toggle (P2 placeholder) -->
				<div class="scale-toggle-bar" aria-label="Serving scale (coming soon)">
					<div class="scale-toggle" role="group" aria-label="Recipe scale">
						{#each ['½', '1×', '2×'] as scale}
							<button
								class="scale-btn"
								class:scale-btn--active={scale === '1×'}
								aria-label="Scale {scale}"
								title="Recipe scaling coming soon"
								onclick={() => {/* P2 — coming soon */}}
							>
								{scale}
							</button>
						{/each}
					</div>
				</div>
			</section>
		{/if}

		<!-- Right pane: steps -->
		<section class="step-pane" aria-label="Recipe steps">
			<!-- Steps list (semantic ol, only active step shown) -->
			<ol class="step-list" aria-label="Recipe steps">
				{#each steps as step, idx}
					<li
						class="step-item"
						class:step-item--active={idx === currentStep}
						aria-current={idx === currentStep ? 'step' : undefined}
						hidden={idx !== currentStep}
					>
						<!-- Step number -->
						<span class="step-number" aria-hidden="true">{idx + 1}</span>

						<!-- Step body -->
						<p class="step-body">{step}</p>
					</li>
				{/each}
			</ol>

			<!-- Gesture hint (step 1, first visit only) -->
			{#if showGestureHint && currentStep === 0}
				<p
					class="gesture-hint"
					class:gesture-hint--visible={gestureHintVisible}
					aria-live="polite"
				>
					<em>Tap anywhere to go to the next step</em>
				</p>
			{/if}

			<!-- Tap-to-advance on step content area -->
			<button
				class="step-tap-zone"
				aria-label="Tap to advance to next step"
				onclick={advanceStep}
				tabindex="-1"
			></button>

			<!-- Step nav bar -->
			<nav class="step-nav" aria-label="Step navigation">
				<!-- Prev -->
				<button
					class="step-nav-btn step-nav-btn--prev"
					aria-label="Previous step"
					aria-disabled={isFirstStep}
					disabled={isFirstStep}
					onclick={retreatStep}
				>
					<span class="nav-chevron nav-chevron--prev" aria-hidden="true">‹</span>
					<span class="nav-label">prev</span>
				</button>

				<!-- Center: step indicator -->
				<div class="step-indicator" role="status" aria-live="polite" aria-atomic="true">
					<span class="step-indicator-text">Step {currentStep + 1} of {stepCount}</span>
					{#if showPips}
						<div class="step-pips" aria-hidden="true">
							{#each steps as _, idx}
								<span
									class="pip"
									class:pip--active={idx === currentStep}
								></span>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Next / Finish -->
				<button
					class="step-nav-btn step-nav-btn--next"
					aria-label={isLastStep ? 'Finish cooking' : 'Next step'}
					onclick={advanceStep}
				>
					<span class="nav-chevron nav-chevron--next" aria-hidden="true">›</span>
					<span class="nav-label">{isLastStep ? 'finish' : 'next'}</span>
				</button>
			</nav>
		</section>
	</div>

	<!-- ── "We made this?" sheet ──────────────────────────────────────────────── -->
	{#if showSheet}
		<div class="sheet-backdrop" onclick={closeSheet} aria-hidden="true"></div>
		<div class="we-made-this-sheet" role="dialog" aria-modal="true" aria-label="Did you make it?">
			{#if confirmationState === 'prompt'}
				<h2 class="sheet-heading">Did you make it?</h2>
				<p class="sheet-recipe-name">{data.title}</p>
				<div class="sheet-actions">
					<button class="sheet-btn sheet-btn--primary" onclick={markCooked}>We made it</button>
					<button class="sheet-btn sheet-btn--ghost" onclick={closeSheet}>Not this time</button>
				</div>
			{:else if confirmationState === 'success'}
				<h2 class="sheet-heading" aria-live="polite">Logged! Cook #{newCookCount}</h2>
				<p class="sheet-recipe-name">{data.title}</p>
				<div class="sheet-actions">
					<button class="sheet-btn sheet-btn--primary" onclick={() => goto('/recipes')}>Browse recipes</button>
					<button class="sheet-btn sheet-btn--ghost" onclick={() => goto(`/recipes/${data.id}`)}>Back to recipe</button>
				</div>
			{:else}
				<h2 class="sheet-heading">Couldn't save</h2>
				<p class="sheet-recipe-name">Want to try again?</p>
				<div class="sheet-actions">
					<button class="sheet-btn sheet-btn--primary" onclick={markCooked}>Retry</button>
					<button class="sheet-btn sheet-btn--ghost" onclick={closeSheet}>Dismiss</button>
				</div>
			{/if}
		</div>
	{/if}
</main>

<style>
	/* ── Cook view root ──────────────────────────────────────────────────────── */
	.cook-view {
		display: flex;
		flex-direction: column;
		height: 100dvh;
		overflow: hidden;
		background-color: var(--color-bone);
	}

	/* ── Header ──────────────────────────────────────────────────────────────── */
	.cook-header {
		position: sticky;
		top: 0;
		z-index: var(--z-header);
		height: 56px;
		display: flex;
		align-items: center;
		background-color: var(--color-bone);
		border-bottom: 1px solid var(--color-divider);
		padding: 0 var(--space-4);
		gap: var(--space-4);
	}

	.header-back {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--space-2);
		color: var(--color-clay);
		text-decoration: none;
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		line-height: var(--text-ui-md-lh);
		flex-shrink: 0;
	}

	.back-chevron {
		font-size: 1.25rem;
		line-height: 1;
	}

	.back-label {
		font-size: var(--text-ui-md-size);
	}

	.header-title {
		position: absolute;
		left: 50%;
		transform: translateX(-50%);
		margin: 0;
		font-family: var(--font-display);
		font-size: var(--text-heading-md-size); /* 20px */
		font-weight: 600;
		line-height: 1.2;
		letter-spacing: -0.01em;
		color: var(--color-ink);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 400px;
		pointer-events: none;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		margin-left: auto;
	}

	/* ── Type-size toggle ─────────────────────────────────────────────────────── */
	.size-toggle {
		display: flex;
		align-items: center;
		border: 2px solid var(--color-divider);
		border-radius: var(--radius-full);
		background-color: var(--color-bone-dim);
		overflow: hidden;
		height: 32px;
	}

	.size-btn {
		width: 40px;
		height: 44px; /* Touch target taller than visual */
		display: flex;
		align-items: center;
		justify-content: center;
		background: none;
		border: none;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-ui-sm-size); /* 14px */
		font-weight: var(--text-ui-sm-weight);
		color: var(--color-ink-secondary);
		transition: background-color var(--transition-fast), color var(--transition-fast);
		padding: 0;
	}

	.size-btn--active {
		background-color: var(--color-clay);
		color: var(--color-surface);
	}

	.size-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 2px;
	}

	/* ── Wake Lock indicator ─────────────────────────────────────────────────── */
	.wake-indicator {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: var(--radius-full);
		background-color: var(--color-clay);
		flex-shrink: 0;
	}

	/* ── Done button ─────────────────────────────────────────────────────────── */
	.done-btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--space-3);
		background: none;
		border: none;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		color: var(--color-clay);
	}

	.done-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		border-radius: var(--radius-sm);
	}

	/* ── Cook layout (38/62 split) ───────────────────────────────────────────── */
	.cook-layout {
		display: grid;
		grid-template-columns: 38fr 62fr;
		flex: 1;
		overflow: hidden;
		min-height: 0;
	}

	.cook-layout--portrait {
		grid-template-columns: 1fr;
	}

	/* ── Ingredient pane (38%) ───────────────────────────────────────────────── */
	.ingredient-pane {
		background-color: var(--color-bone-dim);
		border-right: 1px solid var(--color-divider);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-height: 0;
	}

	.ingredient-pane-inner {
		flex: 1;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: 0 var(--space-5) 0 var(--space-6);
		min-height: 0;
	}

	/* ── Ingredient section header ───────────────────────────────────────────── */
	.ingredient-section-header {
		position: sticky;
		top: 0;
		z-index: var(--z-sticky);
		background-color: var(--color-bone-dim);
		margin: 0;
		padding: var(--space-5) 0 var(--space-5) 0;
		font-family: var(--font-body);
		font-size: var(--text-label-md-size); /* 15px */
		font-weight: var(--text-label-md-weight);
		line-height: var(--text-label-md-lh);
		letter-spacing: var(--text-label-md-tracking);
		font-variant: small-caps;
		color: var(--color-ink-secondary);
		transition: color var(--transition-slow);
	}

	.ingredient-section-header--celebration {
		color: var(--color-success);
	}

	/* ── Ingredient list ─────────────────────────────────────────────────────── */
	.ingredient-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.ingredient-row {
		border-bottom: 1px solid var(--color-divider);
	}

	.ingredient-label {
		display: flex;
		align-items: flex-start;
		gap: var(--space-3); /* 12px */
		padding: var(--space-5) 0; /* 20px top/bottom */
		min-height: 56px;
		cursor: pointer;
		width: 100%;
	}

	/* Custom checkbox: 20pt circle */
	.ingredient-checkbox {
		appearance: none;
		-webkit-appearance: none;
		width: 20px;
		height: 20px;
		min-width: 20px;
		border-radius: var(--radius-full);
		border: 2px solid var(--color-divider);
		background-color: transparent;
		cursor: pointer;
		margin-top: 2px; /* Align with first line of text */
		transition: background-color var(--transition-fast), border-color var(--transition-fast);
		position: relative;
		flex-shrink: 0;
	}

	.ingredient-checkbox:checked {
		background-color: var(--color-clay);
		border-color: var(--color-clay);
	}

	.ingredient-checkbox:checked::after {
		content: '';
		display: block;
		position: absolute;
		left: 4px;
		top: 1px;
		width: 5px;
		height: 10px;
		border: 2px solid var(--color-surface);
		border-top: none;
		border-left: none;
		transform: rotate(45deg);
	}

	.ingredient-checkbox:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	.ingredient-text {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
		min-width: 0;
	}

	.ingredient-qty {
		font-family: var(--font-body);
		font-size: var(--cook-ingredient-size, var(--text-body-lg-size)); /* 22px default */
		font-weight: 600;
		line-height: var(--text-body-lg-lh);
		color: var(--color-ink);
		font-variant-numeric: tabular-nums;
		display: inline;
	}

	.ingredient-name {
		font-family: var(--font-body);
		font-size: var(--cook-ingredient-size, var(--text-body-lg-size)); /* 22px default */
		font-weight: 400;
		line-height: var(--text-body-lg-lh);
		color: var(--color-ink);
		display: inline;
		margin-left: 0.25em;
	}

	.ingredient-note {
		display: block;
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size); /* 16px */
		font-weight: 400;
		line-height: var(--text-body-sm-lh);
		color: var(--color-ink-tertiary);
		font-style: italic;
		margin-top: 2px;
	}

	/* Checked state: strikethrough */
	.ingredient-row--checked .ingredient-qty,
	.ingredient-row--checked .ingredient-name {
		text-decoration: line-through;
		color: var(--color-ink-tertiary);
	}

	/* ── Scale toggle bar (bottom of ingredient pane) ────────────────────────── */
	.scale-toggle-bar {
		flex-shrink: 0;
		height: 48px;
		background-color: var(--color-bone-dim);
		border-top: 1px solid var(--color-divider);
		display: flex;
		align-items: center;
		justify-content: center;
		padding-bottom: env(safe-area-inset-bottom, 0px);
	}

	.scale-toggle {
		display: flex;
		align-items: center;
		border: 2px solid var(--color-divider);
		border-radius: var(--radius-full);
		background-color: var(--color-bone);
		overflow: hidden;
	}

	.scale-btn {
		min-height: 44px;
		min-width: 44px;
		padding: 0 var(--space-4);
		background: none;
		border: none;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		color: var(--color-ink-secondary);
	}

	.scale-btn--active {
		background-color: var(--color-clay);
		color: var(--color-surface);
	}

	/* ── Step pane (62%) ─────────────────────────────────────────────────────── */
	.step-pane {
		background-color: var(--color-bone);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-height: 0;
		position: relative;
	}

	/* ── Step list ───────────────────────────────────────────────────────────── */
	.step-list {
		list-style: none;
		margin: 0;
		padding: 0;
		flex: 1;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: var(--space-6) var(--space-12); /* 24px top, 48px horizontal */
		padding-bottom: calc(var(--space-20) + var(--space-6)); /* clear step nav */
		min-height: 0;
	}

	.step-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-4); /* 16px */
	}

	/* Step number */
	.step-number {
		font-family: var(--font-display);
		font-size: 48px; /* Always 48px regardless of toggle */
		font-weight: 700;
		line-height: 1.0;
		letter-spacing: -0.01em;
		color: var(--color-clay);
		display: block;
	}

	/* Step body */
	.step-body {
		font-family: var(--font-body);
		font-size: var(--cook-step-size, 2rem); /* Controlled by toggle, default 32px */
		font-weight: 400;
		line-height: 1.45;
		color: var(--color-ink);
		max-width: 70ch;
		margin: 0;
	}

	/* ── Gesture hint ────────────────────────────────────────────────────────── */
	.gesture-hint {
		text-align: center;
		font-family: var(--font-body);
		font-size: var(--text-body-sm-size); /* 16px */
		font-weight: 400;
		line-height: 1.5;
		color: var(--color-ink-tertiary);
		margin: 0;
		padding: var(--space-4) var(--space-12);
		opacity: 0;
		transition: opacity var(--transition-slow);
		pointer-events: none;
	}

	.gesture-hint--visible {
		opacity: 1;
	}

	/* ── Tap zone (invisible, covers step content) ───────────────────────────── */
	.step-tap-zone {
		position: absolute;
		inset: 56px 0 80px 0; /* Below header, above nav */
		background: transparent;
		border: none;
		cursor: pointer;
		z-index: 1;
		/* Tab index -1: not keyboard focusable (nav buttons handle keyboard) */
	}

	/* ── Step nav bar ────────────────────────────────────────────────────────── */
	.step-nav {
		position: sticky;
		bottom: 0;
		z-index: var(--z-step-nav);
		height: 80px;
		background-color: var(--color-bone);
		border-top: 1px solid var(--color-divider);
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 var(--space-8);
		padding-bottom: env(safe-area-inset-bottom, 0px);
		flex-shrink: 0;
	}

	.step-nav-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-1);
		min-width: 60px;
		min-height: 60px;
		padding: var(--space-2) var(--space-4);
		background: none;
		border: none;
		cursor: pointer;
		color: var(--color-clay);
		transition: color var(--transition-fast), opacity var(--transition-fast);
		border-radius: var(--radius-md);
	}

	.step-nav-btn:disabled {
		color: var(--color-ink-tertiary);
		opacity: 0.4;
		cursor: not-allowed;
	}

	.step-nav-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	.step-nav-btn:not(:disabled):active {
		color: var(--color-clay-dark);
	}

	.nav-chevron {
		font-size: 24px;
		line-height: 1;
		font-weight: 500;
	}

	.nav-label {
		font-family: var(--font-body);
		font-size: var(--text-label-sm-size); /* 13px */
		font-weight: var(--text-label-sm-weight);
		line-height: var(--text-label-sm-lh);
		color: var(--color-ink-tertiary);
	}

	/* ── Step indicator ──────────────────────────────────────────────────────── */
	.step-indicator {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
	}

	.step-indicator-text {
		font-family: var(--font-body);
		font-size: var(--text-label-md-size); /* 15px */
		font-weight: var(--text-label-md-weight);
		line-height: var(--text-label-md-lh);
		letter-spacing: var(--text-label-md-tracking);
		color: var(--color-ink-secondary);
	}

	.step-pips {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.pip {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: var(--radius-full);
		background-color: transparent;
		border: 2px solid var(--color-divider);
		transition: background-color var(--transition-fast), border-color var(--transition-fast);
	}

	.pip--active {
		background-color: var(--color-clay);
		border-color: var(--color-clay);
	}

	/* ── "We made this?" sheet ───────────────────────────────────────────────── */
	.sheet-backdrop {
		position: fixed;
		inset: 0;
		background-color: var(--color-overlay);
		z-index: var(--z-sheet); /* same layer as sheet — sheet comes after in DOM */
	}

	.we-made-this-sheet {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: calc(var(--z-sheet) + 1); /* always above its own backdrop */
		background-color: var(--color-surface);
		border-radius: var(--radius-lg) var(--radius-lg) 0 0;
		box-shadow: var(--shadow-lg);
		padding: var(--space-8) var(--space-8) calc(var(--space-8) + env(safe-area-inset-bottom, 0px));
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		min-height: 240px;
	}

	.sheet-heading {
		font-family: var(--font-display);
		font-size: var(--text-heading-lg-size); /* 24px */
		font-weight: 600;
		line-height: var(--text-heading-lg-lh);
		letter-spacing: var(--text-heading-lg-tracking);
		color: var(--color-ink);
		margin: 0;
	}

	.sheet-recipe-name {
		font-family: var(--font-body);
		font-size: var(--text-body-md-size);
		font-weight: var(--text-body-md-weight);
		color: var(--color-ink-secondary);
		margin: 0;
	}

	.sheet-actions {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		margin-top: var(--space-4);
	}

	.sheet-btn {
		min-height: 56px;
		padding: 0 var(--space-8);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-ui-md-size);
		font-weight: var(--text-ui-md-weight);
		transition: background-color var(--transition-fast);
	}

	.sheet-btn--primary {
		background-color: var(--color-clay);
		color: var(--color-surface);
		flex: 1;
	}

	.sheet-btn--primary:hover {
		background-color: var(--color-clay-dark);
	}

	.sheet-btn--ghost {
		background: none;
		color: var(--color-ink-secondary);
	}

	.sheet-btn:focus-visible {
		outline: 2px solid var(--color-focus-ring);
		outline-offset: 3px;
		box-shadow: var(--shadow-focus);
	}

	/* ── Portrait mode: ingredient chip ─────────────────────────────────────── */
	.portrait-ingredient-chip {
		background-color: var(--color-bone-dim);
		border-bottom: 1px solid var(--color-divider);
	}

	.ingredient-chip-btn {
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-6);
		background: none;
		border: none;
		cursor: pointer;
		font-family: var(--font-body);
		font-size: var(--text-label-md-size);
		font-weight: var(--text-label-md-weight);
		color: var(--color-ink-secondary);
		text-align: left;
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.chip-chevron {
		font-size: 1.25rem;
		line-height: 1;
		transition: transform var(--transition-fast, 150ms ease);
		display: inline-block;
		transform: rotate(90deg);
	}

	.chip-chevron--open {
		transform: rotate(-90deg);
	}

	@media (prefers-reduced-motion: reduce) {
		.chip-chevron {
			transition: none;
		}
	}

	.portrait-ingredient-panel {
		padding: 0 var(--space-6) var(--space-4);
		background-color: var(--color-bone-dim);
		max-height: 50vh;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
	}

	/* ── Reduced motion override ─────────────────────────────────────────────── */
	@media (prefers-reduced-motion: reduce) {
		* {
			animation-duration: 0.01ms !important;
			transition-duration: 0.01ms !important;
		}
	}
</style>
