import { blob, index, integer, real, sqliteTable, text } from 'drizzle-orm/sqlite-core';

/**
 * Drizzle schema for the Pantomime runner database.
 *
 * This MUST stay in lock-step with the Python writer in
 * `src/pantomime/reporting/recorder.py` (`_SCHEMA`). The Python side creates the
 * tables with `CREATE TABLE IF NOT EXISTS` at run time; Drizzle is used here for
 * typed reads (and `drizzle-kit studio`). Change both together.
 */

export const runs = sqliteTable('runs', {
	id: text('id').primaryKey(),
	testId: text('test_id').notNull(),
	title: text('title').notNull(),
	status: text('status').notNull(), // running | passed | failed | canceled
	region: text('region'), // json [x, y, w, h]
	dryRun: integer('dry_run').notNull().default(0),
	startedAt: integer('started_at').notNull(), // epoch ms
	finishedAt: integer('finished_at'),
	durationS: real('duration_s'),
	usage: text('usage'), // json
	console: text('console') // tail of the child's stdout+stderr, persisted on finish
});

export const events = sqliteTable(
	'events',
	{
		id: integer('id').primaryKey({ autoIncrement: true }),
		runId: text('run_id')
			.notNull()
			.references(() => runs.id),
		seq: integer('seq').notNull(),
		ts: integer('ts').notNull(), // epoch ms
		phase: text('phase').notNull(), // goal | sense | plan | act | verify | info
		kind: text('kind'), // precondition | step | assertion | teardown
		goal: text('goal'),
		attempt: integer('attempt'),
		title: text('title'),
		message: text('message'),
		reasoning: text('reasoning'),
		actionType: text('action_type'),
		elementRef: text('element_ref'),
		outcome: text('outcome'),
		isError: integer('is_error').notNull().default(0),
		passed: integer('passed'), // nullable tri-state
		verdictReasoning: text('verdict_reasoning'),
		verdictConfidence: real('verdict_confidence'),
		screenState: text('screen_state'), // json: region/stable/elements
		screenshot: blob('screenshot', { mode: 'buffer' }) // redacted PNG bytes
	},
	(t) => [index('idx_events_run').on(t.runId, t.seq)]
);

/** Raw DDL — identical to recorder.py — so the app works even before drizzle-kit runs. */
export const ENSURE_SCHEMA = `
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    test_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,
    region      TEXT,
    dry_run     INTEGER NOT NULL DEFAULT 0,
    started_at  INTEGER NOT NULL,
    finished_at INTEGER,
    duration_s  REAL,
    usage       TEXT,
    console     TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT NOT NULL REFERENCES runs(id),
    seq                INTEGER NOT NULL,
    ts                 INTEGER NOT NULL,
    phase              TEXT NOT NULL,
    kind               TEXT,
    goal               TEXT,
    attempt            INTEGER,
    title              TEXT,
    message            TEXT,
    reasoning          TEXT,
    action_type        TEXT,
    element_ref        TEXT,
    outcome            TEXT,
    is_error           INTEGER NOT NULL DEFAULT 0,
    passed             INTEGER,
    verdict_reasoning  TEXT,
    verdict_confidence REAL,
    screen_state       TEXT,
    screenshot         BLOB
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
` as const;

export type Run = typeof runs.$inferSelect;
export type EventRow = typeof events.$inferSelect;
