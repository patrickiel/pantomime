"""Windows UI Automation enumeration.

All UIA/COM access happens on **one dedicated STA worker thread**. pywinauto's
UIA backend is built on COM, which is apartment-threaded; calling it from
arbitrary threads causes intermittent marshalling errors. Routing every call
through a single ``CoInitialize``d thread avoids that entirely.

``enumerate_uia(region)`` returns region-local :class:`Element`s (clipped to the
region). Elements are returned in tree-encounter order with provisional ids;
:mod:`pantomime.perception.sense` sorts and re-assigns final ``eN`` ids.
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Callable

from pantomime.perception.screen_state import Element

if TYPE_CHECKING:
    from pantomime.schema.models import Region

# Interactable control types we always keep.
_ALWAYS = {
    "Button", "Edit", "CheckBox", "RadioButton", "ComboBox", "MenuItem",
    "Hyperlink", "TabItem", "ListItem", "Slider", "Spinner", "TreeItem",
    "Document", "SplitButton", "Menu",
}
# Static text/labels: keep only when they carry a name.
_LABELS = {"Text", "StatusBar"}


class _UiaWorker:
    """A single STA thread that executes UIA callables and returns results."""

    _instance: "_UiaWorker | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_UiaWorker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._q: "queue.Queue[tuple[Callable, Future] | None]" = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="pantomime-uia", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _loop(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        self._ready.set()
        while True:
            item = self._q.get()
            if item is None:
                break
            fn, fut = item
            try:
                fut.set_result(fn())
            except Exception as exc:  # noqa: BLE001 - propagate to caller
                fut.set_exception(exc)

    def submit(self, fn: Callable, timeout: float = 30.0):
        fut: Future = Future()
        self._q.put((fn, fut))
        return fut.result(timeout=timeout)


def enumerate_uia(region: "Region", max_elements: int = 200) -> list[Element]:
    """Enumerate region-local interactable elements via UI Automation."""
    return _UiaWorker.get().submit(lambda: _enumerate(region, max_elements))


# --- worker-thread implementation ----------------------------------------


def _enumerate(region: "Region", max_elements: int) -> list[Element]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    desktop = Desktop(backend="uia")
    out: list[Element] = []
    for root in _roots_for_region(desktop, region):
        for ctrl in _safe_descendants(root):
            el = _to_element(ctrl, region, len(out))
            if el is not None:
                out.append(el)
                if len(out) >= max_elements:
                    return out
    return out


def _roots_for_region(desktop, region: "Region"):
    rx, ry, rw, rh = region
    region_area = max(rw * rh, 1)
    try:
        wins = list(desktop.windows())
    except Exception:
        return []
    best, best_overlap = None, 0
    for w in wins:
        r = _rect_of(w)
        if r is None:
            continue
        ov = _overlap_area(r, region)
        if ov > best_overlap:
            best, best_overlap = w, ov
    # Region sits mostly inside one window -> scope to it (fast, low-noise).
    if best is not None and best_overlap >= 0.5 * region_area:
        return [best]
    # Otherwise return every window that intersects the region.
    inter = [w for w in wins if _overlap_area(_rect_of(w) or (0, 0, 0, 0), region) > 0]
    return inter or wins


def _safe_descendants(root):
    items = [root]
    try:
        items.extend(root.descendants())
    except Exception:
        pass
    return items


def _to_element(ctrl, region: "Region", index: int) -> Element | None:
    try:
        info = ctrl.element_info
        rect = info.rectangle
    except Exception:
        return None
    if rect is None:
        return None
    local = _to_local_box((rect.left, rect.top, rect.right, rect.bottom), region)
    if local is None:
        return None

    role = str(getattr(info, "control_type", None) or "Unknown")
    name = str(getattr(info, "name", None) or "").strip()
    if not _keep(role, name, local):
        return None

    is_pw = _is_password(ctrl)
    text = "" if is_pw else _control_text(ctrl)
    enabled = _safe(lambda: bool(ctrl.is_enabled()), True)

    return Element(
        id=f"u{index}",  # provisional; sense() re-assigns final eN ids
        role=role,
        name=name,
        text=text.strip(),
        box=local,
        enabled=enabled,
        is_password=is_pw,
        source="uia",
    )


def _keep(role: str, name: str, local: tuple[int, int, int, int]) -> bool:
    if local[2] < 3 or local[3] < 3:
        return False
    if role in _ALWAYS:
        return True
    if role in _LABELS and name:
        return True
    return False


def _is_password(ctrl) -> bool:
    try:
        return bool(ctrl.element_info.element.CurrentIsPassword)
    except Exception:
        return False


def _control_text(ctrl) -> str:
    for getter in ("get_value", "window_text"):
        try:
            value = getattr(ctrl, getter)()
            if value:
                return str(value)
        except Exception:
            continue
    try:
        return str(ctrl.legacy_properties().get("Value") or "")
    except Exception:
        return ""


def _rect_of(w) -> tuple[int, int, int, int] | None:
    try:
        r = w.rectangle()
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def _overlap_area(a: tuple[int, int, int, int], region: "Region") -> int:
    al, at, ar, ab = a
    rx, ry, rw, rh = region
    il, it = max(al, rx), max(at, ry)
    ir, ib = min(ar, rx + rw), min(ab, ry + rh)
    if ir <= il or ib <= it:
        return 0
    return (ir - il) * (ib - it)


def _to_local_box(
    abs_box: tuple[int, int, int, int], region: "Region"
) -> tuple[int, int, int, int] | None:
    al, at, ar, ab = abs_box
    rx, ry, rw, rh = region
    il, it = max(al, rx), max(at, ry)
    ir, ib = min(ar, rx + rw), min(ab, ry + rh)
    if ir <= il or ib <= it:
        return None
    return (il - rx, it - ry, ir - il, ib - it)


def _safe(fn: Callable, default):
    try:
        return fn()
    except Exception:
        return default
