import { basename, join } from 'node:path';
import { readdirSync, rmSync } from 'node:fs';
import { sql } from 'drizzle-orm';
import { fail } from '@sveltejs/kit';
import { getDb, runsDir } from '$lib/server/db';
import { events, runs } from '$lib/server/schema';
import { listTests } from '$lib/server/tests';
import { currentProject } from '$lib/server/project';
import { anyRunning, snapshot, forgetExitedRuns, queuedTestIds, type ActiveRun } from '$lib/server/runner';
import type { RunSummary, TestRow } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const project = currentProject();
	const tests = listTests(project.root);

	// All recorded runs grouped by test_id (joins on the YAML id, not the path),
	// newest first, so each test can show its own inline run history.
	const byTest = new Map<string, RunSummary[]>();
	try {
		const db = getDb(project.db);
		const counts = db
			.select({ runId: events.runId, n: sql<number>`count(*)` })
			.from(events)
			.groupBy(events.runId)
			.all();
		const countMap = new Map(counts.map((c) => [c.runId, c.n]));

		const rows = db.select().from(runs).orderBy(sql`${runs.startedAt} desc`).all();
		for (const r of rows) {
			const summary: RunSummary = {
				id: r.id,
				testId: r.testId,
				title: r.title,
				status: r.status,
				dryRun: !!r.dryRun,
				startedAt: r.startedAt,
				finishedAt: r.finishedAt,
				durationS: r.durationS,
				usage: r.usage ? JSON.parse(r.usage) : {},
				eventCount: countMap.get(r.id) ?? 0
			};
			const list = byTest.get(r.testId);
			if (list) list.push(summary);
			else byTest.set(r.testId, [summary]);
		}
	} catch {
		// No DB yet (no run has ever happened) — every test is simply "never-run".
	}

	// In-memory liveness: knows `starting` before any row is written, and the
	// child's exit/stderr for failures that never produce a row (window not found).
	const reg = new Map<string, ActiveRun>();
	for (const r of snapshot()) reg.set(r.testId, r);

	const queuedIds = queuedTestIds();
	const queued = new Set(queuedIds);

	const rows: TestRow[] = tests.map((t): TestRow => {
		const history = byTest.get(t.id) ?? [];
		const run = history[0]; // newest, or undefined
		const active = reg.get(t.id);
		const live = !!active && active.state !== 'exited';

		const stopping = !!active && active.stopRequested && active.state !== 'exited';

		let status: string;
		let error: string | null = t.parseError;
		if (live) {
			status = 'running';
		} else if (
			active &&
			active.state === 'exited' &&
			!active.stopRequested &&
			(active.exitCode ?? 0) !== 0 &&
			(!run || active.startedAt >= run.startedAt)
		) {
			// Child failed without writing a newer run row (e.g. window-not-found
			// exits before the recorder starts). Surface its console/spawn error.
			// A stop-requested exit is expected (canceled), not a failure.
			status = 'failed';
			error = active.error ?? lastLines(active.consoleTail) ?? `exited with code ${active.exitCode}`;
		} else if (run) {
			status = run.status;
		} else {
			status = 'never-run';
		}

		// Safety net: a stop was requested and the child has exited, but the DB row
		// is still 'running' (Python's final write failed, or the force-kill reclaim
		// didn't land). Show it as canceled rather than a stuck 'running'.
		if (active && active.stopRequested && active.state === 'exited' && status === 'running') {
			status = 'canceled';
		}

		return {
			id: t.id,
			title: t.title,
			relPath: t.relPath,
			tags: t.tags,
			priority: t.priority,
			window: t.window,
			parseError: t.parseError,
			status,
			live,
			stopping,
			queued: queued.has(t.id) && !live,
			latestRunId: run?.id ?? null,
			lastStartedAt: run?.startedAt ?? null,
			lastDurationS: run?.durationS ?? null,
			lastCostUsd: run?.usage?.cost_usd ?? null,
			runCount: history.length,
			error,
			recentRuns: history.slice(0, 8)
		};
	});

	return { tests: rows, anyRunning: anyRunning(), queued: queuedIds };
};

function lastLines(s: string): string | null {
	const t = s.trim();
	if (!t) return null;
	return t.split(/\r?\n/).slice(-3).join('\n');
}

export const actions: Actions = {
	/**
	 * Delete every recorded run from the debugger database *and* the on-disk run
	 * artifact folders (screenshots, result.json, junit.xml). The artifact dirs are
	 * keyed by `<test-id>/<timestamp>`, unrelated to the DB's uuid run ids, so we
	 * can't match them per-run — clearing wipes every folder under the runs dir,
	 * keeping only the SQLite database (and its WAL/SHM sidecars).
	 */
	clear: async () => {
		const project = currentProject();
		try {
			const db = getDb(project.db);
			// Events reference runs, so delete children first regardless of FK enforcement.
			db.delete(events).run();
			db.delete(runs).run();

			// The DB is now empty, but the in-memory registry still remembers exited
			// runs from this server session; drop them too, or a finished failure
			// re-surfaces on the test row (status + console tail) under "No runs yet."
			forgetExitedRuns();

			const root = runsDir(project.db);
			const dbName = basename(project.db);
			for (const entry of readdirSync(root, { withFileTypes: true })) {
				// Keep the database and its `-wal`/`-shm` sidecars; remove everything else.
				if (entry.name === dbName || entry.name.startsWith(`${dbName}-`)) continue;
				rmSync(join(root, entry.name), { recursive: true, force: true });
			}
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : String(e) });
		}
		return { cleared: true };
	}
};
