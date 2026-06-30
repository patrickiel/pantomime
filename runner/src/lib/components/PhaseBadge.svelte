<script lang="ts">
	let {
		label,
		color,
		variant = 'inline',
		selected = false,
		selectedClass = 'ring-1 ring-warning/70',
		unselectedClass = ''
	}: {
		label: string;
		color: string;
		variant?: 'inline' | 'rail';
		selected?: boolean;
		selectedClass?: string;
		unselectedClass?: string;
	} = $props();

	const geometry = {
		inline: 'px-2 py-0.5',
		rail: 'h-6 min-w-[3.5rem] shrink-0 justify-center px-1.5'
	};
</script>

<span
	class="inline-flex items-center rounded-md border text-[10px] font-semibold uppercase tracking-wide {geometry[
		variant
	]} {color} {selected ? selectedClass : unselectedClass}"
>
	{label}
</span>
