"""The single ``act`` tool — the grounding contract.

The planner must respond by calling ``act`` with exactly one action. To target an
on-screen element it sets ``element_ref`` to an element id from the ScreenState
it was given; the harness resolves that id to a box and clicks its center. The
planner NEVER provides pixel coordinates.

``strict: true`` guarantees the returned input validates against this schema, so
``ActDecision.model_validate`` can't choke on a malformed tool call. All
properties are listed in ``required`` (strict-mode requirement); irrelevant ones
are passed as ``null``.
"""

from __future__ import annotations

ACT_TOOL = {
    "name": "act",
    "description": (
        "Perform exactly ONE GUI action toward the current step's goal. To target "
        "an on-screen element, set element_ref to the `id` of an element from the "
        "ScreenState you were given (e.g. \"e3\"). NEVER provide pixel coordinates "
        "— the harness resolves element_ref to a bounding box and clicks its "
        "center. Use type=\"done\" when the step's goal is achieved, type=\"fail\" "
        "if it is impossible. For type=\"type\", you may include ${data.KEY} or "
        "${SECRET:NAME} placeholders in `text`; pass them through verbatim — never "
        "invent or guess secret values."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "One short sentence: why this action now.",
            },
            "type": {
                "type": "string",
                "enum": [
                    "click", "double_click", "right_click", "type",
                    "key", "scroll", "wait", "done", "fail",
                ],
            },
            "element_ref": {
                "type": ["string", "null"],
                "description": "id of a ScreenState element (required for clicks; "
                "optional for type to focus a field first).",
            },
            "text": {
                "type": ["string", "null"],
                "description": "Text to type (type only). May contain "
                "${data.KEY} / ${SECRET:NAME} placeholders.",
            },
            "keys": {
                "type": ["string", "null"],
                "description": 'Key or chord for type="key", e.g. "enter", '
                '"tab", "ctrl+a".',
            },
            "direction": {
                "type": ["string", "null"],
                "description": 'Scroll direction (scroll only): "up", "down", "left", or "right".',
            },
            "amount": {
                "type": ["integer", "null"],
                "description": "Scroll amount in clicks (scroll only).",
            },
            "seconds": {
                "type": ["number", "null"],
                "description": "Seconds to wait (wait only).",
            },
        },
        "required": [
            "reasoning", "type", "element_ref", "text",
            "keys", "direction", "amount", "seconds",
        ],
    },
}
