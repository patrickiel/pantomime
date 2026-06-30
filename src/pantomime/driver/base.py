"""The driver interface.

A driver captures pixels from, and sends mouse/keyboard input to, a single
rectangle ``[x, y, w, h]`` on the display. It is **content-agnostic**: it neither
knows nor cares what is inside the rectangle (a native app, a browser, a VNC
client). Whatever the user puts there is what gets driven.

**All coordinates passed to a driver are region-LOCAL** — origin ``(0, 0)`` is
the top-left of the region. Converting to absolute desktop pixels happens in
exactly one place (see :class:`RegionDriver._to_abs`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from pantomime.schema.models import Region


class OutOfRegionError(Exception):
    """Raised when a strict driver is asked to act outside its region."""


class Driver(ABC):
    """Capture + input on one screen rectangle, in region-local coordinates."""

    @property
    @abstractmethod
    def region(self) -> "Region":
        """The driven rectangle ``(x, y, w, h)`` in absolute desktop pixels."""

    @abstractmethod
    def screenshot(self) -> "Image.Image":
        """Capture the region and return it as an RGB PIL image."""

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Move the pointer to region-local ``(x, y)``."""

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """Left-click at region-local ``(x, y)``."""

    @abstractmethod
    def double_click(self, x: int, y: int) -> None:
        """Double left-click at region-local ``(x, y)``."""

    @abstractmethod
    def right_click(self, x: int, y: int) -> None:
        """Right-click at region-local ``(x, y)``."""

    @abstractmethod
    def type(self, text: str) -> None:
        """Type ``text`` into the focused control (click to focus first)."""

    @abstractmethod
    def key(self, combo: str) -> None:
        """Press a key or chord, e.g. ``"enter"`` or ``"ctrl+a"``."""

    @abstractmethod
    def scroll(self, direction: str, amount: int) -> None:
        """Scroll ``"up" | "down" | "left" | "right"`` by ``amount`` clicks."""
