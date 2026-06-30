"""Cooperative cancellation for a running test.

A run can't be interrupted mid-action safely, and Windows can't deliver SIGINT
reliably through the ``uv run`` → python chain the debugger spawns. So instead of
killing the process, the debugger writes a small *flag file* and the run polls for
it at safe points (between actions / steps) via :meth:`CancelToken.check`. When the
flag appears, ``check`` raises :class:`RunCanceled`, which unwinds the run; the
runner records a clean ``canceled`` status. Teardown is intentionally skipped —
"stop" means stop.

``RunCanceled`` subclasses ``BaseException`` (like ``KeyboardInterrupt``) so the
loop's broad ``except Exception`` handlers don't swallow it.
"""

from __future__ import annotations

from pathlib import Path


class RunCanceled(BaseException):
    """Raised at a safe point to unwind a run after a stop was requested."""


class CancelToken:
    """Cooperative cancel signalled by the existence of a flag file.

    A token with ``flag_file=None`` never cancels (the default for terminal runs,
    which still stop via Ctrl-C / KeyboardInterrupt). Once tripped it stays tripped,
    so a single missed-then-deleted flag can't un-cancel a run, and we avoid stat-ing
    the filesystem on every check after the first trip.
    """

    def __init__(self, flag_file: str | Path | None = None) -> None:
        self._flag = Path(flag_file) if flag_file else None
        self._tripped = False

    def cancelled(self) -> bool:
        if not self._tripped and self._flag is not None and self._flag.exists():
            self._tripped = True
        return self._tripped

    def check(self) -> None:
        """Raise :class:`RunCanceled` if a stop has been requested."""
        if self.cancelled():
            raise RunCanceled()
