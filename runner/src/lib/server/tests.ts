/**
 * Discover the YAML GUI tests the runner can launch.
 *
 * The Python writer stores `runs.test_id` = the YAML `id` (see recorder.py /
 * runner.py `start_run(test_id=tc.id)`), so we read each file's `id` here to map
 * tests back to their recorded runs. Metadata is parsed in-process (the `yaml`
 * package) rather than shelling out to `panto`, so the polling home page stays
 * cheap.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';
import { parse } from 'yaml';

/** Directories never worth scanning for tests (incl. Pantomime's own config/runs). */
const SKIP_DIRS = new Set([
	'node_modules',
	'.git',
	'.svelte-kit',
	'.venv',
	'__pycache__',
	'runs',
	'config',
	'dist',
	'build'
]);

/** Config/template/schema files that are not tests. */
function isTestFile(name: string): boolean {
	if (!/\.ya?ml$/i.test(name)) return false;
	return name !== 'pantomime.yaml' && name !== 'pantomime.example.yaml';
}

export interface TestMeta {
	/** Absolute path on disk (server-only). */
	file: string;
	/** Path relative to the repo root, posix-style (e.g. `examples/login/tests/login.yaml`). The spawn arg + route key. */
	relPath: string;
	/** YAML `id` — joins to `runs.test_id`. Falls back to the filename if absent. */
	id: string;
	title: string;
	tags: string[];
	priority: string | null;
	/** Default target window (title substring); null = foreground window. */
	window: string | null;
	/** Set when the file could not be read/parsed; the row is shown but not runnable. */
	parseError: string | null;
}

function toPosix(p: string): string {
	return p.split(sep).join('/');
}

function asString(v: unknown): string | null {
	return typeof v === 'string' && v.trim() ? v : null;
}

function asTags(v: unknown): string[] {
	return Array.isArray(v) ? v.filter((t): t is string => typeof t === 'string') : [];
}

function readMeta(file: string, root: string): TestMeta {
	const relPath = toPosix(relative(root, file));
	const base = { file, relPath };
	let body: Record<string, unknown>;
	try {
		const doc = parse(readFileSync(file, 'utf8'));
		if (doc == null || typeof doc !== 'object') {
			throw new Error('top-level document must be a mapping');
		}
		// Accept either { test: {...} } or a bare mapping (mirrors loader.py).
		const root = doc as Record<string, unknown>;
		body = (('test' in root ? root.test : root) ?? {}) as Record<string, unknown>;
		if (typeof body !== 'object') throw new Error('`test:` must be a mapping');
	} catch (e) {
		return {
			...base,
			id: relPath,
			title: relPath,
			tags: [],
			priority: null,
			window: null,
			parseError: e instanceof Error ? e.message : String(e)
		};
	}
	const id = asString(body.id) ?? relPath;
	return {
		...base,
		id,
		title: asString(body.title) ?? id,
		tags: asTags(body.tags),
		priority: asString(body.priority),
		window: asString(body.window),
		parseError: asString(body.id) ? null : 'missing `id` (cannot map to recorded runs)'
	};
}

/** Recursively collect candidate test YAML files under `dir`, skipping noise dirs. */
function walk(dir: string, acc: string[]): void {
	let entries: import('node:fs').Dirent[];
	try {
		entries = readdirSync(dir, { withFileTypes: true });
	} catch {
		return;
	}
	for (const e of entries) {
		if (e.isDirectory()) {
			if (!SKIP_DIRS.has(e.name) && !e.name.startsWith('.')) walk(join(dir, e.name), acc);
		} else if (e.isFile() && isTestFile(e.name)) {
			acc.push(join(dir, e.name));
		}
	}
}

/**
 * Enumerate the runnable YAML tests under a project root (recursively), excluding
 * config/schema files and noise dirs (node_modules, runs, .venv, …). Sorted by
 * relative path. `relPath` is project-root-relative — the spawn arg + route key.
 */
export function listTests(root: string): TestMeta[] {
	const files: string[] = [];
	walk(root, files);
	return files.map((f) => readMeta(f, root)).sort((a, b) => a.relPath.localeCompare(b.relPath));
}

/**
 * Resolve a project-root-relative path back to an absolute file, confined to the
 * project root and to files that actually appear in {@link listTests}. Returns null
 * for anything outside (path traversal, unknown files) — a security gate before we
 * hand a path to `spawn`.
 */
export function resolveTestFile(root: string, relPath: string): string | null {
	const abs = resolve(root, relPath);
	if (abs !== root && !abs.startsWith(root + sep)) return null;
	return listTests(root).some((t) => t.file === abs && !t.parseError) ? abs : null;
}
