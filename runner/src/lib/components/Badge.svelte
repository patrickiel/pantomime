<script lang="ts">
	import type { Snippet } from 'svelte';
	import { badgeTone } from '$lib/ui';

	let {
		tone = 'muted',
		size = 'xs',
		children
	}: {
		tone?: 'primary' | 'danger' | 'warning' | 'muted';
		size?: 'xs' | '10';
		children: Snippet;
	} = $props();
</script>

<span class="rounded px-1.5 py-0.5 {size === '10' ? 'text-[10px]' : 'text-xs'} {badgeTone(tone)}">
	{@render children()}
</span>
