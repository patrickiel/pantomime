"""Unit tests for the RegionDriver coordinate math and capture.

The math tests are pure (no display); the screenshot test actually captures a
small region and is skipped if capture is unavailable. No clicks are performed
here — real input is exercised only by the end-to-end run.
"""

from __future__ import annotations

import pytest

from pantomime.driver.base import OutOfRegionError
from pantomime.driver.region import RegionDriver


def test_to_abs_adds_origin():
    d = RegionDriver((100, 200, 300, 400))
    assert d._to_abs(0, 0) == (100, 200)
    assert d._to_abs(10, 20) == (110, 220)
    # bottom-right corner is (w-1, h-1) local
    assert d._to_abs(299, 399) == (399, 599)


def test_clamp_default_clamps_into_bounds():
    d = RegionDriver((0, 0, 100, 50))
    assert d._to_abs(-5, -5) == (0, 0)
    assert d._to_abs(999, 999) == (99, 49)


def test_strict_rejects_out_of_region():
    d = RegionDriver((0, 0, 100, 50), strict=True)
    with pytest.raises(OutOfRegionError):
        d._to_abs(150, 10)
    with pytest.raises(OutOfRegionError):
        d._to_abs(10, -1)
    # in-bounds still works
    assert d._to_abs(99, 49) == (99, 49)


def test_zero_size_region_rejected():
    with pytest.raises(ValueError):
        RegionDriver((0, 0, 0, 100))
    with pytest.raises(ValueError):
        RegionDriver((0, 0, 100, 0))


def test_region_offset_with_nonzero_origin():
    d = RegionDriver((640, 360, 200, 100))
    # local center -> absolute center
    assert d._to_abs(100, 50) == (740, 410)


def test_screenshot_capture_smoke():
    """Capture a tiny region from the top-left of the desktop (read-only)."""
    pytest.importorskip("mss")
    pytest.importorskip("PIL")
    try:
        d = RegionDriver((0, 0, 32, 16))
        img = d.screenshot()
    except Exception as exc:  # headless/CI without a display
        pytest.skip(f"screen capture unavailable: {exc}")
    assert img.size == (32, 16)
    assert img.mode == "RGB"
