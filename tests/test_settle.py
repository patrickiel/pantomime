"""Unit tests for frame-difference settle detection (no display needed)."""

from __future__ import annotations

from PIL import Image

from pantomime.perception.settle import frame_delta


def test_identical_frames_zero_delta():
    a = Image.new("RGB", (200, 100), (123, 45, 67))
    b = Image.new("RGB", (200, 100), (123, 45, 67))
    assert frame_delta(a, b) == 0.0


def test_full_black_to_white_is_max_delta():
    a = Image.new("RGB", (200, 100), (0, 0, 0))
    b = Image.new("RGB", (200, 100), (255, 255, 255))
    assert frame_delta(a, b) == 1.0


def test_small_localized_change_below_threshold():
    # A small bright patch on an otherwise-identical frame: visible to the
    # grayscale thumbnail but well under the settle threshold.
    a = Image.new("RGB", (200, 100), (100, 100, 100))
    b = a.copy()
    b.paste((180, 180, 180), (0, 0, 16, 16))
    delta = frame_delta(a, b)
    assert 0.0 < delta < 0.01


def test_handles_different_sizes():
    a = Image.new("RGB", (200, 100), (50, 50, 50))
    b = Image.new("RGB", (400, 300), (50, 50, 50))
    # downscaled to a common thumbnail, identical color -> zero
    assert frame_delta(a, b) == 0.0
