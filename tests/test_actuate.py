"""Component tests for actuation: element_ref -> click center, secret injection,
and the guarantee that secret plaintext never appears in the recorded outcome.
No display or API needed — a fake driver records calls.
"""

from __future__ import annotations

from pantomime.driver.base import Driver
from pantomime.orchestrator.context import RunContext
from pantomime.orchestrator import loop
from pantomime.orchestrator.loop import actuate, deterministic_decision, run_action
from pantomime.perception.screen_state import Element, ScreenState
from pantomime.reasoning.planner import ActDecision
from pantomime.runtime.config import Settings
from pantomime.schema.models import Step


class FakeDriver(Driver):
    def __init__(self, region):
        self._region = region
        self.calls: list = []

    @property
    def region(self):
        return self._region

    def screenshot(self):
        from PIL import Image

        return Image.new("RGB", (self._region[2], self._region[3]), (255, 255, 255))

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def click(self, x, y):
        self.calls.append(("click", x, y))

    def double_click(self, x, y):
        self.calls.append(("double_click", x, y))

    def right_click(self, x, y):
        self.calls.append(("right_click", x, y))

    def type(self, text):
        self.calls.append(("type", text))

    def key(self, combo):
        self.calls.append(("key", combo))

    def scroll(self, direction, amount):
        self.calls.append(("scroll", direction, amount))


class FakeSecrets:
    def __init__(self, **values):
        self._values = values

    def get(self, name):
        return self._values.get(name)


def _state() -> ScreenState:
    return ScreenState(
        region=(100, 200, 400, 300),
        elements=[
            Element(id="e2", role="Edit", name="Password", text="", box=(20, 90, 200, 30), is_password=True),
            Element(id="e3", role="Button", name="Sign in", text="Sign in", box=(20, 140, 100, 36)),
        ],
    )


def _ctx(driver, data, secrets):
    return RunContext(
        data=data,
        secrets=secrets,
        settings=Settings(),
        driver=driver,
        client=None,
        grounder=None,
        dry_run=False,
    )


def test_click_resolves_element_center():
    driver = FakeDriver((100, 200, 400, 300))
    ctx = _ctx(driver, {}, FakeSecrets())
    out = actuate(ctx, _state(), ActDecision(type="click", element_ref="e3"))
    assert out.is_error is False
    # e3 box (20,140,100,36) -> center (70, 158), region-local
    assert driver.calls == [("click", 70, 158)]


def test_type_injects_secret_and_never_echoes_it():
    driver = FakeDriver((100, 200, 400, 300))
    data = {"password": "${SECRET:DEMO_PASSWORD}"}
    ctx = _ctx(driver, data, FakeSecrets(DEMO_PASSWORD="hunter2"))
    out = actuate(ctx, _state(), ActDecision(type="type", element_ref="e2", text="${data.password}"))
    # clicks the field to focus (e2 center = (120, 105)), then types the secret
    assert driver.calls == [("click", 120, 105), ("type", "hunter2")]
    # the secret must NOT appear in the outcome text (which gets logged/sent back)
    assert "hunter2" not in out.text
    assert out.is_error is False


def test_unknown_element_ref_is_error_not_crash():
    driver = FakeDriver((100, 200, 400, 300))
    ctx = _ctx(driver, {}, FakeSecrets())
    out = actuate(ctx, _state(), ActDecision(type="click", element_ref="e99"))
    assert out.is_error is True
    assert driver.calls == []


def test_dry_run_does_not_touch_driver():
    driver = FakeDriver((100, 200, 400, 300))
    ctx = RunContext(data={}, secrets=FakeSecrets(), settings=Settings(), driver=driver, client=None, dry_run=True)
    out = actuate(ctx, _state(), ActDecision(type="click", element_ref="e3"))
    assert driver.calls == []
    assert out.is_error is False
    assert "DRY-RUN" in out.text


def test_deterministic_decision_mapping():
    d, label = deterministic_decision(Step(key="Tab"))
    assert (d.type, d.keys) == ("key", "Tab")
    assert label == "key: Tab"
    d, label = deterministic_decision(Step(scroll="down", amount=5))
    assert (d.type, d.direction, d.amount) == ("scroll", "down", 5)
    # `type` label must not leak the text (it may contain secrets)
    d, label = deterministic_decision(Step(type="${data.password}"))
    assert d.type == "type" and d.text == "${data.password}"
    assert "password" not in label


def test_run_action_skips_plan_and_sense(monkeypatch):
    """A deterministic action runs straight through the driver with no LLM call."""

    def _boom(*a, **k):  # any planner/sense call here is a bug
        raise AssertionError("run_action must not sense or plan")

    monkeypatch.setattr(loop, "plan", _boom)
    monkeypatch.setattr(loop, "_sense", _boom)

    driver = FakeDriver((100, 200, 400, 300))
    ctx = _ctx(driver, {}, FakeSecrets())
    d, label = deterministic_decision(Step(key="Tab"))
    sr = run_action(ctx, d, "step", label, expect=None, retries=0)

    assert sr.passed is True
    assert driver.calls == [("key", "Tab")]
    assert len(sr.actions) == 1 and sr.actions[0].type == "key"
