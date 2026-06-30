<script lang="ts">
	import { ArrowRight } from '@lucide/svelte';
	import Screenshot from './Screenshot.svelte';
	import Badge from './Badge.svelte';
	import PhaseBadge from './PhaseBadge.svelte';
	import Section from './Section.svelte';
	import type { DebugEvent } from '$lib/types';
	import { fmtClock, fmtMs, phaseMeta } from '$lib/ui';

	// `durationMs` is the gap to the next event (how long this step took); null for the last
	// event. For a goal event it is the "self" time before its first sub-event. `totalDurationMs`
	// is the whole group's span (only set for goal events) so a step / precondition / teardown
	// shows both its own time and the time of everything underneath it.
	let {
		event,
		durationMs = null,
		totalDurationMs = null
	}: { event: DebugEvent; durationMs?: number | null; totalDurationMs?: number | null } = $props();

	// Show self and total separately only when the group has sub-steps (total exceeds self);
	// for a childless goal the two coincide, so a single value reads cleaner.
	let splitTiming = $derived(
		totalDurationMs != null && durationMs != null && totalDurationMs > durationMs
	);

	let showBoxes = $state(true);
	// Hover-driven element highlight (set on row mouseenter, cleared on mouseleave).
	let highlight = $state<string | null>(null);
	let meta = $derived(phaseMeta(event.phase));
	// Goal rows mirror the timeline header: the kind (step/precondition/teardown) is the
	// badge and the bare goal is the headline. Other phases keep their own short title.
	let isGoal = $derived(event.phase === 'goal');
	let badgeLabel = $derived(isGoal ? (event.kind ?? 'goal') : meta.label);
	let headline = $derived(isGoal ? (event.goal ?? event.title ?? meta.label) : (event.title ?? meta.label));
	// For non-goal phases the goal block adds the parent context the short title omits.
	let showGoal = $derived(!isGoal && !!event.goal && !(event.title ?? '').includes(event.goal!));
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2">
		<PhaseBadge label={badgeLabel} color={meta.color} />
		<span class="text-sm font-medium text-fg">{headline}</span>
		{#if event.passed === true}
			<Badge tone="primary">passed</Badge>
		{:else if event.passed === false}
			<Badge tone="danger">failed</Badge>
		{/if}
		{#if event.isError}
			<Badge tone="danger">error</Badge>
		{/if}
		<span class="ml-auto font-mono text-xs text-subtle">
			#{event.seq} · {fmtClock(event.ts)}{#if splitTiming}
				· self {fmtMs(durationMs)} · total {fmtMs(totalDurationMs)}{:else if totalDurationMs != null}
				· {fmtMs(totalDurationMs)}{:else if durationMs != null}
				· {fmtMs(durationMs)}{/if}
		</span>
	</div>

	{#if showGoal}
		<div class="text-sm text-muted">
			<span class="text-subtle">{event.kind ?? 'goal'}{event.attempt && event.attempt > 1 ? ` (attempt ${event.attempt})` : ''}:</span>
			{event.goal}
		</div>
	{/if}

	{#if event.hasScreenshot}
		<div class="flex items-center justify-between">
			<span class="text-xs uppercase tracking-wide text-subtle">Screen</span>
			<label class="flex items-center gap-1.5 text-xs text-muted">
				<input type="checkbox" bind:checked={showBoxes} class="accent-primary" />
				element boxes
			</label>
		</div>
		<Screenshot eventId={event.id} screenState={event.screenState} {showBoxes} bind:highlight />
	{:else}
		<div class="rounded-lg border border-dashed border-border bg-base/60 p-6 text-center text-sm text-subtle">
			No screenshot for this {meta.label.toLowerCase()} event.
		</div>
	{/if}

	{#if event.reasoning}
		<Section title="Reasoning">
			<p class="text-muted">{event.reasoning}</p>
		</Section>
	{/if}

	{#if event.actionType || event.outcome}
		<Section title="Action">
			<div class="flex items-center gap-1.5 font-mono text-fg">
				{event.actionType}{#if event.elementRef}<ArrowRight size={13} class="text-subtle" />{event.elementRef}{/if}
			</div>
			{#if event.outcome}
				<div class="mt-1 text-muted">{event.outcome}</div>
			{/if}
		</Section>
	{/if}

	{#if event.verdictReasoning}
		<Section
			title={`Verdict${event.verdictConfidence != null ? ` · ${(event.verdictConfidence * 100).toFixed(0)}% confidence` : ''}`}
		>
			<p class="text-muted">{event.verdictReasoning}</p>
		</Section>
	{/if}

	{#if event.screenState && event.screenState.elements.length}
		<Section
			title={`Elements (${event.screenState.elements.length}) · stable=${String(event.screenState.stable)}`}
			boxed={false}
		>
			<div class="max-h-64 overflow-auto rounded-md border border-border">
				<table class="w-full text-xs">
					<thead class="sticky top-0 bg-surface text-left text-subtle">
						<tr>
							<th class="px-2 py-1">id</th>
							<th class="px-2 py-1">role</th>
							<th class="px-2 py-1">name</th>
							<th class="px-2 py-1">text</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-border/60">
						{#each event.screenState.elements as el (el.id)}
							<tr
								class="cursor-default hover:bg-warning/10 {highlight === el.id ? 'bg-warning/15' : ''}"
								onmouseenter={() => (highlight = el.id)}
								onmouseleave={() => (highlight = null)}
							>
								<td class="px-2 py-1 font-mono text-primary">{el.id}</td>
								<td class="px-2 py-1 text-muted">{el.role}</td>
								<td class="px-2 py-1 text-fg">{el.name}</td>
								<td class="px-2 py-1 text-subtle">{el.is_password ? '••••' : el.text}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</Section>
	{/if}
</div>
