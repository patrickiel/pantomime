import { error as kitError } from '@sveltejs/kit';
import { eq, sql } from 'drizzle-orm';
import { getDb } from '$lib/server/db';
import { events, runs } from '$lib/server/schema';
import { currentProject } from '$lib/server/project';
import { snapshot } from '$lib/server/runner';
import type { DebugEvent, RunSummary, ScreenStateView } from '$lib/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
	const { params } = event;
	const db = getDb(currentProject().db);
	const run = db.select().from(runs).where(eq(runs.id, params.id)).get();
	if (!run) throw kitError(404, `Run ${params.id} not found`);

	const rows = db
		.select({
			id: events.id,
			seq: events.seq,
			ts: events.ts,
			phase: events.phase,
			kind: events.kind,
			goal: events.goal,
			attempt: events.attempt,
			title: events.title,
			message: events.message,
			reasoning: events.reasoning,
			actionType: events.actionType,
			elementRef: events.elementRef,
			outcome: events.outcome,
			isError: events.isError,
			passed: events.passed,
			verdictReasoning: events.verdictReasoning,
			verdictConfidence: events.verdictConfidence,
			screenState: events.screenState,
			hasShot: events.screenshot
		})
		.from(events)
		.where(eq(events.runId, params.id))
		.orderBy(events.seq)
		.all();

	const list: DebugEvent[] = rows.map((r) => ({
		id: r.id,
		seq: r.seq,
		ts: r.ts,
		phase: r.phase,
		kind: r.kind,
		goal: r.goal,
		attempt: r.attempt,
		title: r.title,
		message: r.message,
		reasoning: r.reasoning,
		actionType: r.actionType,
		elementRef: r.elementRef,
		outcome: r.outcome,
		isError: !!r.isError,
		passed: r.passed == null ? null : !!r.passed,
		verdictReasoning: r.verdictReasoning,
		verdictConfidence: r.verdictConfidence,
		screenState: r.screenState ? (JSON.parse(r.screenState) as ScreenStateView) : null,
		hasScreenshot: r.hasShot != null
	}));

	const summary: RunSummary = {
		id: run.id,
		testId: run.testId,
		title: run.title,
		status: run.status,
		dryRun: !!run.dryRun,
		startedAt: run.startedAt,
		finishedAt: run.finishedAt,
		durationS: run.durationS,
		usage: run.usage ? JSON.parse(run.usage) : {},
		eventCount: list.length
	};

	// Console (stdout + stderr) is held live in-memory by the runner, keyed by test
	// id, for the most-recent run of that test only. Prefer that for the live/just-
	// finished run so it streams; otherwise fall back to the copy the runner persists
	// onto the run row when the child exits, so older / post-restart runs still show
	// their console instead of the dock vanishing.
	const latest = db
		.select({ id: runs.id })
		.from(runs)
		.where(eq(runs.testId, run.testId))
		.orderBy(sql`${runs.startedAt} desc`)
		.limit(1)
		.get();
	const active = snapshot().find((a) => a.testId === run.testId);
	const live = active && latest?.id === run.id ? active.consoleTail : '';
	const console = live || run.console || '';

	return { run: summary, events: list, console };
};
