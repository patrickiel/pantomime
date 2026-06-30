<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { ArrowLeft, FolderGit2 } from '@lucide/svelte';

	let { children, data } = $props();
</script>

<div class="flex h-dvh flex-col overflow-hidden">
	<header class="shrink-0 border-b border-border bg-surface/60 backdrop-blur">
		<div class="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
			<a href="/" class="flex items-center gap-2 font-semibold tracking-tight">
				<img src="/icon.svg" alt="Pantomime" class="size-6" />
				<span>Pantomime <span class="text-muted">Runner</span></span>
			</a>
			{#if page.url.pathname !== '/'}
				<a href="/" class="ml-2 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
					<ArrowLeft size={14} /> tests
				</a>
			{/if}
			<span class="ml-auto inline-flex items-center gap-2 text-sm text-muted" title={data.projectName}>
				<FolderGit2 size={14} />
				{data.projectName}
			</span>
		</div>
	</header>
	<main class="mx-auto flex w-full min-h-0 max-w-7xl flex-1 flex-col overflow-y-auto px-4 py-6">
		{@render children?.()}
	</main>
</div>
