"""Implementation of ``panto runner`` — launch the per-project web debugger.

Resolves the project from the current directory (the same walk-up ``Settings.load``
uses) and starts the SvelteKit runner scoped to that one project by exporting
``PANTO_PROJECT_ROOT``. There is no central registry: one runner instance per project.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

# Vite prints the bound address as `  ➜  Local:   http://localhost:5175/`. The
# requested port may be taken (e.g. another project's runner), in which case Vite
# auto-increments, so we read the port it actually bound rather than assuming ours.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_LOCAL_URL_RE = re.compile(r"(http://localhost:\d+)")


def _find_runner_dir() -> Path | None:
    """Locate the SvelteKit runner app (the directory holding its package.json).

    ``PANTO_RUNNER_DIR`` wins; otherwise walk up from this file looking for a
    ``runner/`` directory with a package.json (the repo layout: ``<repo>/runner``).
    """
    override = os.environ.get("PANTO_RUNNER_DIR")
    if override:
        cand = Path(override)
        return cand if (cand / "package.json").is_file() else None
    for directory in Path(__file__).resolve().parents:
        cand = directory / "runner"
        if (cand / "package.json").is_file():
            return cand
    return None


def run_runner(*, port: int = 5173, open_browser: bool = True) -> int:
    from pantomime.runtime.config import Settings, _find_config_file

    if _find_config_file(None) is None:
        print(
            "No Pantomime project here. cd into a project (a directory with "
            "config/pantomime.yaml) or run `panto init` first.",
            file=sys.stderr,
        )
        return 1
    root = Settings.load().project_root

    runner_dir = _find_runner_dir()
    if runner_dir is None:
        print(
            "Could not find the runner app. Set PANTO_RUNNER_DIR to the runner/ "
            "directory (the one with package.json).",
            file=sys.stderr,
        )
        return 1

    # `pnpm` is a .cmd shim on Windows; resolve its full path so Popen need not shell out.
    pnpm = os.environ.get("PANTO_PNPM") or shutil.which("pnpm") or "pnpm"
    env = {**os.environ, "PANTO_PROJECT_ROOT": str(root)}

    print(f"Pantomime runner for {root}", file=sys.stderr)

    proc = subprocess.Popen(
        [pnpm, "dev", "--", "--port", str(port)],
        cwd=str(runner_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        opened = False
        # Tee Vite's output to our stderr while watching for the line that reports
        # the port it actually bound; open the browser on that real URL, not ours.
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stderr.write(line)
            sys.stderr.flush()
            if open_browser and not opened:
                match = _LOCAL_URL_RE.search(_ANSI_RE.sub("", line))
                if match:
                    webbrowser.open(match.group(1))
                    opened = True
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130
