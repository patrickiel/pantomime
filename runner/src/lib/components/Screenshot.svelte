<script lang="ts">
	import type { ScreenStateView } from '$lib/types';

	let {
		eventId,
		screenState,
		showBoxes = true,
		highlight = $bindable<string | null>(null)
	}: {
		eventId: number;
		screenState: ScreenStateView | null;
		showBoxes?: boolean;
		highlight?: string | null;
	} = $props();

	let region = $derived(screenState?.region ?? [0, 0, 1, 1]);
	let rw = $derived(region[2] || 1);
	let rh = $derived(region[3] || 1);
	// Captures are in physical pixels, so a high-DPI screen records larger than it
	// looks. Cap the display at the logical width (physical / scale) to compensate.
	let scale = $derived(screenState?.scale && screenState.scale > 0 ? screenState.scale : 1);
	let displayWidth = $derived(rw / scale);

	function pct(box: [number, number, number, number]) {
		return {
			left: `${(box[0] / rw) * 100}%`,
			top: `${(box[1] / rh) * 100}%`,
			width: `${(box[2] / rw) * 100}%`,
			height: `${(box[3] / rh) * 100}%`
		};
	}
</script>

<div
	class="relative w-full overflow-hidden rounded-lg border border-border bg-surface"
	style="max-width: {displayWidth}px;"
>
	<img
		src="/api/screenshot/{eventId}"
		alt="Screen at step {eventId}"
		class="block w-full select-none"
		draggable="false"
	/>
	{#if showBoxes && screenState}
		<div class="pointer-events-none absolute inset-0">
			{#each screenState.elements as el (el.id)}
				{@const p = pct(el.box)}
				{@const active = highlight === el.id}
				<div
					class="absolute border transition-colors {active
						? 'border-warning bg-warning/20'
						: el.is_password
							? 'border-danger/70'
							: 'border-primary/60'}"
					style="left:{p.left}; top:{p.top}; width:{p.width}; height:{p.height};"
				>
					<span
						class="absolute -top-4 left-0 whitespace-nowrap rounded px-1 text-[10px] leading-4 {active
							? 'bg-warning text-base'
							: 'bg-primary/80 text-base'}"
					>
						{el.id}
					</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
