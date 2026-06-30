"""Unit tests for the reasoning client and the JSON-verdict judge (no network)."""

from __future__ import annotations

from types import SimpleNamespace

from pantomime.perception.screen_state import Element, ScreenState
from pantomime.reasoning.client import make_client
from pantomime.reasoning.judge import Verdict, judge
from pantomime.runtime.config import Settings


# --- defaults ------------------------------------------------------------


def test_models_have_no_builtin_default():
    # The YAML is the single source of truth: the code bakes in no provider, model id,
    # effort, grounding choice, or pricing, so an unconfigured Settings is all unset.
    s = Settings()
    assert s.provider == ""
    assert s.planner_model == ""
    assert s.judge_model == ""
    assert s.effort == ""
    assert s.grounding_enabled is None
    assert s.pricing == {}


# --- make_client ---------------------------------------------------------


def test_make_client_targets_deepseek(monkeypatch):
    import anthropic

    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(anthropic, "Anthropic", _fake_ctor)

    make_client(Settings(api_key="sk-deepseek"))
    assert captured["base_url"] == "https://api.deepseek.com/anthropic"
    assert captured["api_key"] == "sk-deepseek"


def test_make_client_base_url_override(monkeypatch):
    import anthropic

    captured = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: captured.update(kw))
    make_client(Settings(base_url="http://local-proxy/anthropic"))
    assert captured["base_url"] == "http://local-proxy/anthropic"


def test_make_client_selects_provider(monkeypatch):
    import anthropic

    captured = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: captured.update(kw))
    make_client(Settings(provider="anthropic"))
    assert captured["base_url"] == "https://api.anthropic.com"


# --- provider resolution -------------------------------------------------


def test_resolve_base_url_precedence():
    from pantomime.reasoning.providers import resolve_base_url

    # explicit base_url wins over the provider
    assert resolve_base_url("anthropic", "http://proxy/anthropic") == "http://proxy/anthropic"
    # known provider -> its endpoint
    assert resolve_base_url("anthropic", "") == "https://api.anthropic.com"
    # unknown/empty provider -> the default (deepseek)
    assert resolve_base_url(None, None) == "https://api.deepseek.com/anthropic"
    assert resolve_base_url("does-not-exist", None) == "https://api.deepseek.com/anthropic"
    # openai uses the SDK's own default base URL
    assert resolve_base_url("openai", None) is None


def test_provider_kind():
    from pantomime.reasoning.providers import provider_kind

    assert provider_kind("deepseek") == "anthropic"
    assert provider_kind("anthropic") == "anthropic"
    assert provider_kind("openai") == "openai"
    assert provider_kind(None) == "anthropic"  # default provider


# --- openai backend: same interface, translated under the hood -----------


class _FakeOpenAI:
    """Minimal stand-in for the OpenAI SDK client, capturing the request."""

    def __init__(self, reply):
        self._reply = reply
        self.captured = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.captured = kwargs
        return self._reply


