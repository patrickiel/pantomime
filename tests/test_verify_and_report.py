"""Unit tests for the deterministic verifier and the reporting outputs."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pantomime.orchestrator.results import ActionRecord, StepResult, TestResult
from pantomime.perception.screen_state import Element, ScreenState
from pantomime.reporting.explain import explain_result
from pantomime.reporting.junit import build_junit
from pantomime.verification.verify import deterministic


def _state() -> ScreenState:
    return ScreenState(
        region=(0, 0, 400, 300),
        elements=[
            Element(id="e1", role="Text", name="Welcome, demo_user", text="Welcome, demo_user", box=(10, 10, 200, 20)),
            Element(id="e2", role="Button", name="Sign out", text="Sign out", box=(10, 40, 100, 30)),
        ],
    )


def test_contains_and_absent():
    s = _state()
    assert deterministic("contains:Welcome", s).passed is True
    assert deterministic("contains:Invalid credentials", s).passed is False
    assert deterministic("absent:Invalid credentials", s).passed is True
    assert deterministic("absent:Welcome", s).passed is False


def test_prop_role_name():
    s = _state()
    assert deterministic("prop:Button:Sign out", s).passed is True
    assert deterministic("prop:Button:Cancel", s).passed is False
    assert deterministic("prop:Edit", s).passed is False  # no Edit present


def test_fuzzy_returns_none():
    assert deterministic("the user appears to be logged in", _state()) is None


def _result(passed: bool) -> TestResult:
    return TestResult(
        id="login-happy-path",
        title="Login",
        passed=passed,
        steps=[
            StepResult(kind="step", goal="Type username", passed=True,
                       actions=[ActionRecord(type="type", element_ref="e1", outcome="typed into e1")]),
            StepResult(kind="step", goal="Click Sign in", passed=passed,
                       verdict_reasoning="welcome message visible" if passed else "still on login form",
                       error=None if passed else "expectation not met"),
        ],
        duration_s=1.23,
    )


def test_junit_is_valid_xml_with_failure():
    xml = build_junit(_result(False))
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    suite = root.find("testsuite")
    assert suite.get("failures") == "1"
    assert suite.find(".//failure") is not None


def test_explain_mentions_status_and_reason():
    text = explain_result(_result(False))
    assert "FAILED" in text
    assert "Click Sign in" in text
    assert "expectation not met" in text

    ok = explain_result(_result(True))
    assert "PASSED" in ok
