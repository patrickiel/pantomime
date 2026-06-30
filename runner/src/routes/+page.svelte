<script lang="ts">
	import { onMount } from "svelte";
	import { slide } from "svelte/transition";
	import { SvelteSet } from "svelte/reactivity";
	import { enhance } from "$app/forms";
	import { invalidateAll } from "$app/navigation";
	import {
		RotateCw,
		Trash2,
		Play,
		FlaskConical,
		CircleStop,
		LoaderCircle,
		ChevronRight,
		ChevronDown,
		ListVideo,
	} from "@lucide/svelte";
	import StatusBadge from "$lib/components/StatusBadge.svelte";
	import Button from "$lib/components/Button.svelte";
	import Badge from "$lib/components/Badge.svelte";
	import TokenUsage from "$lib/components/TokenUsage.svelte";
	import { fmtDuration, fmtTime, fmtCost } from "$lib/ui";
	import type { TestRow } from "$lib/types";
	import type { PageData } from "./$types";

	let { data }: { data: PageData } = $props();

	let pendingId = $state<string | null>(null);
	let actionError = $state<string | null>(null);
	let clearing = $state(false);
	const expanded = new SvelteSet<string>();

	// Tests still waiting in the "Run all" queue (single-flight drains them in order).
	let queuedCount = $derived(data.queued?.length ?? 0);
	// A run is in flight somewhere (server enforces single-flight; mirror it in the UI).
	// A non-empty queue counts as busy too, so per-row Run stays disabled between tests.
	let busy = $derived(
		data.anyRunning || pendingId !== null || queuedCount > 0,
	);
	let live = $derived(
		data.tests.some((t) => t.live) ||
			data.anyRunning ||
			pendingId !== null ||
			queuedCount > 0,
	);
	let hasHistory = $derived(data.tests.some((t) => t.runCount > 0));
	// Tests that could be started right now (skip parse errors and anything already live).
	let runnable = $derived(
		data.tests.filter((t) => !t.parseError && !t.live).length,
	);

	onMount(() => {
		const t = setInterval(() => {
			if (live) invalidateAll();
		}, 1500);
		return () => clearInterval(t);
	});

	function toggle(id: string) {
		if (expanded.has(id)) expanded.delete(id);
		else expanded.add(id);
	}

	async function run(test: TestRow, dryRun: boolean) {
		actionError = null;
		pendingId = test.id;
		try {
			const res = await fetch("/api/run", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({ testId: test.id, dryRun }),
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				actionError =
					body.message ?? `Could not start run (${res.status}).`;
				pendingId = null;
			} else {
				// Reveal the run as soon as it starts streaming.
				expanded.add(test.id);
			}
		} catch (e) {
			actionError = e instanceof Error ? e.message : String(e);
			pendingId = null;
		}
		await invalidateAll();
		if (data.tests.find((t) => t.id === test.id)?.live) pendingId = null;
	}

	async function stop(test: TestRow) {
		try {
			await fetch("/api/run/stop", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({ testId: test.id }),
			});
		} finally {
			pendingId = null;
			await invalidateAll();
		}
	}

	// Queue every runnable test; the server runs them one after another.
	async function runAll() {
		actionError = null;
		try {
			const res = await fetch("/api/run/all", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({ dryRun: false }),
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				actionError =
					body.message ?? `Could not start runs (${res.status}).`;
			}
		} catch (e) {
			actionError = e instanceof Error ? e.message : String(e);
		}
		await invalidateAll();
	}

	// Cancel the batch: clears the pending queue. The in-flight run keeps going and
	// can still be stopped from its own row.
	async function stopAll() {
		try {
			await fetch("/api/run/all", { method: "DELETE" });
		} finally {
			await invalidateAll();
		}
	}
</script>

