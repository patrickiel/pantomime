<script lang="ts">
	import { statusColor, statusLabel } from '$lib/ui';

	let { status }: { status: string } = $props();
</script>

<span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium uppercase tracking-wide {statusColor(status)}">
	{statusLabel(status)}
</span>