def _openai_reply(*, content=None, tool_calls=None, finish="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=5, prompt_tokens_details=SimpleNamespace(cached_tokens=4))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)], usage=usage)


def _make_openai_client(reply):
    from pantomime.reasoning import openai_backend

    client = openai_backend.OpenAIClient.__new__(openai_backend.OpenAIClient)
    fake = _FakeOpenAI(reply)
    client._client = fake
    return client, fake


def test_openai_translates_planner_tool_call():
    from pantomime.reasoning.planner import plan
    from pantomime.reasoning.tools import ACT_TOOL

    tc = SimpleNamespace(id="call_1", function=SimpleNamespace(name="act", arguments='{"type":"click","element_ref":"e1","reasoning":"go"}'))
    client, fake = _make_openai_client(_openai_reply(tool_calls=[tc], finish="tool_calls"))

    messages = [{"role": "user", "content": [{"type": "text", "text": "STEP GOAL: click"}]}]
    pr = plan(client, Settings(provider="openai", planner_model="gpt-x"), messages)

    # request was translated to OpenAI shape
    assert fake.captured["model"] == "gpt-x"
    assert fake.captured["tools"][0]["function"]["name"] == "act"
    assert fake.captured["messages"][0]["role"] == "system"
    # reply was translated back to an Anthropic-shaped decision
    assert pr.decision.type == "click" and pr.decision.element_ref == "e1"
    assert pr.tool_use_id == "call_1"
    assert pr.usage["input_tokens"] == 12 and pr.usage["cache_read_input_tokens"] == 4


def test_openai_translates_judge_verdict():
    from pantomime.reasoning.judge import Verdict, judge

    client, _ = _make_openai_client(_openai_reply(content='{"passed": true, "reasoning": "ok", "confidence": 0.7}'))
    v = judge(client, Settings(provider="openai"), "expectation", _state_with_image())
    assert isinstance(v, Verdict) and v.passed is True and v.confidence == 0.7


def test_openai_history_roundtrip_to_messages():
    # An assistant tool_use turn followed by its tool_result must translate to a
    # valid OpenAI assistant(tool_calls) + tool message pair.
    from pantomime.reasoning.openai_backend import _to_openai_messages

    assistant = {"role": "assistant", "content": [SimpleNamespace(type="tool_use", id="call_9", name="act", input={"type": "click"})]}
    followup = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_9", "content": "clicked", "is_error": False}, {"type": "text", "text": "new state"}]}
    out = _to_openai_messages([{"type": "text", "text": "sys"}], [assistant, followup])

    assert out[0] == {"role": "system", "content": "sys"}
    assert out[1]["role"] == "assistant" and out[1]["tool_calls"][0]["id"] == "call_9"
    assert out[2] == {"role": "tool", "tool_call_id": "call_9", "content": "clicked"}
    assert out[3] == {"role": "user", "content": "new state"}


# --- judge: forced-tool verdict, text-only -------------------------------


def _state_with_image() -> ScreenState:
    return ScreenState(
        region=(0, 0, 400, 300),
        elements=[Element(id="e1", role="Edit", name="Username", text="demo_user", box=(10, 10, 200, 20))],
        image_b64="AAAA",  # present, but the judge must NOT send it (text-only)
    )


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.last_kwargs = None

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_kwargs = kwargs
            return SimpleNamespace(content=self.outer._content, stop_reason="end_turn")

    @property
    def messages(self):
        return self._Messages(self)


def _text(s: str):
    return SimpleNamespace(type="text", text=s)


def test_judge_parses_json_verdict():
    client = _FakeClient([_text('{"passed": true, "reasoning": "username shows demo_user", "confidence": 0.9}')])
    v = judge(client, Settings(), "the username field shows demo_user", _state_with_image())
    assert isinstance(v, Verdict)
    assert v.passed is True and v.confidence == 0.9


def test_judge_tolerates_fences_and_prose():
    # The reasoning model runs with thinking on; the final text may wrap the JSON.
    client = _FakeClient([_text('Sure:\n```json\n{"passed": false, "reasoning": "still on form", "confidence": 0.8}\n```')])
    v = judge(client, Settings(), "the user is logged in", _state_with_image())
    assert v.passed is False and v.confidence == 0.8


def test_judge_no_tools_no_image():
    # Forced tool_choice + thinking 400s on the reasoning model, so the judge uses
    # neither tools nor a screenshot (despite state.image_b64 being set).
    client = _FakeClient([_text('{"passed": true, "reasoning": "ok", "confidence": 1.0}')])
    judge(client, Settings(), "expectation", _state_with_image())
    kwargs = client.last_kwargs
    assert "tools" not in kwargs and "tool_choice" not in kwargs
    blocks = [b for m in kwargs["messages"] for b in m["content"]]
    assert all(b["type"] != "image" for b in blocks)


def test_judge_unparseable_falls_back():
    client = _FakeClient([_text("not json at all")])
    v = judge(client, Settings(), "expectation", _state_with_image())
    assert v.passed is False and "unparseable" in v.reasoning


# --- planner: malformed tool input is handled, not crashed ----------------


def _act_block(input_, id="call_x"):
    return SimpleNamespace(type="tool_use", name="act", input=input_, id=id)


def test_plan_malformed_tool_input_nudges_instead_of_crashing():
    from pantomime.reasoning.planner import plan

    # Model calls `act` with an empty object (missing the required `type`). This
    # must not raise — it should route to the loop's no-action/nudge path.
    client = _FakeClient([_act_block({})])
    pr = plan(client, Settings(), [{"role": "user", "content": [{"type": "text", "text": "go"}]}])
    assert pr.decision is None
    assert pr.refused is False
    assert pr.tool_use_id == "call_x"  # carried so the next turn can answer the tool_use


def test_plan_valid_tool_input_decodes():
    from pantomime.reasoning.planner import plan

    client = _FakeClient([_act_block({"type": "click", "element_ref": "e1", "reasoning": "go"})])
    pr = plan(client, Settings(), [{"role": "user", "content": [{"type": "text", "text": "go"}]}])
    assert pr.decision is not None and pr.decision.type == "click"
    assert pr.tool_use_id == "call_x"


def test_nudge_turn_answers_dangling_tool_use():
    from pantomime.orchestrator import history

    # No tool_use to answer -> plain text nudge.
    plain = history.nudge_turn()
    assert all(b["type"] == "text" for b in plain["content"])

    # A malformed tool_use must be answered with an error tool_result so the
    # next API call stays valid.
    answered = history.nudge_turn("call_x")
    tr = answered["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "call_x" and tr["is_error"] is True
