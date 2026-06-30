/**
 * The single project this runner instance is scoped to.
 *
 * `panto runner` launches the runner with `PANTO_PROJECT_ROOT=<project root>`. Everything
 * else is derived here: the database is `<root>/runs/pantomime.db` (overridable with
 * `PANTO_DB`), and the display name comes from the project's `config/pantomime.yaml`
 * (`name:`, falling back to the directory name). One process serves one project — there is
 * no registry, cookie, or `?project=` switching.
 */

import { readFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { parse } from 'yaml';

export interface Project {
	/** Absolute project root. */
	root: string;
	/** `<root>/runs/pantomime.db`, or `PANTO_DB` when set. */
	db: string;
	/** Display name from config/pantomime.yaml, else the directory name. */
	name: string;
}

/** The project name from `<root>/config/pantomime.yaml`, or the directory name. */
function projectName(root: string): string {
	try {
		const doc = parse(readFileSync(join(root, 'config', 'pantomime.yaml'), 'utf8')) as Record<string, unknown>;
		const name = doc?.name;
		if (typeof name === 'string' && name.trim()) return name.trim();
	} catch {
		// no/invalid config/pantomime.yaml — fall back to the folder name
	}
	return basename(root);
}

function resolveRoot(): string {
	const fromEnv = process.env.PANTO_PROJECT_ROOT;
	if (fromEnv) return resolve(fromEnv);
	// Back-compat: derive the root from an explicit `PANTO_DB` (`<root>/runs/pantomime.db`).
	const db = process.env.PANTO_DB;
	if (db) return dirname(dirname(resolve(db)));
	// Bare `pnpm dev` with nothing set: assume the repo checkout's sibling project root
	// (matches runner/drizzle.config.ts).
	return resolve(process.cwd(), '..');
}

let cached: Project | null = null;

/** The project this runner serves. Resolved once per process. */
export function currentProject(): Project {
	if (cached) return cached;
	const root = resolveRoot();
	const db = process.env.PANTO_DB ? resolve(process.env.PANTO_DB) : join(root, 'runs', 'pantomime.db');
	cached = { root, db, name: projectName(root) };
	return cached;
}
