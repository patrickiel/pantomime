"""Plain-language run summary — what was expected, what happened, likely cause.

Built from the per-step verdicts already collected (the judge's reasoning is
itself natural language), so this needs no extra API call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.orchestrator.results import TestResult


def explain_result(result: "TestResult") -> str:
    header = "PASSED" if result.passed else "FAILED"
    lines = [f"[{header}] {result.id} — {result.title}  ({result.duration_s:.1f}s)"]
    for s in result.steps:
        mark = "ok " if s.passed else "XX "
        lines.append(f"  {mark}{s.kind}: {s.goal}")
        if not s.passed:
            why = s.error or s.verdict_reasoning or "unknown"
            lines.append(f"       why: {why}")
            if s.verdict_reasoning and s.verdict_reasoning != s.error:
                lines.append(f"       observed: {s.verdict_reasoning}")
            if s.actions:
                last = s.actions[-1]
                lines.append(f"       last action: {last.type} {last.element_ref or ''} -> {last.outcome}")
    if result.usage:
        u = result.usage
        lines.append(
            f"  tokens: in={u.get('input_tokens', 0)} out={u.get('output_tokens', 0)} (est ${u.get('cost_usd', 0.0):.4f})"
        )
    return "\n".join(lines)
