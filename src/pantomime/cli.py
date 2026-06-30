"""``panto`` command-line entry point.

Subcommands:

* ``panto init [dir]`` — scaffold a starter test layout into your project.
* ``panto schema [-o path]`` — emit the JSON Schema for the test format
  (for editor validation); prints to stdout, or writes with ``-o``.
* ``panto validate <path>`` — parse + validate test file(s); print a
  secret-redacted summary.
* ``panto sense [--region x,y,w,h]`` — print the current ScreenState.
* ``panto run <path>`` — execute test(s) end to end.
* ``panto runner [--port N] [--no-open]`` — launch the web debugger for this project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pantomime.parser.loader import ParseError, load_dir, load_testcase
from pantomime.parser.resolve import redact_refs
from pantomime.schema.models import TestCase


def _parse_region(text: str) -> tuple[int, int, int, int]:
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must be 'x,y,w,h'")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"region must be four integers: {exc}") from exc
    return (x, y, w, h)


def _print_testcase(tc: TestCase, variables: dict[str, str] | None = None) -> None:
    """Print a human-readable, secret-redacted summary of a test case."""
    variables = variables or {}
    print(f"  id:        {tc.id}")
    print(f"  title:     {tc.title}")
    if tc.tags:
        print(f"  tags:      {', '.join(tc.tags)}")
    if tc.priority:
        print(f"  priority:  {tc.priority}")
    print(f"  region:    {tc.region if tc.region else 'whole screen / foreground window'}")
    if tc.window:
        print(f"  window:    {tc.window}")
    if tc.data:
        print("  data:")
        for key, value in tc.data.items():
            print(f"    {key}: {redact_refs(value, tc.data, variables)}")
    if tc.preconditions:
        print("  preconditions:")
        for pre in tc.preconditions:
            print(f"    - {redact_refs(pre, tc.data, variables)}")
    if tc.is_prose:
        print("  flow (prose):")
        print(f"    {redact_refs(tc.flow or '', tc.data, variables)}")
    else:
        print(f"  steps:     ({len(tc.steps)})")
        for i, step in enumerate(tc.steps, 1):
            if step.is_deterministic:
                field = step.deterministic_field
                # `type` text may hold secrets, so describe it without the value.
                desc = "type into focused field" if field == "type" else f"{field}: {getattr(step, field)}"
                print(f"    {i}. [{desc}]")
            else:
                print(f"    {i}. {redact_refs(step.action or '', tc.data, variables)}")
            if step.expect:
                print(f"       expect: {redact_refs(step.expect, tc.data, variables)}")
    if tc.assertions:
        print(f"  assertions: ({len(tc.assertions)})")
        for a in tc.assertions:
            print(f"    - {redact_refs(a.expect, tc.data, variables)}")
    if tc.teardown:
        print("  teardown:")
        for td in tc.teardown:
            print(f"    - {redact_refs(td, tc.data, variables)}")


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        testcases = load_dir(path) if path.is_dir() else [load_testcase(path)]
    except ParseError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if not testcases:
        print(f"No test files found under {path}", file=sys.stderr)
        return 1

    from pantomime.runtime.config import Settings

    settings = Settings.load()
    variables = settings.vars
    for tc in testcases:
        print(f"OK  {tc.id}")
        _print_testcase(tc, variables)
        print()
    print(f"Validated {len(testcases)} test case(s).")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    from pantomime.cli_init import run_init

    return run_init(args.dir, force=args.force, name=args.name)


def _cmd_runner(args: argparse.Namespace) -> int:
    from pantomime.cli_runner import run_runner

    return run_runner(port=args.port, open_browser=not args.no_open)


def _cmd_schema(args: argparse.Namespace) -> int:
    from pantomime.schema.export import render_config_json_schema, render_json_schema

    text = render_config_json_schema() if args.config else render_json_schema()
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote: {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def _cmd_sense(args: argparse.Namespace) -> int:
    from pantomime.cli_sense import run_sense

    return run_sense(args.region, window=args.window, need_vision=args.vision)


def _cmd_run(args: argparse.Namespace) -> int:
    from pantomime.cli_run import run_tests

    return run_tests(args.path, dry_run=args.dry_run, window=args.window)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="panto", description="Pantomime — NL-driven GUI testing.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a starter test layout into your project.")
    p_init.add_argument(
        "dir", nargs="?", default="tests", help="Directory for the example test (default: tests)."
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")
    p_init.add_argument(
        "--name", default=None, help="Project name (else you're prompted; defaults to the directory name)."
    )
    p_init.set_defaults(func=_cmd_init)

    p_runner = sub.add_parser("runner", help="Launch the web debugger for the current project.")
    p_runner.add_argument("--port", type=int, default=5173, help="Port to serve on (default: 5173).")
    p_runner.add_argument("--no-open", action="store_true", help="Don't open a browser tab.")
    p_runner.set_defaults(func=_cmd_runner)

    p_schema = sub.add_parser(
        "schema", help="Emit a JSON Schema (test format, or --config for pantomime.yaml)."
    )
    p_schema.add_argument(
        "-o",
        "--output",
        default=None,
        help="Write to this path instead of stdout (e.g. schemas/v1/testcase.schema.json).",
    )
    p_schema.add_argument(
        "--config",
        action="store_true",
        help="Emit the schema for pantomime.yaml (the project config) instead of the test format.",
    )
    p_schema.set_defaults(func=_cmd_schema)

    p_validate = sub.add_parser("validate", help="Parse and validate test file(s).")
    p_validate.add_argument("path", help="A .yaml test file or a directory of them.")
    p_validate.set_defaults(func=_cmd_validate)

    p_sense = sub.add_parser("sense", help="Print the current ScreenState.")
    p_sense.add_argument("--region", type=_parse_region, default=None, help="x,y,w,h (default: foreground window).")
    p_sense.add_argument("--window", default=None, help="Target a window whose title contains this text.")
    p_sense.add_argument("--vision", action="store_true", help="Attach a screenshot to the ScreenState.")
    p_sense.set_defaults(func=_cmd_sense)

    p_run = sub.add_parser("run", help="Execute test(s) end to end.")
    p_run.add_argument("path", help="A .yaml test file or a directory of them.")
    p_run.add_argument(
        "--window",
        default=None,
        help="Target a window whose title contains this text (e.g. 'Login'). Overrides the test's `window:` field.",
    )
    p_run.add_argument("--dry-run", action="store_true", help="Plan without acting (no clicks/typing).")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Load config from two .env files (project root or any parent) so values
    # don't have to be exported every shell:
    #   .env        runner-host config (models, pricing, grounding, debug)
    #   .env.local  the user's own values (API key, PANTO_VAR_*, PANTO_SECRET_*)
    # Precedence: real shell env > .env.local > .env (override=False never
    # clobbers an already-set var, so loading .env.local first wins over .env).
    try:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv(".env.local", usecwd=True), override=False)
        load_dotenv(find_dotenv(usecwd=True), override=False)
    except Exception:
        pass

    # The Windows console default codec (cp1252) can't encode UI text that
    # contains arbitrary Unicode (element names, glyphs). Force UTF-8 output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    # Declare DPI awareness before any GUI library initializes, so UIA, mss, and
    # pyautogui all report physical pixels (no-op for `validate`).
    if args.command in {"sense", "run"}:
        from pantomime.runtime.dpi import ensure_dpi_aware

        ensure_dpi_aware()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
