"""Stability ("settle") detection via downscaled frame differencing.

Instead of fixed sleeps, we wait for the screen to stop changing: capture the
region, downscale to a small grayscale thumbnail, and compare consecutive
frames. ``frame_delta`` is the normalized mean absolute pixel difference in
``[0, 1]``; below ``settle_threshold`` the screen is considered still.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from pantomime.driver.base import Driver
    from pantomime.runtime.config import Settings

_THUMB = 64


def _thumb(img: "Image.Image") -> "Image.Image":
    return img.convert("L").resize((_THUMB, _THUMB))


def frame_delta(a: "Image.Image", b: "Image.Image") -> float:
    """Normalized mean absolute difference between two images, in [0, 1].

    Inputs are downscaled to a common grayscale thumbnail first, so images of
    different sizes can still be compared.
    """
    from PIL import ImageChops

    ta, tb = _thumb(a), _thumb(b)
    diff = ImageChops.difference(ta, tb)
    hist = diff.histogram()  # 256 bins for an "L" image
    total = sum(i * hist[i] for i in range(256))
    count = sum(hist) or 1
    return (total / count) / 255.0


def settle(driver: "Driver", settings: "Settings") -> bool:
    """Poll until two consecutive frames are stable, or the timeout elapses.

    Returns ``True`` if the screen settled, ``False`` on timeout (the caller can
    still proceed; ``stable=False`` is surfaced so the planner may choose to wait).
    """
    deadline = time.monotonic() + settings.settle_timeout_s
    prev = _thumb(driver.screenshot())
    streak = 0
    while time.monotonic() < deadline:
        time.sleep(settings.settle_interval_s)
        cur = _thumb(driver.screenshot())
        if frame_delta(prev, cur) < settings.settle_threshold:
            streak += 1
            if streak >= 2:
                return True
        else:
            streak = 0
        prev = cur
    return False
