/**
 * Launch and track Pantomime test runs as child processes.
 *
 * `startRun` spawns `uv run panto run <test> [--window …] [--dry-run]` from the
 * repo root; the Python side records the run live to the same SQLite DB the
 * debugger reads, so the existing 1.5s timeline polling shows progress. This
 * registry adds what the DB can't answer on its own: liveness *before* the first
 * row is written, the child's exit code / stderr (e.g. "window not found", which
 * never writes a row), and a Stop button.
 *
 * Single-flight: only one run may write the DB at a time (the recorder reclaims
 * orphaned `running` rows on the next start), so a second start is refused.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { eq, sql } from 'drizzle-orm';
import { getDb } from './db';
import { runs } from './schema';
import { resolveTestFile } from './tests';

export type RunState = 'starting' | 'running' | 'exited';

export interface ActiveRun {
	testId: string;
	relPath: string;
	dryRun: boolean;
	startedAt: number;
	state: RunState;
	exitCode: number | null;
	/** A graceful stop has been requested; the child is unwinding (not yet exited). */
	stopRequested: boolean;
	/** Tail of the child's console (stdout + stderr) — the live SPAV narration plus
	 *  TARGET ERROR / tracebacks / ENOENT. Shown live in the UI. */
	consoleTail: string;
	/** Spawn-level failure (e.g. uv not on PATH). */
	error: string | null;
}

/** The uv launcher binary. Override with `PANTO_UV` if it isn't plain `uv` on PATH. */
const UV = process.env.PANTO_UV ?? 'uv';

/**
 * How long to wait after a graceful stop before force-killing a child that hasn't
 * exited (e.g. wedged in a network/driver hang). The runner normally cancels at the
 * next safe point — within the current in-flight planner call — so this is just a
 * last resort. Override with `PANTO_STOP_GRACE_MS`.
 */
const STOP_GRACE_MS = Number(process.env.PANTO_STOP_GRACE_MS) || 60_000;

/** How much of the child's console to retain for the live view (chars, kept as a tail). */
const CONSOLE_CAP = 16_000;

/**
 * Append a console chunk, honoring carriage returns the way a terminal would: a
 * lone `\r` (in-place progress spinners like "grounding… | 55s") rewinds to the
 * start of the current line so frames overwrite instead of piling up thousands of
 * copies and evicting the real narration. CRLF is treated as a plain newline.
 * Returns a bounded tail.
 */
function appendConsole(prev: string, chunk: string): string {
	let out = prev;
	for (let i = 0; i < chunk.length; i++) {
		const c = chunk[i];
		if (c === '\r') {
			if (chunk[i + 1] === '\n') continue; // CRLF: let the '\n' add the newline
			out = out.slice(0, out.lastIndexOf('\n') + 1); // lone CR: drop the in-progress line
		} else {
			out += c;
		}
	}
	return out.slice(-CONSOLE_CAP);
}

interface Tracked {
	proc: ChildProcess;
	info: ActiveRun;
	/** The selected project's database — bookkeeping writes (console, reclaim) target it. */
	db: string;
	/** Sentinel file the child polls; created on stop to request cancellation. */
	cancelFile: string;
	/** Pending force-kill fallback, cleared when the child exits cleanly. */
	killTimer: ReturnType<typeof setTimeout> | null;
}

// Module singleton: survives across requests within the node server process.
// Keyed by YAML test id so the per-row Stop button can ask "is THIS test running?".
const active = new Map<string, Tracked>();

export function anyRunning(): boolean {
	for (const { info } of active.values()) if (info.state !== 'exited') return true;
	return false;
}

/** A test waiting its turn in the "Run all" queue (single-flight runs them in order). */
export type QueueItem = Parameters<typeof startRun>[0];

// Pending runs, drained one at a time as each child exits (see `pump`). Module-level
// so it survives across requests, alongside the `active` registry.
let queue: QueueItem[] = [];

function isActive(testId: string): boolean {
	const t = active.get(testId);
	return !!t && t.info.state !== 'exited';
}

/**
 * Append tests to the run queue and kick it off. Tests already running or already
 * queued are skipped, so clicking "Run all" twice (or while one is running) never
 * double-queues. The first item starts immediately if nothing is running.
 */
