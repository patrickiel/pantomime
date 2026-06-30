"""Unit tests for the TestCase schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pantomime.parser.loader import ParseError, load_testcase
from pantomime.schema.models import Assertion, TestCase

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_structured_testcase_minimal():
    tc = TestCase.model_validate(
        {
            "id": "t1",
            "title": "x",
            "steps": [{"action": "Click 'OK'.", "expect": "A dialog closes."}],
        }
    )
    assert tc.id == "t1"
    assert tc.is_prose is False
    assert tc.steps[0].timeout_s == 20  # default


def test_prose_testcase():
    tc = TestCase.model_validate({"id": "t2", "title": "x", "flow": "Open the app and search."})
    assert tc.is_prose is True


def test_steps_xor_flow():
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "t3", "title": "x"})  # neither
    with pytest.raises(ValidationError):
        TestCase.model_validate(
            {"id": "t4", "title": "x", "flow": "do it", "steps": [{"action": "a"}]}
        )  # both


def test_assertion_string_coercion():
    tc = TestCase.model_validate(
        {
            "id": "t5",
            "title": "x",
            "steps": [{"action": "a"}],
            "assertions": ["absent:Error", {"expect": "logged in", "region": [0, 0, 10, 10]}],
        }
    )
    assert isinstance(tc.assertions[0], Assertion)
    assert tc.assertions[0].expect == "absent:Error"
    assert tc.assertions[1].region == (0, 0, 10, 10)


def test_region_validation():
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "t6", "title": "x", "flow": "f", "region": [0, 0, 10]})
    tc = TestCase.model_validate({"id": "t7", "title": "x", "flow": "f", "region": [1, 2, 3, 4]})
    assert tc.region == (1, 2, 3, 4)


def test_deterministic_step_fields():
    tc = TestCase.model_validate(
        {
            "id": "d1",
            "title": "x",
            "steps": [
                {"key": "Tab", "expect": "field shows it"},
                {"type": "hello"},
                {"wait": 0.5},
                {"scroll": "down", "amount": 5},
            ],
        }
    )
    key_step = tc.steps[0]
    assert key_step.is_deterministic is True
    assert key_step.deterministic_field == "key"
    assert tc.steps[1].deterministic_field == "type"
    assert tc.steps[3].amount == 5
    # a free-text action step is not deterministic
    action_step = TestCase.model_validate({"id": "d2", "title": "x", "steps": [{"action": "a"}]}).steps[0]
    assert action_step.is_deterministic is False
    assert action_step.deterministic_field is None


def test_step_requires_exactly_one_action():
    with pytest.raises(ValidationError):  # none
        TestCase.model_validate({"id": "d3", "title": "x", "steps": [{"expect": "x"}]})
    with pytest.raises(ValidationError):  # two action-bearing fields
        TestCase.model_validate({"id": "d4", "title": "x", "steps": [{"action": "a", "key": "Tab"}]})
    with pytest.raises(ValidationError):  # two deterministic fields
        TestCase.model_validate({"id": "d5", "title": "x", "steps": [{"key": "Tab", "wait": 1}]})


def test_amount_requires_scroll():
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "d6", "title": "x", "steps": [{"key": "Tab", "amount": 3}]})


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "t8", "title": "x", "flow": "f", "bogus": 1})


def test_window_field():
    # Optional: defaults to None, accepts a title-substring string.
    bare = TestCase.model_validate({"id": "t9", "title": "x", "flow": "f"})
    assert bare.window is None
    tc = TestCase.model_validate({"id": "t10", "title": "x", "flow": "f", "window": "Login"})
    assert tc.window == "Login"


def test_loads_example_login_yaml():
    tc = load_testcase(REPO_ROOT / "examples" / "login" / "tests" / "login.yaml")
    assert tc.id == "login-happy-path"
    assert tc.window == "Login"
    # The active step is the free-text, agentic login (the deterministic keystroke
    # version is kept as a commented-out alternative in the YAML).
    assert len(tc.steps) == 1
    assert tc.steps[0].action is not None
    assert not tc.steps[0].is_deterministic
    # The second assertion uses the LLM-free `contains:` fast path.
    assert tc.assertions[1].expect == "contains:You are logged in"


def test_loader_missing_file():
    with pytest.raises(ParseError):
        load_testcase(REPO_ROOT / "tests" / "does-not-exist.yaml")
