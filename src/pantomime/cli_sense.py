"""Implementation of ``panto sense``.

Prints the current :class:`ScreenState` for a region (or the foreground window)
as compact JSON — the exact structure the planner receives.
"""

from __future__ import annotations

import json
import sys

from pantomime.schema.models import Region


def run_sense(region: "Region | None", *, window: str | None = None, need_vision: bool = False) -> int:
    from pantomime.driver.region import RegionDriver
    from pantomime.driver.region_select import RegionError, select_region
    from pantomime.perception.sense import sense
    from pantomime.perception.grounder import build_grounder
    from pantomime.runtime.config import Settings

    settings = Settings.load()
    try:
        resolved = select_region(region, window)
    except RegionError as exc:
        print(f"TARGET ERROR: {exc}", file=sys.stderr)
        return 2
    driver = RegionDriver(resolved)
    grounder = build_grounder(settings) if (need_vision or settings.grounding_enabled) else None

    state = sense(driver, settings, need_vision=need_vision, grounder=grounder)
    payload = state.to_prompt()
    # Surface each element's grounding source (uia/cv/ocr) for inspection. This is
    # the CLI view only; to_prompt() (the planner prompt) stays source-free so it
    # remains byte-stable for prompt caching.
    for el, src in zip(payload["elements"], state.elements):
        el["source"] = src.source
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n# {len(state.elements)} element(s), stable={state.stable}, region={resolved}")
    return 0
