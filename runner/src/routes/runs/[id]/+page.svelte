<script lang="ts">
	import { onMount } from 'svelte';
	import { slide } from 'svelte/transition';
	import { invalidateAll } from '$app/navigation';
	import { PersistedState } from 'runed';
	import { ChevronDown, ChevronRight } from '@lucide/svelte';
	import DurationBar from '$lib/components/DurationBar.svelte';
	import EventDetail from '$lib/components/EventDetail.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import TokenUsage from '$lib/components/TokenUsage.svelte';
	import type { Attachment } from 'svelte/attachments';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let selected = $state(0);
	let index = $derived(Math.min(selected, data.events.length - 1));
	let current = $derived(data.events[index]);
	// How long this step took: the gap to the next event, or to the run's end for the last
	// step once it has finished. Null while the final step is still open (run streaming).
	// For a goal event this is its "self" time (the gap before its first sub-event).
	let currentDurationMs = $derived.by(() => {
		const next = data.events[index + 1];
		const endTs = next?.ts ?? data.run.finishedAt;
		return endTs != null ? endTs - current.ts : null;
	});
	// For a goal event (step / precondition / teardown), the total time of the whole group:
	// from the goal up to the next goal (or the run's end). Null for non-goal events and for
	// the final, still-open group while streaming.
	let currentTotalMs = $derived.by(() => {
		if (current.phase !== 'goal') return null;
		let boundaryTs: number | null = data.run.finishedAt;
		for (let i = index + 1; i < data.events.length; i++) {
			if (data.events[i].phase === 'goal') {
				boundaryTs = data.events[i].ts;
				break;
			}
		}
		return boundaryTs != null ? boundaryTs - current.ts : null;
	});

	// Global, persisted user preference: should runs follow the newest step by default?
	// Only the explicit toggle below writes this, so it survives reloads and applies
	// across runs without being corrupted by per-run navigation.
	const autofocus = new PersistedState('panto:autofocus', true);
	// Whether THIS view is currently following the tail. Seeded from the preference;
	// navigation pauses it without touching the global default.
	let following = $state(autofocus.current);

	// Collapsible console dock at the bottom of the view, expanded by default (persisted).
	const open = new PersistedState('panto:console-open', true);

	// Keep the console box pinned to the bottom as new output streams in.
	function autoscroll(getText: () => string): Attachment<HTMLElement> {
		return (node) => {
			$effect(() => {
				getText(); // track the console text so this re-runs as it grows
				node.scrollTop = node.scrollHeight;
			});
		};
	}

	function step(delta: number) {
		const n = data.events.length;
		if (!n) return;
		// Manually stepping away from the tail pauses following for this view only.
		following = false;
		selected = Math.max(0, Math.min(n - 1, selected + delta));
	}

	function select(i: number) {
		following = i >= data.events.length - 1;
		selected = i;
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.target instanceof HTMLInputElement) return;
		if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'j') {
			e.preventDefault();
			step(1);
		} else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'k') {
			e.preventDefault();
			step(-1);
		}
	}

	// While the run is live, keep pulling new events and follow the tail.
	let live = $derived(data.run.status === 'running');
	onMount(() => {
		// Apply autofocus immediately so the newest step is shown on load, not only
		// after the first poll.
		if (following) selected = data.events.length - 1;
		const t = setInterval(async () => {
			if (!live) return;
			await invalidateAll();
			if (following) selected = data.events.length - 1;
		}, 1500);
		return () => clearInterval(t);
	});
</script>

<svelte:window {onkeydown} />

<div class="flex min-h-0 flex-1 flex-col">
<div class="mb-4 flex shrink-0 flex-wrap items-center gap-3">
	<StatusBadge status={data.run.status} />
	<h1 class="text-lg font-semibold">{data.run.title}</h1>
	<span class="font-mono text-xs text-subtle">{data.run.testId}</span>
	<div class="ml-auto flex items-center gap-4 text-sm text-muted">
		<span>{data.events.length} steps</span>
		<TokenUsage usage={data.run.usage} variant="header" />
		{#if live}
			<button
				type="button"
				class="rounded border px-2 py-0.5 text-xs transition-colors {following
					? 'border-info/50 bg-info/10 text-info'
					: 'border-border-strong text-muted hover:bg-elevated'}"
				aria-pressed={following}
				onclick={() => {
					following = !following;
					autofocus.current = following; // persist the explicit choice as the new global default
					if (following) selected = data.events.length - 1;
				}}
				title="Follow the newest step as the run streams in"
			>
				Autofocus {following ? 'on' : 'off'}
			</button>
		{/if}
	</div>
</div>

{#if data.events.length === 0}
	<div class="rounded-lg border border-border bg-surface/40 p-8 text-center text-muted">
		No events recorded for this run.
	</div>
{:else}
	<div class="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
		<aside class="flex min-h-0 flex-col rounded-lg border border-border bg-surface">
			<div class="flex shrink-0 items-center border-b border-border px-3 py-2">
				<span class="text-xs uppercase tracking-wide text-subtle">Timeline</span>
			</div>
			<div class="min-h-0 flex-1 overflow-auto py-1">
				<Timeline events={data.events} {selected} onselect={select} autofocus={following} />
			</div>
		</aside>

		<section class="min-h-0 overflow-auto rounded-lg border border-border bg-surface p-4">
			{#if current}
				<EventDetail event={current} durationMs={currentDurationMs} totalDurationMs={currentTotalMs} />
			{/if}
		</section>
	</div>

	<div class="mt-3 shrink-0">
		<DurationBar
			events={data.events}
			{selected}
			onselect={select}
			endTs={data.run.finishedAt}
		/>
	</div>
{/if}

{#if data.console}
	<div class="mt-3 shrink-0">
		<button
			type="button"
			onclick={() => (open.current = !open.current)}
			aria-expanded={open.current}
			class="flex w-full items-center gap-1.5 py-2 text-left text-subtle hover:text-muted"
		>
			{#if open.current}<ChevronDown size={14} class="text-subtle" />{:else}<ChevronRight size={14} class="text-subtle" />{/if}
			<span class="text-xs uppercase tracking-wide text-subtle">Console</span>
		</button>
		{#if open.current}
			<div transition:slide={{ duration: 150 }} class="overflow-hidden">
				<pre
					{@attach autoscroll(() => data.console)}
					class="max-h-[40vh] overflow-auto whitespace-pre-wrap wrap-break-word rounded border border-border bg-base p-3 font-mono text-xs text-muted">{data.console}</pre>
			</div>
		{/if}
	</div>
{/if}
</div>
