<p align="center">
  <img src="../design/icon.svg" alt="Pantomime" width="128" />
</p>

# Pantomime Runner

A **web app to launch and debug** Pantomime runs, built with **SvelteKit +
Tailwind + Drizzle (SQLite)**. Pick a test and hit **Run** (or **Dry-run**) to
start it from the browser and watch it play out live, then **Stop** it if needed.
Every run is recorded beat by beat, so you can also replay it one **Sense, Plan,
Act, Verify** step at a time, each with the (redacted) screenshot the loop saw and
the element boxes it grounded against.

## How the data gets here

Starting a run from the web app spawns `uv run panto run …` as a child process;
you can also run that command yourself in a terminal. Either way the Python
orchestrator records every beat to a SQLite database (by default
`runs/pantomime.db`) via
[`src/pantomime/reporting/recorder.py`](../src/pantomime/reporting/recorder.py).
Screenshots are stored as redacted PNG blobs (password fields blacked out). This
app reads that same database, opened in WAL mode, so you can watch a run **live**
while it is still executing.

## Run it

```bash
cd runner
pnpm install          # first time only (builds native better-sqlite3)
```

Then, from inside a project (a directory with `config/pantomime.yaml`):

```bash
panto runner          # serves http://localhost:5173 and opens it
```

`panto runner` resolves the project from the current directory and launches this
app scoped to it, passing the project root as `PANTO_PROJECT_ROOT`. One runner
instance serves one project. Run a test from the list, or open a past run and use
**↑/↓ (or j/k, ←/→)** to step through it.

The recorder runs by default; disable it with `PANTO_DEBUG=false` if you ever
want the old stderr-only behavior.

## Which project / database

The runner serves a single project, selected by `PANTO_PROJECT_ROOT` (set for you
by `panto runner`). From that root it derives the database as
`<root>/runs/pantomime.db`. You can override the database path directly with
`PANTO_DB`, and a bare `pnpm dev` with neither set falls back to `../runs/pantomime.db`
relative to `runner/` (matching the Python default):

```bash
# Python (writer)                 # Node (reader)
$env:PANTO_DB = "C:\path\to.db"   PANTO_DB=/path/to.db pnpm dev
```

## Layout

| Path | Role |
|---|---|
| `src/lib/server/schema.ts` | Drizzle schema (**keep in lock-step with `recorder.py`**) |
| `src/lib/server/db.ts` | Opens the SQLite file (WAL, ensures schema) |
| `src/lib/server/runner.ts` | Launches/stops `panto run` child processes; tracks live status |
| `src/routes/+page.svelte` | Test list with Run/Dry-run/Stop + recent-run history (auto-refreshes while live) |
| `src/routes/api/run/` | Starts a run; `api/run/stop/` stops it |
| `src/routes/runs/[id]/` | Step-by-step viewer: timeline + screenshot + detail |
| `src/routes/api/screenshot/[eventId]/` | Serves a step's PNG straight from the blob |

## Useful scripts

```bash
pnpm check        # svelte-check (types)
pnpm build        # production build (adapter-node)
pnpm db:studio    # browse the DB with Drizzle Studio
```
