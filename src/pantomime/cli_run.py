"""Implementation of ``panto run``."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def run_tests(path: str, *, dry_run: bool = False, window: str | None = None) -> int:
    from pantomime.driver.region_select import RegionError
    from pantomime.orchestrator.cancel import RunCanceled
    from pantomime.orchestrator.runner import run_testcase
    from pantomime.parser.loader import ParseError, load_dir, load_testcase
    from pantomime.reporting.explain import explain_result
    from pantomime.runtime.config import ConfigError, Settings

    p = Path(path)
    try:
        testcases = load_dir(p) if p.is_dir() else [load_testcase(p)]
    except ParseError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if not testcases:
        print(f"No test files found under {p}", file=sys.stderr)
        return 2

    settings = Settings.load()
    # Models and their pricing live only in pantomime.yaml (no built-in default), so
    # fail fast with a clear message before touching the screen. --dry-run plans
    # without a model, so it skips this.
    if not dry_run:
        try:
            settings.require_runnable()
        except ConfigError as exc:
            print(f"CONFIG ERROR: {exc}", file=sys.stderr)
            return 2
    # The debugger requests a graceful stop by creating this file; the run polls
    # for it at safe points and unwinds (see orchestrator/cancel.py).
    cancel_file = os.environ.get("PANTO_CANCEL_FILE") or None
    all_passed = True
    for tc in testcases:
        try:
            result = run_testcase(tc, settings, dry_run=dry_run, window=window, cancel_file=cancel_file)
        except RunCanceled:
            print("Canceled.", file=sys.stderr)
            return 130
        except RegionError as exc:
            print(f"TARGET ERROR: {exc}", file=sys.stderr)
            return 2
        print(explain_result(result))
        print()
        all_passed = all_passed and result.passed
    return 0 if all_passed else 1