export function enqueueRuns(items: QueueItem[]): void {
	for (const item of items) {
		if (isActive(item.testId)) continue;
		if (queue.some((q) => q.testId === item.testId)) continue;
		queue.push(item);
	}
	pump();
}

/** The test ids still waiting in the queue (for the loader / UI "Queued" badges). */
export function queuedTestIds(): string[] {
	return queue.map((q) => q.testId);
}

/** Drop every still-pending test from the queue; the in-flight run keeps going. */
export function clearQueue(): number {
	const n = queue.length;
	queue = [];
	return n;
}

/**
 * Start the next queued test if nothing is running. Called after each child exits so
 * the queue advances on its own. Items that fail to start synchronously (e.g. their
 * file vanished) are skipped rather than stalling the whole batch.
 */
function pump(): void {
	if (anyRunning()) return;
	while (queue.length) {
		const next = queue.shift()!;
		try {
			startRun(next);
			return;
		} catch {
			// Unstartable item — skip it and try the next one.
		}
	}
}

/** Public snapshot of every tracked run (for the status endpoint / loader merge). */
export function snapshot(): ActiveRun[] {
	return [...active.values()].map((r) => ({ ...r.info }));
}

/**
 * Forget finished (exited) runs from the in-memory registry.
 *
 * The registry keeps an entry after its child exits so the loader can still
 * surface a child failure that never wrote a DB row (e.g. window-not-found). But
 * when the user clears run history, those rows are gone — and a leftover exited
 * entry would otherwise keep driving a test's `failed` status + console error in
 * the loader, showing a phantom failure under "No runs yet." Live (non-exited)
 * runs are left intact.
 */
export function forgetExitedRuns(): void {
	for (const [testId, t] of active) {
		if (t.info.state === 'exited') active.delete(testId);
	}
}

export function startRun(opts: {
	testId: string;
	relPath: string;
	window: string | null;
	dryRun: boolean;
	/** Selected project root — the child's cwd (so config + runs resolve there). */
	root: string;
	/** Selected project's database — for console/reclaim bookkeeping. */
	db: string;
}): ActiveRun {
	if (anyRunning()) throw new Error('A test run is already in progress.');
	if (!resolveTestFile(opts.root, opts.relPath)) throw new Error(`Unknown or invalid test file: ${opts.relPath}`);

	// Fresh per-run sentinel path under the OS temp dir; nothing stale to clear.
	// `panto run` reads PANTO_CANCEL_FILE and stops when this file appears.
	const cancelFile = join(tmpdir(), `panto-cancel-${randomUUID()}.flag`);

	// Repo-root-relative path (no spaces) keeps the argv clean; cwd makes it resolve.
	const args = ['run', 'panto', 'run', opts.relPath];
	if (opts.window) args.push('--window', opts.window);
	if (opts.dryRun) args.push('--dry-run');

	const info: ActiveRun = {
		testId: opts.testId,
		relPath: opts.relPath,
		dryRun: opts.dryRun,
		startedAt: Date.now(),
		state: 'starting',
		exitCode: null,
		stopRequested: false,
		consoleTail: '',
		error: null
	};

	const proc = spawn(UV, args, {
		cwd: opts.root,
		env: { ...process.env, PANTO_CANCEL_FILE: cancelFile },
		stdio: ['ignore', 'pipe', 'pipe']
	});
	const tracked: Tracked = { proc, info, db: opts.db, cancelFile, killTimer: null };
	active.set(opts.testId, tracked);

	const onOutput = (buf: Buffer) => {
		// First byte of output means Python is alive and past argument parsing.
		if (info.state === 'starting') info.state = 'running';
		info.consoleTail = appendConsole(info.consoleTail, buf.toString());
	};
	// `panto` narrates the SPAV loop on stderr and prints the result on stdout;
	// capture both so the UI shows the full console.
	proc.stderr?.on('data', onOutput);
	proc.stdout?.on('data', onOutput);
	proc.on('error', (e) => {
		info.state = 'exited';
		info.exitCode = -1;
		info.error =
			(e as NodeJS.ErrnoException).code === 'ENOENT'
				? `Could not launch "${UV}" — is uv installed and on PATH? (set PANTO_UV to override)`
				: e.message;
		persistConsole(info, tracked.db);
		cleanup(tracked);
		pump(); // advance the "Run all" queue past this failed start
	});
	proc.on('exit', (code) => {
		info.state = 'exited';
		info.exitCode = code;
		// Stop was requested and the child is now gone. If it unwound cleanly Python
		// already wrote `canceled`; if its final write failed or it was force-killed,
		// the row is still `running` — reclaim it. No-op if already finished, and
		// running it here (after exit) avoids racing Python's own last write.
		if (info.stopRequested) reclaimRunningRows(tracked.db);
		// The console is captured only here in node (Python streams it to stderr but
		// can't faithfully re-render the in-place spinner rewrites). Persist the tail
		// so a finished run keeps its console after it's no longer the latest run /
		// after a server restart, instead of the dock vanishing.
		persistConsole(info, tracked.db);
		cleanup(tracked);
		pump(); // start the next queued test, if any
	});

	return { ...info };
}

