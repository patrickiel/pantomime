/** Shapes shared between server loaders and components (no server-only imports). */

/** Token counts for one reasoning role (planner or judge). */
export interface RoleUsage {
	input_tokens?: number;
	output_tokens?: number;
	cache_read_input_tokens?: number;
	cache_creation_input_tokens?: number;
}

/**
 * A run's token usage: the flat totals the debugger displays, plus a per-role
 * breakdown (`planner` / `judge`) so each role is priced by its own model.
 */
export interface Usage extends RoleUsage {
	/** Estimated USD cost, computed from per-role tokens and per-model pricing. */
	cost_usd?: number;
	planner?: RoleUsage;
	judge?: RoleUsage;
}

export interface RunSummary {
	id: string;
	testId: string;
	title: string;
	status: string; // running | passed | failed
	dryRun: boolean;
	startedAt: number;
	finishedAt: number | null;
	durationS: number | null;
	usage: Usage;
	eventCount: number;
}

/** One row of the Tests list: a discovered YAML test merged with its latest run. */
export interface TestRow {
	id: string;
	title: string;
	relPath: string;
	tags: string[];
	priority: string | null;
	window: string | null;
	parseError: string | null;
	/** passed | failed | running | canceled | never-run (registry liveness wins). */
	status: string;
	/** True while a child process for this test is starting/running. */
	live: boolean;
	/** True after Stop was requested but before the child has exited. */
	stopping: boolean;
	/** Waiting its turn in the "Run all" queue (not yet started). */
	queued: boolean;
	/** Latest run, if any has ever been recorded. */
	latestRunId: string | null;
	lastStartedAt: number | null;
	lastDurationS: number | null;
	/** Estimated USD cost of the latest run (from token usage), if recorded. */
	lastCostUsd: number | null;
	runCount: number;
	/** Spawn / target error surfaced from the child process (e.g. window not found). */
	error: string | null;
	/** This test's recorded runs, newest first (for the inline history drawer). */
	recentRuns: RunSummary[];
}

export interface ScreenElement {
	id: string;
	role: string;
	name: string;
	text: string;
	box: [number, number, number, number]; // region-local x, y, w, h
	is_password?: boolean;
}

export interface ScreenStateView {
	region: [number, number, number, number];
	stable: boolean;
	elements: ScreenElement[];
	/** Physical/logical pixel ratio of the captured monitor (1.0 at 100% scaling).
	 *  Used to render the screenshot at its logical size; absent on older runs. */
	scale?: number;
}

export interface DebugEvent {
	id: number;
	seq: number;
	ts: number;
	phase: string; // goal | sense | plan | act | verify | info
	kind: string | null;
	goal: string | null;
	attempt: number | null;
	title: string | null;
	message: string | null;
	reasoning: string | null;
	actionType: string | null;
	elementRef: string | null;
	outcome: string | null;
	isError: boolean;
	passed: boolean | null;
	verdictReasoning: string | null;
	verdictConfidence: number | null;
	screenState: ScreenStateView | null;
	hasScreenshot: boolean;
}
