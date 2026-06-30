"""The Sense -> Plan -> Act -> Verify loop for one goal, with retries.

A *goal* is a precondition, a step, or a teardown line (assertions are
verify-only — see :func:`run_assertion`). The planner proposes one ``act`` per
turn; we execute it (resolving element ids to clicks and secrets to keystrokes),
re-sense, and continue until the planner says ``done``/``fail`` or the action
budget runs out, then verify the step's ``expect`` if it has one.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pantomime.orchestrator import history
from pantomime.orchestrator.results import ActionRecord, StepResult
from pantomime.parser.resolve import ResolutionError, resolve_refs
from pantomime.perception.screen_state import GroundingError, ScreenState
from pantomime.perception.sense import sense
from pantomime.reasoning.planner import ActDecision, plan
from pantomime.runtime.log import log
from pantomime.verification.verify import verify

if TYPE_CHECKING:
    from pantomime.orchestrator.context import RunContext
    from pantomime.schema.models import Step


@dataclass
class Outcome:
    text: str
    is_error: bool = False


# --- sensing ---------------------------------------------------------------


def _sense(ctx: "RunContext", *, need_vision: bool) -> "ScreenState":
    return sense(ctx.driver, ctx.settings, need_vision=need_vision, grounder=ctx.grounder)


# --- acting ----------------------------------------------------------------


def actuate(ctx: "RunContext", state: "ScreenState", d: ActDecision) -> Outcome:
    if ctx.dry_run:
        return Outcome(f"DRY-RUN: would {d.type} {d.element_ref or ''}".strip())
    try:
        t = d.type
        if t in ("click", "double_click", "right_click"):
            if not d.element_ref:
                return Outcome(f"{t} requires an element_ref", True)
            x, y = state.center(d.element_ref)
            getattr(ctx.driver, t)(x, y)
            return Outcome(f"{t} at element {d.element_ref}")
        if t == "type":
            if d.element_ref:
                x, y = state.center(d.element_ref)
                ctx.driver.click(x, y)
            plaintext = resolve_refs(d.text or "", ctx.data, ctx.secrets, ctx.variables)
            ctx.driver.type(plaintext)
            return Outcome(f"typed into {d.element_ref or 'focused field'}")  # never echo the text
        if t == "key":
            ctx.driver.key(d.keys or "")
            return Outcome(f"pressed key {d.keys!r}")
        if t == "scroll":
            ctx.driver.scroll(d.direction or "down", d.amount or 3)
            return Outcome(f"scrolled {d.direction} by {d.amount}")
        if t == "wait":
            time.sleep(min(d.seconds or 0.5, 5.0))
            return Outcome(f"waited {d.seconds}s")
        return Outcome(f"unknown action type {t!r}", True)
    except GroundingError as exc:
        return Outcome(str(exc), True)
    except ResolutionError as exc:
        return Outcome(f"data/secret resolution failed: {exc}", True)
    except Exception as exc:  # noqa: BLE001 - report any driver error back to the planner
        return Outcome(f"action error: {exc}", True)


def _record(d: ActDecision, outcome: str, is_error: bool = False) -> ActionRecord:
    return ActionRecord(
        type=d.type, element_ref=d.element_ref, reasoning=d.reasoning, outcome=outcome, is_error=is_error
    )


# --- goal execution --------------------------------------------------------


def run_goal(ctx: "RunContext", goal: str, kind: str, expect: str | None, retries: int) -> StepResult:
    ctx.cancel.check()  # stop requested? bail before any work (covers the dry-run planner call too)
    if ctx.dry_run:
        log(f"> {kind} (dry-run): {goal[:90]}")
        return _dry_run_goal(ctx, goal, kind)
    last: StepResult | None = None
    for attempt in range(1, retries + 2):
        ctx.cancel.check()  # stop requested? bail before another attempt
        suffix = f"  (attempt {attempt})" if attempt > 1 else ""
        log(f"> {kind}: {goal[:90]}{suffix}")
        ctx.rec("goal", kind=kind, goal=goal, attempt=attempt, title=f"{kind}: {goal[:90]}", message=suffix.strip() or None)
        last = _attempt(ctx, goal, kind, expect, attempt)
        if last.passed:
            log(f"  PASS{(' — ' + last.verdict_reasoning[:80]) if last.verdict_reasoning else ''}")
            return last
        log(f"  FAIL — {(last.error or last.verdict_reasoning or 'unknown')[:120]}")
    return last  # type: ignore[return-value]


# --- deterministic (LLM-free) actions --------------------------------------


def deterministic_decision(step: "Step") -> tuple[ActDecision, str]:
    """Map a deterministic ``Step`` to an ``ActDecision`` and a secret-safe label.

    The label never includes ``type`` text, which may contain secrets.
    """
    field = step.deterministic_field
    if field == "key":
        return ActDecision(type="key", keys=step.key), f"key: {step.key}"
    if field == "type":
        return ActDecision(type="type", text=step.type), "type into focused field"
    if field == "wait":
        return ActDecision(type="wait", seconds=step.wait), f"wait {step.wait}s"
    if field == "scroll":
        amount = step.amount if step.amount is not None else 3
        return ActDecision(type="scroll", direction=step.scroll, amount=amount), f"scroll {step.scroll} by {amount}"
    raise ValueError(f"step is not deterministic: {step!r}")  # pragma: no cover - guarded by caller


def run_action(ctx: "RunContext", d: ActDecision, kind: str, label: str, expect: str | None, retries: int) -> StepResult:
    """Execute one deterministic action with no Sense and no Plan call.

    Mirrors :func:`run_goal`'s retry/log/record shape, but the action is fixed up
    front so the model is never asked what to do. ``expect`` (if any) is still
    verified with a vision sense + judge via :func:`_verify_goal`.
    """
    ctx.cancel.check()
    if ctx.dry_run:
        log(f"> {kind} (dry-run): {label}")
        outcome = actuate(ctx, ScreenState(region=(0, 0, 0, 0)), d)
        ctx.rec("goal", kind=kind, goal=label, attempt=1, title=f"{kind}: {label}")
        return StepResult(
            kind=kind, goal=label, passed=True, actions=[_record(d, outcome.text)],
            verdict_reasoning="dry-run: deterministic action not executed",
        )
    last: StepResult | None = None
    for attempt in range(1, retries + 2):
        ctx.cancel.check()
        suffix = f"  (attempt {attempt})" if attempt > 1 else ""
        log(f"> {kind}: {label}{suffix}")
        ctx.rec("goal", kind=kind, goal=label, attempt=attempt, title=f"{kind}: {label}", message=suffix.strip() or None)
        # No element_ref / screen state needed: key/type(focused)/wait/scroll
        # never dereference `state`, so an empty ScreenState is enough.
        outcome = actuate(ctx, ScreenState(region=(0, 0, 0, 0)), d)
        log(f"    -> {outcome.text}{' [error]' if outcome.is_error else ''}")
        ctx.rec(
            "act", kind=kind, goal=label, attempt=attempt, title=label,
            action_type=d.type, outcome=outcome.text, is_error=outcome.is_error,
        )
        actions = [_record(d, outcome.text, outcome.is_error)]
        if outcome.is_error:
            last = StepResult(kind=kind, goal=label, passed=False, attempts=attempt, actions=actions, error=outcome.text)
            log(f"  FAIL — {outcome.text[:120]}")
            continue
        last = _verify_goal(ctx, kind, label, expect, attempt, actions, exhausted=False)
        if last.passed:
            log(f"  PASS{(' — ' + last.verdict_reasoning[:80]) if last.verdict_reasoning else ''}")
            return last
        log(f"  FAIL — {(last.error or last.verdict_reasoning or 'unknown')[:120]}")
    return last  # type: ignore[return-value]


def _attempt(ctx: "RunContext", goal: str, kind: str, expect: str | None, attempt: int) -> StepResult:
    actions: list[ActionRecord] = []
    data_keys = list(ctx.data.keys())
    log("  sensing screen…")
    state = _sense(ctx, need_vision=False)
    log(f"  ({len(state.elements)} elements, stable={state.stable})")
    ctx.rec(
        "sense", kind=kind, goal=goal, attempt=attempt,
        title=f"{len(state.elements)} elements",
        message=f"stable={state.stable}", screen_state=state.to_view(),
        screenshot=ctx.capture_png(state),
    )
    messages = [history.first_user_turn(goal, state, data_keys)]
    no_action = 0

    for _ in range(ctx.settings.max_actions_per_step):
        ctx.cancel.check()  # stop requested? bail before the next (slow) planner call
        log(f"  planning… (calling {ctx.settings.planner_model})")
        pr = plan(ctx.client, ctx.settings, messages)
        ctx.add_usage(pr.usage, "planner")

        if pr.refused:
            log("  planner refused")
            ctx.rec("plan", kind=kind, goal=goal, attempt=attempt, title="refused", is_error=True)
            return StepResult(kind=kind, goal=goal, passed=False, attempts=attempt, actions=actions, error="planner refused")

        messages.append({"role": "assistant", "content": pr.assistant_content})

        if pr.decision is None:
            no_action += 1
            log("  planner sent no usable action; nudging" if pr.tool_use_id is None else "  planner sent a malformed action; nudging")
            if no_action > 2:
                return StepResult(kind=kind, goal=goal, passed=False, attempts=attempt, actions=actions, error="planner did not call the act tool")
            messages.append(history.nudge_turn(pr.tool_use_id))
            continue

        d = pr.decision
        if d.type == "done":
            log("  act: done")
            ctx.rec("plan", kind=kind, goal=goal, attempt=attempt, title="done", reasoning=d.reasoning, action_type="done")
            actions.append(_record(d, "done"))
            return _verify_goal(ctx, kind, goal, expect, attempt, actions, exhausted=False)
        if d.type == "fail":
            log(f"  act: fail — {d.reasoning[:90]}")
            ctx.rec("plan", kind=kind, goal=goal, attempt=attempt, title="gave up", reasoning=d.reasoning, action_type="fail", is_error=True)
            actions.append(_record(d, f"planner gave up: {d.reasoning}", is_error=True))
            return StepResult(kind=kind, goal=goal, passed=False, attempts=attempt, actions=actions, error=f"planner gave up: {d.reasoning}")

        log(f"  act: {d.type} {d.element_ref or ''} — {d.reasoning[:70]}")
        ctx.rec(
            "plan", kind=kind, goal=goal, attempt=attempt,
            title=f"{d.type} {d.element_ref or ''}".strip(),
            reasoning=d.reasoning, action_type=d.type, element_ref=d.element_ref,
        )
        outcome = actuate(ctx, state, d)
        log(f"    -> {outcome.text}{' [error]' if outcome.is_error else ''}")
        ctx.rec(
            "act", kind=kind, goal=goal, attempt=attempt,
            title=f"{d.type} {d.element_ref or ''}".strip(),
            action_type=d.type, element_ref=d.element_ref, outcome=outcome.text, is_error=outcome.is_error,
        )
        actions.append(_record(d, outcome.text, outcome.is_error))
        state = _sense(ctx, need_vision=False)
        ctx.rec(
            "sense", kind=kind, goal=goal, attempt=attempt,
            title=f"{len(state.elements)} elements",
            message=f"after {d.type}; stable={state.stable}", screen_state=state.to_view(),
            screenshot=ctx.capture_png(state),
        )
        messages.append(history.followup_user_turn(pr.tool_use_id, outcome.text, outcome.is_error, state, data_keys))

    return _verify_goal(ctx, kind, goal, expect, attempt, actions, exhausted=True)


def _verify_goal(
    ctx: "RunContext", kind: str, goal: str, expect: str | None, attempt: int, actions: list[ActionRecord], exhausted: bool
) -> StepResult:
    if expect:
        log(f"  verifying: {expect[:80]}")
        vstate = _sense(ctx, need_vision=True)
        v = verify(expect, vstate, client=ctx.client, settings=ctx.settings)
        ctx.add_usage(v.usage, "judge")
        shot = _save_shot(ctx, vstate)
        ctx.rec(
            "verify", kind=kind, goal=goal, attempt=attempt,
            title=f"{'PASS' if v.passed else 'FAIL'}", message=expect,
            passed=v.passed, verdict_reasoning=v.reasoning, verdict_confidence=v.confidence,
            is_error=not v.passed, screen_state=vstate.to_view(), screenshot=_b64_to_bytes(vstate.image_b64),
        )
        return StepResult(
            kind=kind, goal=goal, passed=v.passed, attempts=attempt, actions=actions,
            verdict_reasoning=v.reasoning, verdict_confidence=v.confidence,
            error=None if v.passed else "expectation not met", screenshot=shot,
        )
    passed = not exhausted
    return StepResult(
        kind=kind, goal=goal, passed=passed, attempts=attempt, actions=actions,
        error=None if passed else "step did not complete within the action budget",
    )


def run_assertion(ctx: "RunContext", expect: str) -> StepResult:
    ctx.cancel.check()  # stop requested? bail before any work (mirrors run_goal)
    if ctx.dry_run:
        return StepResult(kind="assertion", goal=expect, passed=True, error=None, verdict_reasoning="dry-run: not evaluated")
    log(f"> assertion: {expect[:90]}")
    ctx.rec("goal", kind="assertion", goal=expect, attempt=1, title=f"assertion: {expect[:90]}")
    vstate = _sense(ctx, need_vision=True)
    v = verify(expect, vstate, client=ctx.client, settings=ctx.settings)
    ctx.add_usage(v.usage, "judge")
    shot = _save_shot(ctx, vstate)
    log(f"  {'PASS' if v.passed else 'FAIL'} — {v.reasoning[:90]}")
    ctx.rec(
        "verify", kind="assertion", goal=expect, attempt=1,
        title=f"{'PASS' if v.passed else 'FAIL'}", message=expect,
        passed=v.passed, verdict_reasoning=v.reasoning, verdict_confidence=v.confidence,
        is_error=not v.passed, screen_state=vstate.to_view(), screenshot=_b64_to_bytes(vstate.image_b64),
    )
    return StepResult(
        kind="assertion", goal=expect, passed=v.passed,
        verdict_reasoning=v.reasoning, verdict_confidence=v.confidence,
        error=None if v.passed else "assertion failed", screenshot=shot,
    )


def _dry_run_goal(ctx: "RunContext", goal: str, kind: str) -> StepResult:
    """Plan only the first action for the goal — no acting, no verifying."""
    data_keys = list(ctx.data.keys())
    state = _sense(ctx, need_vision=False)
    messages = [history.first_user_turn(goal, state, data_keys)]
    if ctx.client is None:
        return StepResult(kind=kind, goal=goal, passed=True, verdict_reasoning="dry-run: no client; sensed only", actions=[])
    pr = plan(ctx.client, ctx.settings, messages)
    ctx.add_usage(pr.usage, "planner")
    actions = [_record(pr.decision, "dry-run: planned, not executed")] if pr.decision else []
    return StepResult(kind=kind, goal=goal, passed=True, actions=actions, verdict_reasoning="dry-run: first action planned only")


def _save_shot(ctx: "RunContext", state: "ScreenState") -> str | None:
    if ctx.trace is None or not state.image_b64:
        return None
    return ctx.trace.save_png_b64(f"step{ctx.next_step_index()}", state.image_b64)


def _b64_to_bytes(b64: str | None) -> bytes | None:
    if not b64:
        return None
    try:
        return base64.standard_b64decode(b64)
    except Exception:
        return None
