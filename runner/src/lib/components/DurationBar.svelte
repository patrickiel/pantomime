<script lang="ts">
	import type { DebugEvent } from '$lib/types';
	import { fmtMs, phaseFill, phaseMeta } from '$lib/ui';

	let {
		events,
		selected,
		onselect,
		endTs = null
	}: {
		events: DebugEvent[];
		selected: number;
		onselect: (i: number) => void;
		// Wall-clock end of the run, used to measure the final (open) step once it has finished.
		endTs?: number | null;
	} = $props();

	// Each event's duration is the gap to the next event, or to the run's end for the last
	// one. Still-open steps (no next event, run not finished) measure 0 so the bar only
	// reflects elapsed time.
	let durations = $derived(
		events.map((ev, i) => {
			const next = events[i + 1]?.ts ?? endTs;
			return next != null ? Math.max(0, next - ev.ts) : 0;
		})
	);
	let total = $derived(durations.reduce((a, b) => a + b, 0));

	function labelFor(ev: DebugEvent): string {
		const name = phaseMeta(ev.phase).label;
		return ev.title ? `${name}: ${ev.title}` : name;
	}

	// Per-event segments, colored by phase.
	let eventSegs = $derived(
		events.map((ev, i) => ({
			index: i,
			phase: ev.phase,
			label: labelFor(ev),
			ms: durations[i],
			pct: total > 0 ? (durations[i] / total) * 100 : 0,
			isError: ev.isError,
			isSel: i === selected
		}))
	);

	type GroupSeg = {
		label: string;
		goal: string | null;
		startIndex: number;
		indices: number[];
		ms: number;
		pct: number;
		isError: boolean;
		hasSelected: boolean;
	};

	// Groups mirror the timeline: each `goal` event opens a group that owns the sense/plan/
	// act/verify events until the next goal. Events before the first goal form a lead group.
	let groupSegs = $derived.by<GroupSeg[]>(() => {
		const out: GroupSeg[] = [];
		let cur: GroupSeg | null = null;
		for (let i = 0; i < events.length; i++) {
			const ev = events[i];
			if (ev.phase === 'goal') {
				cur = {
					label: ev.kind ?? 'goal',
					goal: ev.goal ?? ev.title ?? 'Goal',
					startIndex: i,
					indices: [i],
					ms: 0,
					pct: 0,
					isError: ev.isError,
					hasSelected: false
				};
				out.push(cur);
			} else {
				if (!cur) {
					cur = {
						label: 'setup',
						goal: null,
						startIndex: i,
						indices: [],
						ms: 0,
						pct: 0,
						isError: false,
						hasSelected: false
					};
					out.push(cur);
				}
				cur.indices.push(i);
			}
		}
		for (const g of out) {
			g.ms = g.indices.reduce((a, i) => a + durations[i], 0);
			g.pct = total > 0 ? (g.ms / total) * 100 : 0;
			g.isError = g.indices.some((i) => events[i].isError);
			g.hasSelected = g.indices.includes(selected);
		}
		return out;
	});
</script>

{#if total > 0}
	<div class="space-y-1.5">
		<div class="flex items-center justify-between text-xs text-subtle">
			<span class="uppercase tracking-wide">Durations</span>
			<span class="font-mono text-muted">{fmtMs(total)} total</span>
		</div>

		<!-- Group tier: teardown / precondition / step spans. -->
		<div class="flex h-5 w-full overflow-hidden rounded">
			{#each groupSegs as g (g.startIndex)}
				{#if g.pct > 0}
					<button
						type="button"
						style="width:{g.pct}%"
						onclick={() => onselect(g.startIndex)}
						title={`${g.label}${g.goal ? `: ${g.goal}` : ''} · ${fmtMs(g.ms)} (${g.pct.toFixed(0)}%)`}
						class="flex items-center overflow-hidden border-r border-base/60 px-1 text-left text-[10px] transition-[width,background-color,border-color,color] duration-300 ease-out {g.isError
							? 'bg-danger/25 text-danger hover:bg-danger/35'
							: 'bg-goal/20 text-goal hover:bg-goal/30'} {g.hasSelected
							? 'ring-1 ring-inset ring-fg/60'
							: ''}"
					>
						{#if g.pct > 6}
							<span class="truncate">{g.label}{g.pct > 14 ? ` ${fmtMs(g.ms)}` : ''}</span>
						{/if}
					</button>
				{/if}
			{/each}
		</div>

		<!-- Element tier: individual sense / plan / act / verify events. -->
		<div class="flex h-2.5 w-full overflow-hidden rounded">
			{#each eventSegs as s (s.index)}
				{#if s.pct > 0}
					<button
						type="button"
						style="width:{s.pct}%"
						onclick={() => onselect(s.index)}
						title={`${s.label} · ${fmtMs(s.ms)} (${s.pct.toFixed(0)}%)`}
						class="border-r border-base/60 transition-[width,filter,opacity] duration-300 ease-out hover:brightness-125 {s.isError
							? 'bg-danger'
							: phaseFill(s.phase)} {s.isSel ? 'ring-1 ring-inset ring-fg' : 'opacity-80'}"
						aria-current={s.isSel ? 'true' : undefined}
					></button>
				{/if}
			{/each}
		</div>
	</div>
{/if}