/** Release the force-kill timer and the sentinel file once a child is done. */
function cleanup(t: Tracked): void {
	if (t.killTimer) {
		clearTimeout(t.killTimer);
		t.killTimer = null;
	}
	try {
		rmSync(t.cancelFile, { force: true });
	} catch {
		// temp file; the OS reaps it eventually.
	}
}

/**
 * Stop the run for a test, gracefully.
 *
 * First call: create the sentinel file so the runner cancels at its next safe
 * point (between actions) and records a clean `canceled` status itself. A
 * fallback timer force-kills the tree only if the child wedges. A *second* call
 * while already stopping escalates straight to a force-kill — so an impatient
 * second click on "Stopping…" kills now instead of waiting out the grace period.
 *
 * Either way the `exit` handler reconciles the DB row once the child is gone, so
 * a stopped run never lingers as `running`.
 */
export function stopRun(testId: string): boolean {
	const t = active.get(testId);
	if (!t || t.info.state === 'exited') return false;

	if (t.info.stopRequested) {
		forceKill(t); // second click: don't wait out the grace period
		return true;
	}

	t.info.stopRequested = true;
	try {
		writeFileSync(t.cancelFile, ''); // existence = "please stop"
	} catch {
		// Couldn't write the flag — skip the grace period and force-kill now.
		forceKill(t);
		return true;
	}
	t.killTimer = setTimeout(() => forceKill(t), STOP_GRACE_MS);
	return true;
}

/**
 * Last resort: kill the whole tree. The child's `exit` handler then does all the
 * bookkeeping (state, row reclaim, cleanup) once the process is actually dead —
 * so there's no double cleanup and no reclaim racing Python's final write.
 */
function forceKill(t: Tracked): void {
	if (t.info.state === 'exited') return;
	const pid = t.proc.pid;
	if (process.platform === 'win32' && pid) {
		// SIGINT doesn't reach a Windows console child through `uv`; kill the tree
		// (the python grandchild holds the DB).
		spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
	} else {
		t.proc.kill('SIGKILL');
	}
}

/**
 * Save the child's captured console onto its run row so it survives past being the
 * latest run (and past a server restart). Single-flight means the run that just
 * exited is the most-recent row for this test, so target that one. Best-effort: the
 * console is a convenience, never block exit bookkeeping on it.
 */
function persistConsole(info: ActiveRun, dbFile: string): void {
	if (!info.consoleTail) return;
	try {
		const db = getDb(dbFile);
		const latest = db
			.select({ id: runs.id })
			.from(runs)
			.where(eq(runs.testId, info.testId))
			.orderBy(sql`${runs.startedAt} desc`)
			.limit(1)
			.get();
		if (latest) db.update(runs).set({ console: info.consoleTail }).where(eq(runs.id, latest.id)).run();
	} catch {
		// best-effort: a missing console just falls back to the empty dock as before.
	}
}

/** Mark any lingering `running` row as `canceled` (force-kill leaves no clean finish). */
function reclaimRunningRows(dbFile: string): void {
	try {
		getDb(dbFile)
			.update(runs)
			.set({ status: 'canceled', finishedAt: Date.now() })
			.where(eq(runs.status, 'running'))
			.run();
	} catch {
		// best-effort: the next `panto run` reclaims it anyway.
	}
}
