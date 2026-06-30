"""Image redaction: paint over sensitive element boxes before a screenshot
ever leaves the machine (to the planner, the judge, or a saved trace).

Any element flagged ``is_password`` is filled with a solid block so the secret
is masked even in a vision crop.
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from pantomime.perception.screen_state import Element


def redact_image(img: "Image.Image", elements: "list[Element]") -> "Image.Image":
    """Return a copy of ``img`` with sensitive element boxes blacked out.

    ``img`` is the region image; element boxes are region-local, so they map
    directly onto it.
    """
    from PIL import ImageDraw

    out = img.copy()
    draw = ImageDraw.Draw(out)
    for el in elements:
        if not el.is_password:
            continue
        x, y, w, h = el.box
        draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0))
    return out


def encode_png_b64(img: "Image.Image") -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def redact_and_encode(img: "Image.Image", elements: "list[Element]") -> str:
    """Redact sensitive boxes and return a base64-encoded PNG."""
    return encode_png_b64(redact_image(img, elements))
