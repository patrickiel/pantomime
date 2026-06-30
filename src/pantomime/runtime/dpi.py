"""Process DPI awareness.

UIA rectangles, ``mss`` capture, and ``pyautogui`` input must all agree on a
single coordinate space. If the process is *not* DPI-aware, Windows virtualizes
coordinates: ``win32``/``pyautogui`` report logical (scaled) pixels while ``mss``
reports physical ones, so clicks land in the wrong place on a scaled display.

Declaring per-monitor DPI awareness once, before any GUI library initializes,
makes them all report physical pixels. Call :func:`ensure_dpi_aware` at startup.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.schema.models import Region

_done = False


def scale_for_region(region: "Region") -> float:
    """The DPI scale factor (physical / logical pixels) of the monitor holding ``region``.

    Because the process is per-monitor DPI-aware, every coordinate the runner records
    is in *physical* pixels, so a window the user sees as 1280px wide is captured as
    1920px on a 150% display. The debugger uses this factor to render the screenshot
    back at its logical size. Returns ``1.0`` off Windows or whenever the lookup fails.
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        from ctypes import wintypes

        x, y, w, h = region
        pt = wintypes.POINT(int(x) + int(w) // 2, int(y) + int(h) // 2)

        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        hmon = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST

        shcore = ctypes.windll.shcore
        shcore.GetDpiForMonitor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        ]
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))  # MDT_EFFECTIVE_DPI
        return (dpi_x.value or 96) / 96.0
    except Exception:
        return 1.0


def ensure_dpi_aware() -> None:
    global _done
    if _done or sys.platform != "win32":
        _done = True
        return
    import ctypes

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _done = True
