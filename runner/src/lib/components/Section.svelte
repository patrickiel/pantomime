<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		title,
		boxed = true,
		children
	}: {
		title: string;
		boxed?: boolean;
		children: Snippet;
	} = $props();
</script>

<div>
	<h3 class="mb-1 text-xs uppercase tracking-wide text-subtle">{title}</h3>
	{#if boxed}
		<div class="rounded-md border border-border bg-base/60 p-3 text-sm">
			{@render children()}
		</div>
	{:else}
		{@render children()}
	{/if}
</div>
