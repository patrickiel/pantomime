"""Cooperative cancellation: the file-flag token, and the guarantee that the
SPAV loop bails on a stop request *before* doing any work (sensing/planning)."""

from __future__ import annotations

import pytest

from pantomime.driver.base import Driver
from pantomime.orchestrator.cancel import CancelToken, RunCanceled
from pantomime.orchestrator.context import RunContext
from pantomime.orchestrator.loop import run_assertion, run_goal
from pantomime.runtime.config import Settings


class ExplodingDriver(Driver):
    """Every method fails — proves the loop never touches the driver once canceled."""

    @property
    def region(self):
        return (0, 0, 100, 100)

    def screenshot(self):
        raise AssertionError("screenshot called after cancel — loop did not bail in time")

    def move(self, x, y):
        raise AssertionError("move called after cancel")

    def click(self, x, y):
        raise AssertionError("click called after cancel")

    def double_click(self, x, y):
        raise AssertionError("double_click called after cancel")

    def right_click(self, x, y):
        raise AssertionError("right_click called after cancel")

    def type(self, text):
        raise AssertionError("type called after cancel")

    def key(self, combo):
        raise AssertionError("key called after cancel")

    def scroll(self, direction, amount):
        raise AssertionError("scroll called after cancel")


class FakeSecrets:
    def get(self, name):
        return None


def _ctx(cancel: CancelToken) -> RunContext:
    # client is a sentinel: if the planner were reached it'd blow up, but cancel
    # should fire first.
    return RunContext(
        data={},
        secrets=FakeSecrets(),
        settings=Settings(),
        driver=ExplodingDriver(),
        client=object(),
        dry_run=False,
        cancel=cancel,
    )


# --- the token -------------------------------------------------------------


def test_token_is_noop_without_a_flag_file():
    tok = CancelToken(None)
    assert tok.cancelled() is False
    tok.check()  # must not raise


def test_token_trips_once_the_flag_file_appears(tmp_path):
    flag = tmp_path / "cancel.flag"
    tok = CancelToken(flag)
    assert tok.cancelled() is False
    tok.check()  # still nothing

    flag.write_text("")  # debugger requests a stop
    assert tok.cancelled() is True
    with pytest.raises(RunCanceled):
        tok.check()


def test_token_stays_tripped_even_if_the_flag_is_removed(tmp_path):
    flag = tmp_path / "cancel.flag"
    flag.write_text("")
    tok = CancelToken(flag)
    assert tok.cancelled() is True
    flag.unlink()  # a late cleanup must not un-cancel the run
    assert tok.cancelled() is True


def test_run_canceled_unwinds_past_broad_except_handlers():
    # Subclassing BaseException (not Exception) is load-bearing: the loop's
    # `except Exception` around actuation must NOT swallow a cancel.
    assert issubclass(RunCanceled, BaseException)
    assert not issubclass(RunCanceled, Exception)


# --- loop integration ------------------------------------------------------


def test_run_goal_bails_before_sensing_when_already_canceled(tmp_path):
    flag = tmp_path / "cancel.flag"
    flag.write_text("")  # stop requested before the goal even starts
    ctx = _ctx(CancelToken(flag))
    with pytest.raises(RunCanceled):
        run_goal(ctx, "click the button", "step", expect="a dialog opens", retries=2)


def test_run_assertion_bails_before_sensing_when_already_canceled(tmp_path):
    flag = tmp_path / "cancel.flag"
    flag.write_text("")
    ctx = _ctx(CancelToken(flag))
    with pytest.raises(RunCanceled):
        run_assertion(ctx, "the page shows 'Welcome'")


def test_dry_run_assertion_is_still_cancellable(tmp_path):
    # The dry-run early-return must not shadow the cancel check (regression).
    flag = tmp_path / "cancel.flag"
    flag.write_text("")
    ctx = _ctx(CancelToken(flag))
    ctx.dry_run = True
    with pytest.raises(RunCanceled):
        run_assertion(ctx, "the page shows 'Welcome'")


# --- runner: cancel skips teardown and records `canceled` -------------------


def test_cancel_skips_teardown_and_records_canceled(monkeypatch, tmp_path):
    """When a step is canceled, run_testcase must NOT run teardown and must record
    a clean `canceled` status (the debugger reads that status)."""
    import pantomime.driver.region as region_mod
    import pantomime.driver.region_select as region_select
    import pantomime.orchestrator.runner as runner_mod
    import pantomime.perception.grounder as grounder_mod
    import pantomime.reporting.recorder as recorder_mod
    from pantomime.orchestrator.runner import run_testcase
    from pantomime.runtime.config import Settings
    from pantomime.schema.models import TestCase

    # Stub the heavy perception/driver setup that runs before the first goal.
    monkeypatch.setattr(region_select, "select_region", lambda region, window: (0, 0, 100, 100))
    monkeypatch.setattr(grounder_mod, "build_grounder", lambda settings: None)
    monkeypatch.setattr(region_mod, "RegionDriver", lambda region: object())

    # The first goal (the step) is "interrupted"; teardown would be a second call.
    calls: list[str] = []

    def fake_run_goal(ctx, goal, kind, expect, retries):
        calls.append(kind)
        raise RunCanceled()

    monkeypatch.setattr(runner_mod, "run_goal", fake_run_goal)

    finished: dict[str, str] = {}

    class FakeRecorder:
        capture = False

        def start_run(self, **kw):
            return "run-id"

        def event(self, *a, **k):
            pass

        def finish_run(self, *, status, duration_s, usage):
            finished["status"] = status

        def close(self):
            pass

    monkeypatch.setattr(recorder_mod, "DebugRecorder", lambda *a, **k: FakeRecorder())

    tc = TestCase.model_validate(
        {"id": "cancel-me", "title": "x", "steps": [{"action": "do a thing"}], "teardown": ["close the app"]}
    )

    # client is a sentinel so run_testcase doesn't try to build a real API client.
    with pytest.raises(RunCanceled):
        run_testcase(tc, Settings(), client=object(), dry_run=False, runs_root=tmp_path)

    assert calls == ["step"]  # teardown's run_goal was never reached
    assert finished["status"] == "canceled"
