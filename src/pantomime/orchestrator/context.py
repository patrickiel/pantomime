"""Per-run context shared across the loop functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pantomime.orchestrator.cancel import CancelToken

if TYPE_CHECKING:
    from pantomime.driver.base import Driver
    from pantomime.perception.screen_state import ScreenState
    from pantomime.perception.grounder import Grounder
    from pantomime.reporting.recorder import DebugRecorder
    from pantomime.reporting.trace import TraceRecorder
    from pantomime.runtime.config import Settings
    from pantomime.runtime.secrets import SecretStore


@dataclass
class RunContext:
    data: dict[str, str]
    secrets: "SecretStore"
    settings: "Settings"
    driver: "Driver"
    client: Any  # anthropic client (None in dry-run with no key)
    variables: dict[str, str] = field(default_factory=dict)  # ${VAR:NAME} (from pantomime.yaml)
    grounder: "Grounder | None" = None
    trace: "TraceRecorder | None" = None
    recorder: "DebugRecorder | None" = None  # writes the step-by-step debugger DB
    dry_run: bool = False
    cancel: CancelToken = field(default_factory=CancelToken)  # no-op token unless a flag file is set
    usage: dict = field(default_factory=dict)
    _step_seq: int = 0

    def add_usage(self, u: dict, role: str) -> None:
        """Accumulate one model call's token usage under ``role`` (planner/judge).

        Tokens are kept per role (so each can be priced by its own model in
        ``Settings.cost_usd``) and also summed into the flat top-level totals the
        debugger's TokenUsage view reads. The two stay in lockstep here.
        """
        bucket = self.usage.setdefault(role, {})
        for k, v in (u or {}).items():
            bucket[k] = bucket.get(k, 0) + v
            self.usage[k] = self.usage.get(k, 0) + v

    def next_step_index(self) -> int:
        self._step_seq += 1
        return self._step_seq

    def rec(self, phase: str, **kw: Any) -> None:
        """Record one timeline event for the debugger (no-op without a recorder)."""
        if self.recorder is not None:
            self.recorder.event(phase, **kw)

    def capture_png(self, state: "ScreenState") -> bytes | None:
        """Grab + redact the current region as PNG bytes for the debugger timeline.

        No API cost — it's a local screen grab with sensitive boxes blacked out.
        Returns ``None`` when recording is off or capture fails.
        """
        if self.recorder is None or not self.recorder.capture:
            return None
        try:
            import io

            from pantomime.perception.redact import redact_image

            img = self.driver.screenshot()
            buf = io.BytesIO()
            redact_image(img, state.elements).save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None
