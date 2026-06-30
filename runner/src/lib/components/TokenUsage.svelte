<script lang="ts">
	import { ArrowDown, ArrowUp } from '@lucide/svelte';
	import { fmtTokens, fmtCost } from '$lib/ui';
	import type { Usage } from '$lib/types';

	let {
		usage,
		variant = 'list'
	}: {
		usage: Usage | null | undefined;
		variant?: 'list' | 'header';
	} = $props();

	// 'list' rows dim the figures against the busy table; the run header inherits its parent color.
	let iconSize = $derived(variant === 'header' ? 'size-3.5' : 'size-3');
	let tokenClass = $derived(variant === 'header' ? '' : 'text-faint');
	let costClass = $derived(variant === 'header' ? '' : 'text-subtle');
</script>

{#if usage?.input_tokens || usage?.output_tokens}
	<span class="inline-flex items-center gap-1 {tokenClass}" title="input tokens">
		<ArrowDown class={iconSize} />{fmtTokens(usage.input_tokens)}
	</span>
	<span class="inline-flex items-center gap-1 {tokenClass}" title="output tokens">
		<ArrowUp class={iconSize} />{fmtTokens(usage.output_tokens)}
	</span>
{/if}
{#if usage?.cost_usd}
	<span class={costClass} title="estimated cost (cents)">{fmtCost(usage.cost_usd)}</span>
{/if}
