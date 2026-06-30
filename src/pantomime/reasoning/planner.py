"""The planner: ask the reasoning model for the next ``act`` action.

Runs on an Anthropic-compatible endpoint via the ``anthropic`` SDK. Uses adaptive
thinking + effort for good per-step decisions, a single ``act`` tool (so the reply
is a clean structured action), and prompt caching on the stable system prompt (a
real win on backends that support it, a harmless no-op otherwise). We do *not*
force ``tool_choice`` (incompatible with thinking); the single tool + explicit
instruction make the call reliable, and the loop nudges if the model ever replies
without one. Text-only: the model reasons off the structured element list, not a
screenshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from pantomime.reasoning.prompts import GROUNDING_RULES, SYSTEM_PLANNER
from pantomime.reasoning.tools import ACT_TOOL


class ActDecision(BaseModel):
    reasoning: str = ""
    type: str
    element_ref: str | None = None
    text: str | None = None
    keys: str | None = None
    direction: str | None = None
    amount: int | None = None
    seconds: float | None = None


@dataclass
class PlanResult:
    decision: ActDecision | None
    assistant_content: Any  # raw SDK content blocks, appended to history as-is
    tool_use_id: str | None
    usage: dict
    refused: bool = False


def system_blocks() -> list[dict]:
    return [
        {"type": "text", "text": SYSTEM_PLANNER},
        {"type": "text", "text": GROUNDING_RULES, "cache_control": {"type": "ephemeral"}},
    ]


def plan(client, settings, messages) -> PlanResult:
    resp = client.messages.create(
        model=settings.planner_model,
        max_tokens=settings.planner_max_tokens,
        system=system_blocks(),
        thinking={"type": "adaptive"},
        output_config={"effort": settings.effort},
        tools=[ACT_TOOL],
        messages=messages,
    )
    usage = _usage_dict(resp)

    if getattr(resp, "stop_reason", None) == "refusal":
        return PlanResult(None, resp.content, None, usage, refused=True)

    tool_block = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "act":
            tool_block = block
            break

    if tool_block is None:
        return PlanResult(None, resp.content, None, usage)

    try:
        decision = ActDecision.model_validate(dict(tool_block.input))
    except ValidationError:
        # The model called `act` with malformed/incomplete input (e.g. an empty
        # object missing `type`). Treat it like a no-action turn so the loop nudges
        # and retries; tool_block.id is carried so the next turn can answer the
        # dangling tool_use with an error tool_result.
        return PlanResult(None, resp.content, tool_block.id, usage)
    return PlanResult(decision, resp.content, tool_block.id, usage)


def _usage_dict(resp) -> dict:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
