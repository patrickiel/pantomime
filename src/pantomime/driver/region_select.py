"""Choosing the rectangle to drive.

A test's ``region`` is optional. When omitted, we scope to the **foreground
window** (the app the preconditions just brought to front) — far cheaper and
less noisy than the whole desktop — falling back to the whole primary screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.schema.models import Region


def whole_screen() -> "Region":
    """The primary monitor's rectangle in absolute desktop pixels."""
    import mss

    with mss.MSS() as sct:
        mon = sct.monitors[1]  # [0] is the union of all monitors; [1] is primary
    return (int(mon["left"]), int(mon["top"]), int(mon["width"]), int(mon["height"]))


def foreground_window_region() -> "Region | None":
    """Rectangle of the current foreground window, or ``None`` if unavailable."""
    try:
        import win32gui
    except Exception:
        return None
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None
    return (int(left), int(top), int(w), int(h))


def _matching_windows(title_substr: str) -> list[tuple[int, int, int, "Region"]]:
    """Return (tier, neg_area, hwnd, region) for visible windows matching the
    title, ranked best-first: exact match > starts-with > contains, then larger
    area. This avoids e.g. ``--window Login`` matching "login.yaml - VS Code"
    instead of the actual "Login" window."""
    try:
        import win32gui
    except Exception:
        return []
    needle = title_substr.lower().strip()
    out: list[tuple[int, int, int, Region]] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return
        tl = title.lower()
        if tl == needle:
            tier = 0
        elif tl.startswith(needle):
            tier = 1
        elif needle in tl:
            tier = 2
        else:
            return
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return
        w, h = right - left, bottom - top
        if w > 0 and h > 0:
            out.append((tier, -(w * h), hwnd, (left, top, w, h)))

    win32gui.EnumWindows(_cb, None)
    out.sort(key=lambda m: (m[0], m[1]))
    return out


def find_window_region(title_substr: str) -> "Region | None":
    """Rectangle of the best-matching visible window, or ``None`` if none match.

    Ranks exact title match above starts-with above contains, then by area."""
    matches = _matching_windows(title_substr)
    return matches[0][3] if matches else None


def resolve_region(region: "Region | None", *, prefer_foreground: bool = True) -> "Region":
    """Resolve an explicit region, else the foreground window, else the screen."""
    if region is not None:
        return region
    if prefer_foreground:
        fg = foreground_window_region()
        if fg is not None:
            return fg
    return whole_screen()


def focus_window(title_substr: str) -> bool:
    """Best-effort: bring the best-matching window to the front so it isn't
    occluded (clicks/typing go to whatever is actually on top). Uses the same
    ranking as :func:`find_window_region`. Returns True on success."""
    matches = _matching_windows(title_substr)
    if not matches:
        return False
    hwnd = matches[0][2]
    try:
        import win32con
        import win32gui

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


class RegionError(Exception):
    """Raised when a requested target window can't be found."""


def select_region(region: "Region | None" = None, window: "str | None" = None) -> "Region":
    """Pick the rectangle to drive: explicit region > window-by-title > foreground.

    Raises :class:`RegionError` if ``window`` is given but no window matches.
    """
    if region is not None:
        return region
    if window:
        found = find_window_region(window)
        if found is None:
            raise RegionError(f"no visible window title contains {window!r}")
        return found
    return resolve_region(None)