<div class="mb-5 flex items-end justify-between">
	<div>
		<h1 class="text-xl font-semibold">Tests</h1>
		<div class="mt-1 flex items-center gap-2 text-sm text-muted">
			<span>Run a test and watch it play out</span>
		</div>
	</div>
	<div class="flex items-center gap-2">
		{#if queuedCount > 0}
			<Button
				size="lg"
				variant="danger"
				onclick={stopAll}
				title="Stop launching the remaining queued tests"
			>
				<CircleStop size={14} /> Stop all ({queuedCount} queued)
			</Button>
		{:else}
			<Button
				size="lg"
				variant="primary"
				onclick={runAll}
				disabled={busy || runnable === 0}
				disabledClass="disabled:opacity-50"
				title="Run every test, one after another"
			>
				<ListVideo size={14} /> Run all
			</Button>
		{/if}
		<Button size="lg" onclick={() => invalidateAll()}>
			<RotateCw size={14} /> Refresh
		</Button>
		{#if hasHistory}
			<form
				method="POST"
				action="?/clear"
				use:enhance={({ cancel }) => {
					if (
						!confirm(
							"Delete all recorded runs? This cannot be undone.",
						)
					) {
						cancel();
						return;
					}
					clearing = true;
					return async ({ update }) => {
						await update();
						clearing = false;
					};
				}}
			>
				<Button
					type="submit"
					size="lg"
					disabled={clearing}
					disabledClass="disabled:opacity-50"
					title="Delete all recorded run history"
				>
					<Trash2 size={14} />
					{clearing ? "Clearing…" : "Clear history"}
				</Button>
			</form>
		{/if}
	</div>
</div>

{#if actionError}
	<div
		class="mb-4 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger"
	>
		{actionError}
	</div>
{/if}

{#if data.tests.length === 0}
	<div
		class="rounded-lg border border-border bg-surface/40 p-8 text-center text-muted"
	>
		No tests found in this project. Add a
		<code class="font-mono text-muted">.yaml</code> test (see
		<code class="font-mono text-muted">examples/login/tests/login.yaml</code
		>).
	</div>
{:else}
	<div class="overflow-hidden rounded-lg border border-border">
		<table class="w-full text-sm">
			<thead
				class="bg-surface/60 text-left text-xs uppercase tracking-wide text-subtle"
			>
				<tr>
					<th class="w-8 px-2 py-2"></th>
					<th class="px-4 py-2 font-medium">Status</th>
					<th class="px-4 py-2 font-medium">Test</th>
					<th class="px-4 py-2 font-medium">Window</th>
					<th class="px-4 py-2 font-medium">Tags</th>
					<th class="px-4 py-2 font-medium">Last run</th>
					<th class="px-4 py-2 text-right font-medium">Actions</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-border">
				{#each data.tests as t (t.id)}
					{@const starting = pendingId === t.id && !t.live}
					{@const isOpen = expanded.has(t.id)}
					{@const canExpand = t.runCount > 0 || t.live}
					<tr class="align-top hover:bg-surface/40">
						<td class="px-2 py-3">
							<button
								onclick={() => toggle(t.id)}
								disabled={!canExpand}
								class="rounded p-1 text-subtle transition-colors hover:bg-elevated hover:text-fg disabled:opacity-30"
								title={!canExpand
									? "No runs yet"
									: isOpen
										? "Hide runs"
										: "Show runs"}
								aria-label="Toggle run history"
								aria-expanded={isOpen}
							>
								{#if isOpen}<ChevronDown
										size={16}
									/>{:else}<ChevronRight size={16} />{/if}
							</button>
						</td>
						<td class="px-4 py-3">
							<StatusBadge
								status={starting
									? "running"
									: t.queued
										? "queued"
										: t.status}
							/>
						</td>
						<td class="px-4 py-3">
							<button
								type="button"
								onclick={() => canExpand && toggle(t.id)}
								disabled={!canExpand}
								class="block text-left font-medium text-fg {canExpand
									? 'hover:text-fg hover:underline'
									: 'cursor-default'}"
							>
								{t.title}
							</button>
							<div class="font-mono text-xs text-subtle">
								{t.id}
							</div>
							{#if t.error}
								<div
									class="mt-1 max-w-md whitespace-pre-wrap font-mono text-xs text-danger"
								>
									{t.error}
								</div>
							{/if}
						</td>
						<td class="px-4 py-3 text-muted">
							{#if t.window}{t.window}{:else}<span
									class="text-faint">foreground</span
								>{/if}
						</td>
						<td class="px-4 py-3">
							<div class="flex flex-wrap gap-1">
								{#if t.priority}
									<Badge tone="warning" size="10"
										>{t.priority}</Badge
									>
								{/if}
								{#each t.tags as tag (tag)}
									<Badge tone="muted" size="10">{tag}</Badge>
								{/each}
							</div>
						</td>
						<td class="px-4 py-3 text-muted">
							{#if t.latestRunId}
								<a
									href="/runs/{t.latestRunId}"
									class="block hover:text-fg"
								>
									{fmtTime(t.lastStartedAt)}
									{#if t.lastDurationS != null}
										<span class="text-faint"
											>{fmtDuration(
												t.lastDurationS,
											)}</span
										>
									{/if}
									{#if t.lastCostUsd != null}
										<span
											class="text-subtle"
											title="estimated cost (cents)"
											>{fmtCost(t.lastCostUsd)}</span
										>
									{/if}
								</a>
							{/if}
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center justify-end gap-1.5">
								{#if t.live || starting}
									{#if starting}
										<Button
											variant="danger"
											disabled
											disabledClass="disabled:opacity-50"
										>
											<LoaderCircle
												size={14}
												class="animate-spin"
											/> Starting…
										</Button>
									{:else if t.stopping}
										<Button
											variant="danger"
											onclick={() => stop(t)}
											title="Stopping… — click again to force kill"
										>
											<LoaderCircle
												size={14}
												class="animate-spin"
											/> Stopping…
										</Button>
									{:else}
										<Button
											variant="danger"
											onclick={() => stop(t)}
										>
											<CircleStop size={14} /> Stop
										</Button>
									{/if}
								{:else}
									<Button
										variant="primary"
										onclick={() => run(t, false)}
										disabled={busy || !!t.parseError}
										title={t.parseError ?? "Run this test"}
									>
										<Play size={14} /> Run
									</Button>
									<Button
										onclick={() => run(t, true)}
										disabled={busy || !!t.parseError}
										title="Plan without clicking/typing (dry run)"
									>
										<FlaskConical size={14} /> Dry-run
									</Button>
								{/if}
							</div>
						</td>
					</tr>
					{#if isOpen}
						<tr class="bg-base/20">
							<td colspan="7" class="p-0">
								<div
									transition:slide={{ duration: 150 }}
									class="ml-9 pb-1.5"
								>
									{#if t.recentRuns.length === 0}
										<p class="px-3 py-2 text-xs text-faint">
											No runs yet.
										</p>
									{:else}
										{#each t.recentRuns as r (r.id)}
											<a
												href="/runs/{r.id}"
												class="flex items-center gap-3 px-3 py-1.5 text-sm text-muted hover:bg-surface/50"
											>
												<StatusBadge
													status={r.status}
												/>
												<span
													>{fmtTime(
														r.startedAt,
													)}</span
												>
												{#if r.durationS != null}
													<span class="text-faint"
														>{fmtDuration(
															r.durationS,
														)}</span
													>
												{/if}
												<span class="text-faint"
													>{r.eventCount}
													{r.eventCount === 1
														? "step"
														: "steps"}</span
												>
												<TokenUsage
													usage={r.usage}
													variant="list"
												/>
												{#if r.dryRun}<span
														class="text-[10px] text-subtle"
														>dry-run</span
													>{/if}
											</a>
										{/each}
										{#if t.runCount > t.recentRuns.length}
											<p
												class="px-3 pt-1 text-xs text-faint"
											>
												{t.runCount -
													t.recentRuns.length} more runs
											</p>
										{/if}
									{/if}
								</div>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
{/if}
