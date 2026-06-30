"""Two-stage verification.

1. **Deterministic fast path** (free, instant) for structured expectations:
   * ``contains:<text>`` — text present anywhere on screen
   * ``absent:<text>``   — text NOT present
   * ``prop:<Role>:<Name>`` — an element of that role (and name) exists
2. **LLM judge** (the reasoning model) for everything else (fuzzy natural language).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pantomime.reasoning.judge import Verdict, judge

if TYPE_CHECKING:
    from pantomime.perception.screen_state import ScreenState
    from pantomime.runtime.config import Settings


def verify(
    expect: str,
    state: "ScreenState",
    *,
    client=None,
    settings: "Settings | None" = None,
) -> Verdict:
    fast = deterministic(expect, state)
    if fast is not None:
        return fast

    if client is None or settings is None:
        return Verdict(passed=False, reasoning="no judge available for a fuzzy expectation", confidence=0.0)

    return judge(client, settings, expect, state)


def deterministic(expect: str, state: "ScreenState") -> Verdict | None:
    e = expect.strip()
    low = e.lower()

    if low.startswith("contains:"):
        needle = e[len("contains:"):].strip().lower()
        ok = needle in _haystack(state)
        return Verdict(passed=ok, reasoning=f"text {'present' if ok else 'absent'}: {needle!r}", confidence=1.0)

    if low.startswith("absent:"):
        needle = e[len("absent:"):].strip().lower()
        ok = needle not in _haystack(state)
        return Verdict(passed=ok, reasoning=f"text {'absent' if ok else 'present'}: {needle!r}", confidence=1.0)

    if low.startswith("prop:"):
        rest = e[len("prop:"):]
        role, _, name = rest.partition(":")
        role, name = role.strip().lower(), name.strip().lower()
        ok = any(
            el.role.lower() == role and (not name or name in el.name.lower())
            for el in state.elements
        )
        return Verdict(passed=ok, reasoning=f"element {role}/{name or '*'}: {'found' if ok else 'not found'}", confidence=1.0)

    return None  # fuzzy -> judge


def _haystack(state: "ScreenState") -> str:
    parts = [state.ocr_text]
    for el in state.elements:
        parts.append(el.name)
        if not el.is_password:
            parts.append(el.text)
    return " ".join(parts).lower()
