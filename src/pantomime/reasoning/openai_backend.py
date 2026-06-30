"""An OpenAI-backed client that quacks like the Anthropic one.

The planner and judge are written against the Anthropic Messages interface
(``client.messages.create(...)`` returning blocks + ``stop_reason`` + ``usage``).
Rather than branch that code per provider, this module wraps the OpenAI Chat
Completions API behind the *same* interface: it translates the request shapes the
reasoning code actually sends (system blocks, text / tool_result turns, a single
strict tool, adaptive thinking + effort) into OpenAI calls, and translates the
reply back into Anthropic-shaped blocks. So the rest of the codebase stays
provider-agnostic and untouched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

# Anthropic effort levels -> OpenAI reasoning_effort. xhigh/max collapse to the
# OpenAI ceiling; anything unrecognized falls back to a sensible middle.
_EFFORT = {"minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}

# OpenAI finish_reason -> Anthropic stop_reason.
_FINISH = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}


class OpenAIClient:
    """Drop-in stand-in for ``anthropic.Anthropic`` over the OpenAI SDK."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)

    @property
    def messages(self) -> "_Messages":
        return _Messages(self._client)


class _Messages:
    def __init__(self, client: Any):
        self._client = client

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: Any = None,
        thinking: Any = None,  # accepted for parity; OpenAI infers it from the model
        output_config: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **_ignored: Any,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _to_openai_messages(system, messages),
            "max_completion_tokens": max_tokens,
        }
        effort = (output_config or {}).get("effort")
        if effort:
            kwargs["reasoning_effort"] = _EFFORT.get(effort, "medium")
        if tools:
            kwargs["tools"] = [_to_openai_tool(t) for t in tools]
        resp = self._client.chat.completions.create(**kwargs)
        return _to_anthropic_response(resp)


# --- block helpers (handle both dict blocks and SimpleNamespace blocks) ------


def _btype(b: Any) -> str | None:
    return b.get("type") if isinstance(b, dict) else getattr(b, "type", None)


def _bget(b: Any, key: str, default: Any = None) -> Any:
    return b.get(key, default) if isinstance(b, dict) else getattr(b, key, default)


def _system_text(system: Any) -> str:
    if not system:
        return ""
    if isinstance(system, str):
        return system
    return "\n\n".join(_bget(b, "text", "") for b in system if _btype(b) == "text")


# --- request translation -----------------------------------------------------


def _to_openai_messages(system: Any, messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    sys_text = _system_text(system)
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for m in messages:
        content = m.get("content")
        if m.get("role") == "assistant":
            out.append(_assistant_to_openai(content))
        else:
            out.extend(_user_to_openai(content))
    return out


def _user_to_openai(content: Any) -> list[dict]:
    if isinstance(content, str):
        return [{"role": "user", "content": content}]
    # tool_result blocks become standalone tool messages (they must directly follow
    # the assistant tool call); remaining text blocks fold into one user message.
    tool_msgs: list[dict] = []
    texts: list[str] = []
    for b in content:
        if _btype(b) == "tool_result":
            tool_msgs.append({"role": "tool", "tool_call_id": _bget(b, "tool_use_id"), "content": str(_bget(b, "content", ""))})
        elif _btype(b) == "text":
            texts.append(_bget(b, "text", ""))
    if texts:
        tool_msgs.append({"role": "user", "content": "\n\n".join(texts)})
    return tool_msgs


def _assistant_to_openai(content: Any) -> dict:
    if isinstance(content, str):
        return {"role": "assistant", "content": content}
    texts: list[str] = []
    tool_calls: list[dict] = []
    for b in content:
        bt = _btype(b)
        if bt == "text":
            texts.append(_bget(b, "text", ""))
        elif bt == "tool_use":
            tool_calls.append(
                {
                    "id": _bget(b, "id"),
                    "type": "function",
                    "function": {"name": _bget(b, "name"), "arguments": json.dumps(_bget(b, "input") or {})},
                }
            )
    msg: dict[str, Any] = {"role": "assistant", "content": ("\n\n".join(texts) if texts else None)}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    elif msg["content"] is None:
        msg["content"] = ""  # OpenAI rejects a fully empty assistant turn
    return msg


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
            "strict": bool(tool.get("strict")),
        },
    }


# --- response translation ----------------------------------------------------


def _to_anthropic_response(resp: Any):
    choice = resp.choices[0]
    msg = choice.message
    blocks: list[Any] = []
    if getattr(msg, "content", None):
        blocks.append(SimpleNamespace(type="text", text=msg.content))
    for tc in getattr(msg, "tool_calls", None) or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except (ValueError, TypeError):
            args = {}
        blocks.append(SimpleNamespace(type="tool_use", id=tc.id, name=tc.function.name, input=args))
    return SimpleNamespace(
        content=blocks,
        stop_reason=_FINISH.get(getattr(choice, "finish_reason", None), "end_turn"),
        usage=_usage(getattr(resp, "usage", None)),
    )


def _usage(u: Any) -> SimpleNamespace:
    if u is None:
        return SimpleNamespace(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return SimpleNamespace(
        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
        output_tokens=getattr(u, "completion_tokens", 0) or 0,
        cache_read_input_tokens=cached,
        cache_creation_input_tokens=0,
    )
