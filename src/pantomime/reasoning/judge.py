"""The judge: a cheap, fast yes/no verdict from the reasoning model.

Used only for fuzzy, natural-language expectations — deterministic checks are
handled first in :mod:`pantomime.verification.verify`. The judge asks for a small
JSON verdict and parses it tolerantly. We do **not** use tools or a forced
``tool_choice``: the reasoning model runs with thinking on by default, which
rejects a forced tool choice (e.g. ``400: Thinking mode does not support this
tool_choice``). Text-only: the model reasons off the structured element list, so
no screenshot is sent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from pantomime.reasoning.prompts import SYSTEM_JUDGE

if TYPE_CHECKING:
    from pantomime.perception.screen_state import ScreenState
    from pantomime.runtime.config import Settings


class Verdict(BaseModel):
    passed: bool
    reasoning: str
    confidence: float
    usage: dict = {}  # token usage for this judge call (empty for deterministic checks)


def judge(client, settings: "Settings", expect: str, state: "ScreenState") -> Verdict:
    content: list[dict] = [
        {"type": "text", "text": f"Expectation:\n{expect}\n\nScreenState:"},
        {"type": "text", "text": json.dumps(state.to_prompt(), separators=(",", ":"))},
    ]

    resp = client.messages.create(
        model=settings.judge_model,
        max_tokens=1024,
        system=SYSTEM_JUDGE,
        messages=[{"role": "user", "content": content}],
    )

    verdict = _parse_verdict(resp)
    verdict.usage = _usage(resp)
    return verdict


def _parse_verdict(resp) -> Verdict:
    if getattr(resp, "stop_reason", None) == "refusal":
        return Verdict(passed=False, reasoning="judge refused", confidence=0.0)
    text = " ".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    data = _extract_json_object(text)
    if data is not None:
        try:
            return Verdict(passed=bool(data["passed"]), reasoning=str(data["reasoning"]), confidence=float(data["confidence"]))
        except Exception:
            pass
    return Verdict(passed=False, reasoning=f"unparseable judge output: {text[:200]}", confidence=0.0)


def _usage(resp) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
    }


def _extract_json_object(text: str) -> dict | None:
    """Pull a JSON object out of the reply (tolerating code fences / surrounding prose)."""
    import re

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None
