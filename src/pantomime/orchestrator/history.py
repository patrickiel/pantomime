"""Build the message turns sent to the planner.

The screen state travels in the user turns (not stored separately), so message
alternation stays valid: the tool_result for the previous action and the *new*
screen state arrive together in one user turn.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.perception.screen_state import ScreenState


def _state_text(state: "ScreenState") -> str:
    return json.dumps(state.to_prompt(), separators=(",", ":"))


def first_user_turn(goal: str, state: "ScreenState", data_keys: list[str]) -> dict:
    # Text-only: the reasoning model grounds off the structured element list,
    # not a screenshot.
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"STEP GOAL: {goal}\n"
                f"Available data keys (reference as ${{data.KEY}}; values hidden): {sorted(data_keys)}\n"
                "Current SCREEN STATE (use element `id` values as element_ref):"
            ),
        },
        {"type": "text", "text": _state_text(state)},
    ]
    return {"role": "user", "content": content}


def followup_user_turn(
    tool_use_id: str,
    outcome_text: str,
    is_error: bool,
    state: "ScreenState",
    data_keys: list[str],
) -> dict:
    content: list[dict] = [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": outcome_text, "is_error": is_error},
        {"type": "text", "text": "Updated SCREEN STATE after your action:"},
        {"type": "text", "text": _state_text(state)},
    ]
    return {"role": "user", "content": content}


def nudge_turn(tool_use_id: str | None = None) -> dict:
    # When the model emitted an `act` tool_use that was malformed/incomplete, the
    # API requires the next user turn to answer it with a tool_result; carry one so
    # the conversation stays valid. When there was no tool_use at all, a plain
    # text nudge suffices.
    content: list[dict] = []
    if tool_use_id is not None:
        content.append(
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": "That `act` call was missing required fields (at least `type` is required). Call `act` again with one complete action.",
                "is_error": True,
            }
        )
    content.append({"type": "text", "text": "You must respond by calling the `act` tool with exactly one action."})
    return {"role": "user", "content": content}
