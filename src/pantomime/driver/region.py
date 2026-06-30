"""The screen-region driver: capture with ``mss``, input with ``pyautogui``.

This is the **single place** where region-local coordinates become absolute
desktop pixels (:meth:`_to_abs`). Everything upstream — perception, grounding,
the planner — works in region-local space; the region origin is added here and
nowhere else, so there is no chance of double-applying or drifting the offset.

``pyautogui`` and ``mss`` are imported lazily so the coordinate math can be unit
tested without a display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pantomime.driver.base import Driver, OutOfRegionError

if TYPE_CHECKING:
    from PIL import Image

    from pantomime.schema.models import Region


class RegionDriver(Driver):
    def __init__(self, region: "Region", *, strict: bool = False, pause: float = 0.05) -> None:
        x, y, w, h = region
        if w <= 0 or h <= 0:
            raise ValueError(f"region width/height must be positive: {region!r}")
        self._region: Region = (int(x), int(y), int(w), int(h))
        self.strict = strict
        self.pause = pause
        self._pg_configured = False

    @property
    def region(self) -> "Region":
        return self._region

    # --- the one and only coordinate conversion site -------------------------

    def _clamp(self, value: int, hi: int, axis: str) -> int:
        if value < 0 or value > hi:
            if self.strict:
                raise OutOfRegionError(
                    f"{axis}={value} is outside [0, {hi}] of region {self._region}"
                )
            return 0 if value < 0 else hi
        return value

    def _to_abs(self, x: int, y: int) -> tuple[int, int]:
        rx, ry, rw, rh = self._region
        cx = self._clamp(int(x), rw - 1, "x")
        cy = self._clamp(int(y), rh - 1, "y")
        return rx + cx, ry + cy

    # --- input backend (pyautogui) -------------------------------------------

    def _pg(self):
        import pyautogui

        if not self._pg_configured:
            pyautogui.FAILSAFE = True  # slam pointer to a corner to abort
            pyautogui.PAUSE = self.pause
            self._pg_configured = True
        return pyautogui

    # --- capture --------------------------------------------------------------

    def screenshot(self) -> "Image.Image":
        import mss
        from PIL import Image

        rx, ry, rw, rh = self._region
        with mss.MSS() as sct:
            raw = sct.grab({"left": rx, "top": ry, "width": rw, "height": rh})
        return Image.frombytes("RGB", raw.size, raw.rgb)

    # --- actions (all region-local) ------------------------------------------

    def move(self, x: int, y: int) -> None:
        ax, ay = self._to_abs(x, y)
        self._pg().moveTo(ax, ay)

    def click(self, x: int, y: int) -> None:
        ax, ay = self._to_abs(x, y)
        self._pg().click(ax, ay)

    def double_click(self, x: int, y: int) -> None:
        ax, ay = self._to_abs(x, y)
        self._pg().doubleClick(ax, ay)

    def right_click(self, x: int, y: int) -> None:
        ax, ay = self._to_abs(x, y)
        self._pg().click(ax, ay, button="right")

    def type(self, text: str) -> None:
        # pyautogui.write handles standard printable characters; keystrokes go
        # to whatever window currently has focus (click first to focus a field).
        self._pg().write(text, interval=0.02)

    def key(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        if not parts:
            return
        self._pg().hotkey(*parts)

    def scroll(self, direction: str, amount: int) -> None:
        pg = self._pg()
        rw, rh = self._region[2], self._region[3]
        cx, cy = self._to_abs(rw // 2, rh // 2)
        pg.moveTo(cx, cy)
        d = direction.strip().lower()
        if d == "up":
            pg.scroll(amount)
        elif d == "down":
            pg.scroll(-amount)
        elif d == "left":
            pg.hscroll(-amount)
        elif d == "right":
            pg.hscroll(amount)
        else:
            raise ValueError(f"unknown scroll direction: {direction!r}")
