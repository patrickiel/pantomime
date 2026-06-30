"""Pydantic models for the Pantomime test-case schema.

A test case is plain text written in natural language. Two levels can be mixed:

* **Structured mode** — ``steps`` of ``action`` (+ optional ``expect``) pairs.
* **Prose mode** — a single free-text ``flow``.

The framework is **content-agnostic by design**: a test case carries no
``application``, ``platform``, or ``launch`` field. Launching is just a step
(``"double-click the 'MyApp' icon"``). Spatial targeting is optional: ``region`` —
a rectangle ``[x, y, w, h]`` — pins a fixed area, and ``window`` names the target
window by a title substring; omit both to use the foreground window / whole screen.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# A screen rectangle in absolute desktop pixels: (x, y, width, height).
Region = tuple[int, int, int, int]


# Deterministic action fields: the field name *is* the runtime action type and
# its value is that action's primary parameter. These skip the Sense/Plan LLM
# loop and run straight through the actuator (see orchestrator.loop.run_action).
DETERMINISTIC_FIELDS = ("key", "type", "wait", "scroll")


class Step(BaseModel):
    """One structured step.

    Either a free-text ``action`` (driven by the agentic Sense/Plan/Act loop) or
    exactly one *deterministic* field (``key``/``type``/``wait``/``scroll``),
    which runs mechanically with no model call. ``expect`` (+ optional ``region``)
    applies to both forms.
    """

    model_config = ConfigDict(extra="forbid")

    action: str | None = None

    # Deterministic, LLM-free actions. Exactly one of these OR `action`.
    key: str | None = None  # key combo, e.g. "Tab", "ctrl+a"
    type: str | None = None  # literal text typed into the focused field; supports ${data.x}/${SECRET:NAME}
    wait: float | None = None  # seconds to pause
    scroll: str | None = None  # direction: "up" | "down"
    amount: int | None = None  # scroll amount (optional companion to `scroll`)

    expect: str | None = None
    region: Region | None = None
    timeout_s: int = 20
    retries: int = 2

    @model_validator(mode="after")
    def _exactly_one_action(self) -> Step:
        present = [f for f in ("action", *DETERMINISTIC_FIELDS) if getattr(self, f) is not None]
        if not present:
            raise ValueError("step must define `action` or one of " + ", ".join(DETERMINISTIC_FIELDS))
        if len(present) > 1:
            raise ValueError("step must define only one of `action`, " + ", ".join(DETERMINISTIC_FIELDS) + f"; got {present}")
        if self.amount is not None and self.scroll is None:
            raise ValueError("`amount` is only valid alongside `scroll`")
        return self

    @property
    def is_deterministic(self) -> bool:
        return any(getattr(self, f) is not None for f in DETERMINISTIC_FIELDS)

    @property
    def deterministic_field(self) -> str | None:
        """The name of the set deterministic field (its value is the action type), or None."""
        return next((f for f in DETERMINISTIC_FIELDS if getattr(self, f) is not None), None)


class Assertion(BaseModel):
    """A final, hard check evaluated after all steps run.

    Accepts either a bare string (the natural-language expectation) or a
    mapping with ``expect`` (+ optional ``region``).
    """

    model_config = ConfigDict(extra="forbid")

    expect: str
    region: Region | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, value: object) -> object:
        if isinstance(value, str):
            return {"expect": value}
        return value


class TestCase(BaseModel):
    """A parsed, validated test case (the internal representation)."""

    model_config = ConfigDict(extra="forbid")
    __test__ = False  # not a pytest test class despite the name

    id: str
    title: str
    description: str | None = None
    tags: list[str] = []
    priority: str | None = None

    # The only thing the framework needs spatially. Omit for the whole screen.
    region: Region | None = None

    # Default target window (matched by title substring). Lets the runner UI / CLI
    # launch this test with one click. The CLI ``--window`` flag overrides this.
    window: str | None = None

    # Test data; values may contain ${data.x} and ${SECRET:NAME} references.
    data: dict[str, str] = {}

    preconditions: list[str] = []

    # Exactly one of `steps` (structured) or `flow` (prose) must be present.
    steps: list[Step] = []
    flow: str | None = None

    assertions: list[Assertion] = []
    teardown: list[str] = []

    @field_validator("region", mode="before")
    @classmethod
    def _region_length(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("region must be exactly [x, y, w, h]")
        return tuple(value)

    @model_validator(mode="after")
    def _steps_xor_flow(self) -> TestCase:
        if not self.steps and not self.flow:
            raise ValueError("test must define either `steps` or `flow`")
        if self.steps and self.flow:
            raise ValueError("test must define `steps` OR `flow`, not both")
        return self

    @property
    def is_prose(self) -> bool:
        return self.flow is not None
