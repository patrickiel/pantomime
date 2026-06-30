<script lang="ts">
	import { untrack } from 'svelte';
	import { ChevronDown, ChevronRight, Image } from '@lucide/svelte';
	import { slide } from 'svelte/transition';
	import { SvelteSet } from 'svelte/reactivity';
	import PhaseBadge from './PhaseBadge.svelte';
	import type { Attachment } from 'svelte/attachments';
	import type { DebugEvent } from '$lib/types';
	import { phaseMeta } from '$lib/ui';

	let {
		events,
		selected,
		onselect,
		autofocus = false
	}: {
		events: DebugEvent[];
		selected: number;
		onselect: (i: number) => void;
		autofocus?: boolean;
	} = $props();

	type Row = { ev: DebugEvent; index: number };
	type Group = { header: Row | null; items: Row[] };

	// Group events under their preceding `goal` event, keeping each event's
	// original index into `events` so keyboard navigation stays intact.
	let groups = $derived.by(() => {
		const out: Group[] = [];
		let current: Group | null = null;
		for (const [index, ev] of events.entries()) {
			if (ev.phase === 'goal') {
				current = { header: { ev, index }, items: [] };
				out.push(current);
			} else {
				if (!current) {
					current = { header: null, items: [] };
					out.push(current);
				}
				current.items.push({ ev, index });
			}
		}
		return out;
	});

	// Collapsed groups, keyed by the header event's id. Default = expanded.
	const collapsed = new SvelteSet<string>();

	function toggle(id: string) {
		if (collapsed.has(id)) collapsed.delete(id);
		else collapsed.add(id);
	}

	function scrollParent(el: HTMLElement): HTMLElement | null {
		for (let p = el.parentElement; p; p = p.parentElement) {
			const oy = getComputedStyle(p).overflowY;
			if (oy === 'auto' || oy === 'scroll') return p;
		}
		return null;
	}

	// While following the tail, keep the active (selected) row in view as it advances.
	// We scroll the timeline's own container by the minimum amount, and only when the
	// row is actually out of view, so a row already on screen never jumps.
	const followSelected: Attachment<HTMLElement> = (node) => {
		$effect(() => {
			// Read `autofocus` before `selected` so that while following is off the
			// effect never subscribes to selection changes and stays dormant.
			if (!autofocus) return;
			selected; // re-run whenever the active row changes
			untrack(() => {
				const el = node.querySelector<HTMLElement>('[aria-current="true"]');
				const container = scrollParent(node);
				if (!el || !container) return;
				const c = container.getBoundingClientRect();
				const r = el.getBoundingClientRect();
				if (r.top < c.top) container.scrollTop += r.top - c.top;
				else if (r.bottom > c.bottom) container.scrollTop += r.bottom - c.bottom;
			});
		});
	};
</script>

{#snippet phaseRow(row: Row)}
	{@const meta = phaseMeta(row.ev.phase)}
	{@const ev = row.ev}
	{@const isSel = row.index === selected}
	<button
		type="button"
		onclick={() => onselect(row.index)}
		aria-current={isSel ? 'true' : undefined}
		class="flex w-full items-center gap-2.5 rounded-md py-1.5 pr-2 pl-2 text-left text-sm transition-colors {isSel
			? 'bg-elevated'
			: 'hover:bg-elevated/40'}"
	>
		<PhaseBadge label={meta.label} color={`bg-surface ${meta.color}`} variant="rail" selected={isSel} />
		{#if ev.title}
			<span
				class="min-w-0 flex-1 truncate {ev.isError
					? 'text-danger'
					: isSel
						? 'text-fg'
						: 'text-muted'}"
			>
				{ev.title}
			</span>
		{/if}
		{#if ev.hasScreenshot}
			<Image size={12} class="shrink-0 text-faint" aria-label="has screenshot" />
		{/if}
	</button>
{/snippet}

<ol {@attach followSelected} class="flex flex-col gap-2 p-1.5">
	{#each groups as group (group.header?.ev.id ?? `lead-${group.items[0]?.ev.id ?? 'empty'}`)}
		<li>
			{#if group.header}
				{@const ev = group.header.ev}
				{@const headerId = String(ev.id)}
				{@const isOpen = !collapsed.has(headerId)}
				{@const isSel = group.header.index === selected}
				<div class="flex items-stretch">
					<button
						type="button"
						onclick={() => toggle(headerId)}
						aria-label={isOpen ? 'Collapse step' : 'Expand step'}
						aria-expanded={isOpen}
						class="flex w-5 shrink-0 items-center justify-center text-faint transition-colors hover:text-muted"
					>
						{#if isOpen}<ChevronDown size={14} />{:else}<ChevronRight size={14} />{/if}
					</button>
					<button
						type="button"
						onclick={() => onselect(group.header!.index)}
						aria-current={isSel ? 'true' : undefined}
						class="flex min-w-0 flex-1 items-center gap-2.5 rounded-md py-1.5 pr-2 pl-0 text-left transition-colors {isSel
							? 'bg-elevated'
							: 'hover:bg-elevated/40'}"
					>
						<PhaseBadge
							label={ev.kind ?? 'goal'}
							color="bg-goal/15 text-goal"
							variant="rail"
							selected={isSel}
							selectedClass="border-warning/70 ring-1 ring-warning/70"
							unselectedClass="border-goal/40"
						/>
						<span
							class="min-w-0 flex-1 truncate text-sm font-medium {ev.isError ? 'text-danger' : 'text-fg'}"
						>
							{ev.goal ?? ev.title ?? 'Goal'}
						</span>
						{#if !isOpen && group.items.length}
							<span class="shrink-0 text-xs text-faint">{group.items.length}</span>
						{/if}
						{#if ev.hasScreenshot}
							<Image size={12} class="shrink-0 text-faint" aria-label="has screenshot" />
						{/if}
					</button>
				</div>
				{#if isOpen && group.items.length}
					<div transition:slide={{ duration: 150 }} class="mt-0.5 ml-2.5 space-y-0.5 overflow-hidden pl-4">
						{#each group.items as row (row.ev.id)}
							{@render phaseRow(row)}
						{/each}
					</div>
				{/if}
			{:else}
				<div class="space-y-0.5">
					{#each group.items as row (row.ev.id)}
						{@render phaseRow(row)}
					{/each}
				</div>
			{/if}
		</li>
	{/each}
</ol>
