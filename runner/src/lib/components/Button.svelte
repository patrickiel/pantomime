<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';

	let {
		variant = 'neutral',
		size = 'md',
		disabledClass = 'disabled:opacity-40',
		children,
		class: extra = '',
		...rest
	}: {
		variant?: 'neutral' | 'primary' | 'danger';
		size?: 'md' | 'lg';
		/** Literal Tailwind class for the disabled state (full strings so they survive purging). */
		disabledClass?: string;
		class?: string;
	} & HTMLButtonAttributes = $props();

	const variants = {
		neutral: 'border-border-strong text-muted hover:bg-elevated',
		primary: 'border-primary/60 text-primary hover:bg-primary/10',
		danger: 'border-danger/60 text-danger hover:bg-danger/10'
	};

	// Both sizes share py-1.5 text-sm; only the horizontal padding differs
	// (lg = toolbar buttons, md = compact row actions).
	const sizes = {
		md: 'px-2.5 py-1.5 text-sm',
		lg: 'px-3 py-1.5 text-sm'
	};
</script>

<button
	class="inline-flex items-center gap-1.5 rounded-md border {sizes[size]} {variants[
		variant
	]} {disabledClass} {extra}"
	{...rest}
>
	{@render children?.()}
</button>
