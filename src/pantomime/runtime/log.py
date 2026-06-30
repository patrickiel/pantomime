"""Minimal progress logging to stderr.

A run makes several slow LLM calls; without feedback it looks hung. These
helpers print live progress to stderr (stdout stays clean for the final
summary). Verbosity is a process-global toggle set by the CLI.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from contextlib import contextmanager

_verbose = True


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = value


def log(message: str) -> None:
    if _verbose:
        print(message, file=sys.stderr, flush=True)


@contextmanager
def spinner(message: str, *, interval: float = 0.2):
    """Show a live spinner + elapsed-seconds ticker while a slow call blocks.

    Wraps any blocking operation (e.g. an OCR pass or a planner call) so the user
    sees it's working instead of a frozen line::

        with spinner("grounding: cv+ocr"):
            elements = grounder.parse(img, region)

    Updates a single stderr line in place and clears it on exit, so a regular
    ``log()`` afterward prints cleanly. A no-op when output is quiet.
    """
    if not _verbose:
        yield
        return

    stop = threading.Event()
    width = [0]  # last line length, for clearing without ANSI escapes

    def _spin() -> None:
        frames = itertools.cycle("|/-\\")
        start = time.monotonic()
        while not stop.wait(interval):
            line = f"{message} {next(frames)} {time.monotonic() - start:0.0f}s"
            width[0] = max(width[0], len(line))
            sys.stderr.write("\r" + line)
            sys.stderr.flush()

    thread = threading.Thread(target=_spin, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        if width[0]:  # overwrite the spinner line with blanks, then return to col 0
            sys.stderr.write("\r" + " " * width[0] + "\r")
            sys.stderr.flush()
