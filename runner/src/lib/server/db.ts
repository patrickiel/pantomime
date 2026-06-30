import { existsSync } from 'node:fs';
import { dirname } from 'node:path';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { ENSURE_SCHEMA } from './schema';

/** Directory holding a DB and its per-run artifact folders (screenshots, result.json). */
export function runsDir(dbFile: string): string {
	return dirname(dbFile);
}

/** Add a column to an existing table if it isn't already there (no-op otherwise). */
function addColumnIfMissing(sqlite: Database.Database, table: string, column: string, type: string): void {
	const cols = sqlite.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[];
	if (!cols.some((c) => c.name === column)) {
		sqlite.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${type}`);
	}
}

// One drizzle handle per database file (a project can have its own DB). Memoized
// so repeated requests for the same project reuse the open connection.
const _dbs = new Map<string, ReturnType<typeof drizzle>>();

export function getDb(dbFile: string) {
	const cached = _dbs.get(dbFile);
	if (cached) return cached;
	if (!existsSync(dirname(dbFile))) {
		throw new Error(
			`Database directory does not exist: ${dirname(dbFile)}. Run a Pantomime test in ` +
				`this project first (it creates the DB).`
		);
	}
	// Read-write so we can CREATE TABLE IF NOT EXISTS before any run has happened;
	// WAL lets us read while the Python runner is still writing a live run.
	const sqlite = new Database(dbFile);
	sqlite.pragma('journal_mode = WAL');
	sqlite.exec(ENSURE_SCHEMA);
	// `CREATE TABLE IF NOT EXISTS` never adds columns to a pre-existing table, so
	// bring older databases up to date with idempotent ALTERs (kept in lock-step
	// with recorder.py's migration).
	addColumnIfMissing(sqlite, 'runs', 'console', 'TEXT');
	const db = drizzle(sqlite);
	_dbs.set(dbFile, db);
	return db;
}
