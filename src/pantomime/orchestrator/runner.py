"""Run a whole test case: preconditions -> steps (or prose flow) -> assertions
-> teardown (teardown always runs). Writes result.json + junit.xml + shots.

Goal text sent to the planner is **redacted** (``${data.x}`` resolved for
non-secrets, secrets masked) — the planner references ``${data.KEY}`` placeholders and
the actuation layer substitutes real values.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from pantomime.orchestrator.cancel import CancelToken, RunCanceled
from pantomime.orchestrator.context import RunContext
from pantomime.orchestrator.loop import deterministic_decision, run_action, run_assertion, run_goal
from pantomime.orchestrator.results import TestResult
from pantomime.parser.resolve import redact_refs
from pantomime.reporting.junit import write_junit
from pantomime.reporting.trace import TraceRecorder

if TYPE_CHECKING:
    from pantomime.runtime.config import Settings
    from pantomime.schema.models import TestCase


def run_testcase(
    tc: "TestCase",
    settings: "Settings",
    *,
    client=None,
    dry_run: bool = False,
    window: str | None = None,
    runs_root: str | Path | None = None,
    cancel_file: str | Path | None = None,
) -> TestResult:
    from pantomime.driver.region import RegionDriver
    from pantomime.driver.region_select import select_region
    from pantomime.perception.grounder import build_grounder
    from pantomime.runtime.log import log
    from pantomime.runtime.secrets import SecretStore

    # CLI --window overrides the test's own `window:` field; either may be None.
    effective_window = window or tc.window
    region = select_region(tc.region, effective_window)
    if effective_window:
        from pantomime.driver.region_select import focus_window

        focus_window(effective_window)  # best-effort: bring the target app to the front
    if tc.region is None and not effective_window:
        log(
            "WARNING: no region/window specified — targeting the FOREGROUND window "
            f"({region}), which is likely this terminal. Use --window <title> to "
            "target your app (e.g. --window Login)."
        )
    log(f"=== {tc.id}: {tc.title} | region={region} ===")
    driver = RegionDriver(region)
    grounder = build_grounder(settings)
    if client is None and not dry_run:
        from pantomime.reasoning.client import make_client

        settings.require_runnable()  # fail fast if the YAML omits models or their pricing
        client = make_client(settings)

    # Timestamp + short random suffix so two runs of the same test in the same second
    # (e.g. a future parallel runner) never share a dir and overwrite each other's
    # artifacts. The debugger keys off the DB run id, not this path, so the format is free.
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = Path(runs_root or settings.resolved_runs_dir()) / tc.id / stamp
    trace = TraceRecorder(run_dir)

    recorder = None
    if settings.debug_record:
        try:
            from pantomime.reporting.recorder import DebugRecorder

            recorder = DebugRecorder(settings.resolved_db_path())
            recorder.start_run(test_id=tc.id, title=tc.title, region=region, dry_run=dry_run)
            log(f"recording debugger timeline -> {settings.resolved_db_path()}")
        except Exception as exc:  # never let recording break a run
            log(f"WARNING: could not open debugger database: {exc}")
            recorder = None

    ctx = RunContext(
        data=dict(tc.data),
        secrets=SecretStore(settings.secrets),
        settings=settings,
        driver=driver,
        client=client,
        variables=dict(settings.vars),
        grounder=grounder,
        trace=trace,
        recorder=recorder,
        dry_run=dry_run,
        cancel=CancelToken(cancel_file),
    )

    result = TestResult(id=tc.id, title=tc.title, passed=True)
    start = time.monotonic()
    status = "failed"
    try:
        for pre in tc.preconditions:
            sr = run_goal(ctx, redact_refs(pre, ctx.data, ctx.variables), "precondition", None, retries=1)
            result.steps.append(sr)
            if not sr.passed:
                result.passed = False
                break

        if result.passed:
            if tc.is_prose:
                sr = run_goal(ctx, redact_refs(tc.flow or "", ctx.data, ctx.variables), "step", None, retries=2)
                result.steps.append(sr)
                result.passed = sr.passed
            else:
                for step in tc.steps:
                    expect = redact_refs(step.expect, ctx.data, ctx.variables) if step.expect else None
                    if step.is_deterministic:
                        d, label = deterministic_decision(step)
                        sr = run_action(ctx, d, "step", label, expect, retries=step.retries)
                    else:
                        sr = run_goal(
                            ctx, redact_refs(step.action or "", ctx.data, ctx.variables), "step", expect, retries=step.retries
                        )
                    result.steps.append(sr)
                    if not sr.passed:
                        result.passed = False
                        break

        if result.passed:
            for assertion in tc.assertions:
                sr = run_assertion(ctx, redact_refs(assertion.expect, ctx.data, ctx.variables))
                result.steps.append(sr)
                if not sr.passed:
                    result.passed = False

        for td in tc.teardown:  # always runs
            result.steps.append(run_goal(ctx, redact_refs(td, ctx.data, ctx.variables), "teardown", None, retries=0))

        ctx.usage["cost_usd"] = round(settings.cost_usd(ctx.usage), 6)
        result.usage = ctx.usage
        result.duration_s = time.monotonic() - start
        status = "passed" if result.passed else "failed"
        trace.write_result(result)
        write_junit(result, run_dir / "junit.xml")
        return result
    except BaseException as exc:  # cancel / Ctrl-C / crash: never leave the run stuck as "running"
        result.passed = False
        result.duration_s = time.monotonic() - start
        canceled = isinstance(exc, (RunCanceled, KeyboardInterrupt, SystemExit))
        status = "canceled" if canceled else "failed"
        if canceled:
            log("=== canceled (stop requested) ===")
            ctx.rec("info", title="Canceled", message="Stopped by user.", is_error=True)
        raise
    finally:
        if recorder is not None:
            try:
                ctx.usage["cost_usd"] = round(settings.cost_usd(ctx.usage), 6)
                recorder.finish_run(
                    status=status,
                    duration_s=time.monotonic() - start,
                    usage=ctx.usage,
                )
            except Exception as exc:  # recording must never mask the real outcome
                # Leaves the row 'running'; the debugger reclaims it as canceled/failed.
                log(f"WARNING: could not record final status ({status}): {exc}")
            recorder.close()
