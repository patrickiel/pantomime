"""Run artifacts: per-step screenshots + a machine-readable result.json."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.orchestrator.results import TestResult


class TraceRecorder:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save_png_b64(self, name: str, b64: str) -> str:
        path = self.run_dir / f"{name}.png"
        try:
            path.write_bytes(base64.standard_b64decode(b64))
        except Exception:
            return ""
        return path.name

    def write_result(self, result: "TestResult") -> Path:
        path = self.run_dir / "result.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path
