"""Assemble one uniform :class:`ScreenState` from all perception sources.

Priority: UIA first (precise, local). The CV + OCR grounder then augments it for
screens UIA can't read. All elements — whatever their source — are sorted
top-to-bottom/left-to-right and given final ``eN`` ids, so the grounding contract
is identical downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pantomime.perception.a11y.uia import enumerate_uia
from pantomime.perception.screen_state import Element, ScreenState
from pantomime.perception.settle import settle

if TYPE_CHECKING:
    from pantomime.driver.base import Driver
    from pantomime.perception.grounder import Grounder
    from pantomime.runtime.config import Settings


def sense(
    driver: "Driver",
    settings: "Settings",
    *,
    need_vision: bool = False,
    grounder: "Grounder | None" = None,
) -> ScreenState:
    region = driver.region
    elements: list[Element] = enumerate_uia(region)

    # When a grounder is configured it always augments UIA — UIA-only often sees
    # just window chrome (e.g. Tkinter exposes the title bar but not its text
    # fields), so the grounder fills in what UIA can't. `_merge` keeps every UIA
    # element and adds only the grounder's non-overlapping ones.
    if grounder is not None:
        try:
            from pantomime.perception.redact import redact_image

            img = driver.screenshot()
            grounded = grounder.parse(redact_image(img, elements), region)
            elements = _merge(elements, grounded)
        except Exception:
            pass  # fail soft: keep whatever UIA found

    elements = _assign_ids(_sort(elements))

    try:
        stable = settle(driver, settings)
    except Exception:
        stable = True

    image_b64 = None
    if need_vision:
        from pantomime.perception.redact import redact_and_encode

        image_b64 = redact_and_encode(driver.screenshot(), elements)

    from pantomime.runtime.dpi import scale_for_region

    return ScreenState(
        region=region,
        elements=elements,
        stable=stable,
        scale=scale_for_region(region),
        image_b64=image_b64,
    )


def _sort(elements: list[Element]) -> list[Element]:
    # top-to-bottom, then left-to-right by box origin
    return sorted(elements, key=lambda e: (e.box[1], e.box[0]))


def _assign_ids(elements: list[Element]) -> list[Element]:
    for i, el in enumerate(elements, 1):
        el.id = f"e{i}"
    return elements


def _merge(uia: list[Element], grounded: list[Element], iou_threshold: float = 0.6) -> list[Element]:
    """Keep all UIA elements; add grounded ones that aren't already a UIA element.

    A grounded element is dropped if it overlaps a UIA element (IoU) *or* sits
    mostly inside one (containment) — the latter catches OCR text that lands on a
    UIA-named control, e.g. the word "Sign in" inside the Sign-in button.
    """
    merged = list(uia)
    for g in grounded:
        if any(_iou(g.box, u.box) >= iou_threshold or _contained(g.box, u.box) >= 0.7 for u in uia):
            continue
        merged.append(g)
    return merged


def _contained(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> float:
    """Fraction of ``inner``'s area that falls within ``outer``."""
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    x1, y1 = max(ix, ox), max(iy, oy)
    x2, y2 = min(ix + iw, ox + ow), min(iy + ih, oy + oh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area = iw * ih
    return inter / area if area else 0.0


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0
