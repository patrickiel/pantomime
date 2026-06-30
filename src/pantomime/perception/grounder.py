"""Local GUI grounding: OpenCV input-field detection + Windows OCR for text.

When UI Automation can't see a control (Tkinter text fields, custom-drawn UIs), we
ground it without a vision model. An input field is a filled rectangle — OpenCV
finds it instantly — and Windows' built-in OCR reads the on-screen text, so fields
get **named** from the label above them (Username/Password) for the planner and for
password redaction. Fast (~tens of ms), local, keyless, deterministic: no GPU, no
server, no API key.

``parse`` returns region-local elements and fails soft (``[]`` on any error). Set
``PANTO_GROUNDING_DEBUG=1`` to log what was detected.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from pantomime.perception.screen_state import Element
from pantomime.runtime.log import log, spinner

if TYPE_CHECKING:
    from PIL import Image

    from pantomime.runtime.config import Settings
    from pantomime.schema.models import Region

# An OCR box + its text. Box is (x, y, w, h) in region-local pixels.
_Line = tuple[tuple[int, int, int, int], str]

# Windows OCR is markedly more accurate on upscaled text; 2x reliably reads
# small form labels/values (e.g. "demo_user" instead of "d em o_user") without
# the spurious detections 3x introduces. Word boxes are scaled back down.
_OCR_SCALE = 2


def _norm(text: str) -> str:
    """Collapse OCR whitespace runs; strip. (OCR often inserts stray spaces.)"""
    return re.sub(r"\s+", " ", text or "").strip()


def _despace(text: str) -> str:
    """Drop all whitespace + lowercase — for matching OCR labels like 'p assword'."""
    return re.sub(r"\s+", "", text or "").lower()


class Grounder:
    """Ground UIA-opaque screens with OpenCV (input fields) + Windows OCR (text)."""

    def __init__(self, *, debug: bool = False) -> None:
        self.debug = debug

    def parse(self, img: "Image.Image", region: "Region") -> list[Element]:
        try:
            with spinner("  grounding: cv+ocr"):
                fields = _detect_fields(img)
                lines = _ocr_lines(img)
        except Exception as exc:  # noqa: BLE001
            if self.debug:
                log(f"  [grounder] failed: {exc}")
            return []

        elements: list[Element] = []

        # OCR text -> Text elements (labels, messages). Lines that sit *inside* a
        # detected field are that field's content, folded in below — not emitted
        # separately.
        for i, (box, text) in enumerate(lines):
            if _field_containing(box, fields) is not None:
                continue
            name = _norm(text)
            elements.append(
                Element(id=f"t{i}", role="Text", name=name, text=name, box=box, source="ocr")
            )

        # Input fields -> Edit elements, named from the nearest label above.
        for j, field in enumerate(fields):
            label = _label_above(field, lines)
            content = _content_inside(field, lines)
            is_pw = "password" in _despace(label)
            elements.append(
                Element(
                    id=f"f{j}",  # provisional; sense() re-assigns final ids
                    role="Edit",
                    name=_norm(label) or content,
                    text="" if is_pw else content,
                    box=field,
                    source="cv",
                    is_password=is_pw,
                )
            )

        if self.debug:
            log(f"  [grounder] {len(fields)} field(s), {len(lines)} OCR line(s) -> {len(elements)} element(s)")
        return elements


def _detect_fields(img: "Image.Image") -> list[tuple[int, int, int, int]]:
    """Find input-field rectangles: near-white filled boxes, wide and short.

    Covers light-theme form fields (Tk/WinForms/most web forms). The horizontal
    morphological close bridges any text inside a field so it stays one region.
    """
    import cv2
    import numpy as np

    arr = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB -> BGR
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape
    white = cv2.inRange(gray, 245, 255)
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 21), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    fields: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, w, h = (int(v) for v in cv2.boundingRect(c))
        if w < 60 or not (12 <= h <= 64) or (w / h) < 2.0 or (w * h) < 1000:
            continue
        if w >= 0.97 * w_img and h >= 0.5 * h_img:
            continue  # the window's white card background, not a field
        fields.append((x, y, w, h))
    return fields


def _ocr_lines(img: "Image.Image") -> list[_Line]:
    """Run Windows OCR; return one (box, text) per recognized line. Fail soft."""
    try:
        import asyncio

        return asyncio.run(_ocr_async(img))
    except Exception:  # noqa: BLE001
        return []


async def _ocr_async(img: "Image.Image") -> list[_Line]:
    import io

    from PIL import Image
    import winsdk.windows.graphics.imaging as imaging
    import winsdk.windows.media.ocr as ocr
    import winsdk.windows.storage.streams as streams

    s = _OCR_SCALE
    big = img if s == 1 else img.resize((img.width * s, img.height * s), Image.LANCZOS)
    buf = io.BytesIO()
    big.save(buf, format="PNG")

    stream = streams.InMemoryRandomAccessStream()
    writer = streams.DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(buf.getvalue())
    await writer.store_async()
    stream.seek(0)

    decoder = await imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = ocr.OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return []
    result = await engine.recognize_async(bitmap)

    out: list[_Line] = []
    for line in result.lines:
        words = list(line.words)
        if not words:
            continue
        x = min(w.bounding_rect.x for w in words)
        y = min(w.bounding_rect.y for w in words)
        x2 = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
        y2 = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
        # boxes come back in upscaled pixels; map back to region-local
        out.append(((int(x / s), int(y / s), int((x2 - x) / s), int((y2 - y) / s)), line.text))
    return out


def _field_containing(box: tuple[int, int, int, int], fields: list[tuple[int, int, int, int]]):
    """The field whose rectangle contains the centre of ``box``, or None."""
    bx, by, bw, bh = box
    cx, cy = bx + bw / 2, by + bh / 2
    for f in fields:
        fx, fy, fw, fh = f
        if fx <= cx <= fx + fw and fy <= cy <= fy + fh:
            return f
    return None


def _label_above(field: tuple[int, int, int, int], lines: list[_Line]) -> str:
    """The OCR line sitting *just* above ``field`` (closest, horizontally overlapping).

    The gap between the label's bottom and the field's top must be small — a
    label hugs its field. This keeps a distant line (e.g. a field's label two
    rows up, or text above a button) from being mis-attached.
    """
    fx, fy, fw, fh = field
    max_gap = max(fh, 16)
    best_text, best_y = "", -1
    for (lx, ly, lw, lh), text in lines:
        if ly + lh > fy + 4:  # not above the field
            continue
        if lx > fx + fw or lx + lw < fx:  # no horizontal overlap
            continue
        if fy - (ly + lh) > max_gap:  # too far above to be this field's label
            continue
        if ly > best_y:
            best_y, best_text = ly, text
    return best_text


def _content_inside(field: tuple[int, int, int, int], lines: list[_Line]) -> str:
    """Text OCR'd inside ``field`` (its current value), or ''."""
    for box, text in lines:
        if _field_containing(box, [field]) is not None:
            return _norm(text)
    return ""


def build_grounder(settings: "Settings", *, debug: bool = False) -> Grounder | None:
    """Construct the grounder, or ``None`` when grounding is disabled."""
    if not settings.grounding_enabled:
        return None
    return Grounder(debug=debug or _env_truthy("PANTO_GROUNDING_DEBUG"))


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
