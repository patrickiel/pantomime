"""Result models for a test run (also what reporting serializes)."""

from __future__ import annotations

from pydantic import BaseModel


class ActionRecord(BaseModel):
    type: str
    element_ref: str | None = None
    reasoning: str = ""
    outcome: str = ""
    is_error: bool = False


class StepResult(BaseModel):
    __test__ = False  # not a pytest class

    kind: str  # precondition | step | assertion | teardown
    goal: str
    passed: bool
    attempts: int = 1
    actions: list[ActionRecord] = []
    verdict_reasoning: str = ""
    verdict_confidence: float = 1.0
    error: str | None = None
    screenshot: str | None = None  # filename under the run dir, if captured


class TestResult(BaseModel):
    __test__ = False

    id: str
    title: str
    passed: bool
    steps: list[StepResult] = []
    usage: dict = {}
    duration_s: float = 0.0
