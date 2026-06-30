"""Durable, image-rich event recorder for the step-by-step web debugger.

The orchestrator normally narrates a run to stderr (see :mod:`pantomime.runtime.log`)
— ephemeral text that vanishes when the terminal scrolls. This recorder writes the
*same* Sense -> Plan -> Act -> Verify beats to a SQLite database instead, one row
per beat, each optionally carrying a redacted PNG of what the screen looked like.

The SvelteKit debugger (``runner/``) reads this database via Drizzle and replays a
run step by step, with screenshots. Schema here is kept in lock-step with the Drizzle
schema in ``runner/src/lib/server/schema.ts`` — change both together.

SQLite is opened in WAL mode so the debugger can read a run live while Python is
still writing it.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pantomime.perception.screen_state import ScreenState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    test_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,            -- running | passed | failed | canceled
    region      TEXT,                     -- json [x, y, w, h]
    dry_run     INTEGER NOT NULL DEFAULT 0,
    started_at  INTEGER NOT NULL,         -- epoch ms
    finished_at INTEGER,
    duration_s  REAL,
    usage       TEXT,                     -- json
    console     TEXT                      -- child stdout+stderr tail (written by the debugger runner)
);

CREATE TABLE IF NOT EXISTS events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT NOT NULL REFERENCES runs(id),
    seq                INTEGER NOT NULL,
    ts                 INTEGER NOT NULL,  -- epoch ms
    phase              TEXT NOT NULL,     -- goal | sense | plan | act | verify | info
    kind               TEXT,              -- precondition | step | assertion | teardown
    goal               TEXT,
    attempt            INTEGER,
    title              TEXT,              -- short headline for the timeline row
    message            TEXT,              -- detail text
    reasoning          TEXT,              -- planner reasoning
    action_type        TEXT,
    element_ref        TEXT,
    outcome            TEXT,
    is_error           INTEGER NOT NULL DEFAULT 0,
    passed             INTEGER,           -- nullable tri-state
    verdict_reasoning  TEXT,
    verdict_confidence REAL,
    screen_state       TEXT,              -- json: region/stable/elements
    screenshot         BLOB               -- redacted PNG bytes (optional)
);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
"""


def default_db_path(runs_dir: str | Path) -> Path:
    """Where the debugger database lives unless overridden by ``PANTO_DB``."""
    return Path(runs_dir) / "pantomime.db"


def _now_ms() -> int:
    return int(time.time() * 1000)


class DebugRecorder:
    """Writes run + event rows to SQLite. One instance per test run."""

    def __init__(self, db_path: str | Path, *, capture: bool = True) -> None:
        self.db_path = Path(db_path)
        self.capture = capture
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()
        self.run_id: str | None = None
        self._seq = 0

    def _migrate(self) -> None:
        """Bring an older database up to date. ``CREATE TABLE IF NOT EXISTS`` never
        adds columns to a pre-existing table, so apply idempotent ALTERs (kept in
        lock-step with the debugger's db.ts migration)."""
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "console" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN console TEXT")

    # --- run lifecycle -----------------------------------------------------

    def start_run(self, *, test_id: str, title: str, region: Any, dry_run: bool) -> str:
        # Any row still 'running' is an orphan from a previously killed process
        # (only one run ever writes this DB at a time) — reclaim it as canceled so
        # it stops showing as a live run in the debugger.
        self._conn.execute("UPDATE runs SET status = 'canceled' WHERE status = 'running'")

        self.run_id = uuid.uuid4().hex
        self._seq = 0
        self._conn.execute(
            "INSERT INTO runs (id, test_id, title, status, region, dry_run, started_at) "
            "VALUES (?, ?, ?, 'running', ?, ?, ?)",
            (self.run_id, test_id, title, json.dumps(list(region)) if region else None, int(dry_run), _now_ms()),
        )
        self._conn.commit()
        return self.run_id

    def finish_run(self, *, status: str, duration_s: float, usage: dict | None) -> None:
        if self.run_id is None:
            return
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, duration_s = ?, usage = ? WHERE id = ?",
            (status, _now_ms(), duration_s, json.dumps(usage or {}), self.run_id),
        )
        self._conn.commit()

    # --- events ------------------------------------------------------------

    def event(
        self,
        phase: str,
        *,
        kind: str | None = None,
        goal: str | None = None,
        attempt: int | None = None,
        title: str | None = None,
        message: str | None = None,
        reasoning: str | None = None,
        action_type: str | None = None,
        element_ref: str | None = None,
        outcome: str | None = None,
        is_error: bool = False,
        passed: bool | None = None,
        verdict_reasoning: str | None = None,
        verdict_confidence: float | None = None,
        screen_state: dict | None = None,
        screenshot: bytes | None = None,
    ) -> None:
        if self.run_id is None:
            return
        self._seq += 1
        self._conn.execute(
            "INSERT INTO events (run_id, seq, ts, phase, kind, goal, attempt, title, message, "
            "reasoning, action_type, element_ref, outcome, is_error, passed, verdict_reasoning, "
            "verdict_confidence, screen_state, screenshot) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.run_id,
                self._seq,
                _now_ms(),
                phase,
                kind,
                goal,
                attempt,
                title,
                message,
                reasoning,
                action_type,
                element_ref,
                outcome,
                int(is_error),
                None if passed is None else int(passed),
                verdict_reasoning,
                verdict_confidence,
                json.dumps(screen_state) if screen_state is not None else None,
                screenshot,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
