"""The structured screen representation and the grounding resolver.

``box`` coordinates are **region-local** (origin = top-left of the region), so
they line up with crops and feed straight into the driver, which adds the region
origin once. Element ids (``e1``, ``e2``, ...) are assigned per pass and are only
valid for that pass.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# region-local rectangle: (x, y, w, h)
Region = tuple[int, int, int, int]


class GroundingError(Exception):
    """Raised when an element_ref cannot be resolved to a known element."""


class Element(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    name: str = ""
    text: str = ""
    box: Region  # region-local (x, y, w, h)
    enabled: bool = True
    focused: bool = False
    is_password: bool = False
    source: str = "uia"  # uia | cv | ocr | vlm | template

    def center(self) -> tuple[int, int]:
        x, y, w, h = self.box
        return (x + w // 2, y + h // 2)


class ScreenState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: Region  # absolute desktop rectangle being driven
    elements: list[Element] = []
    ocr_text: str = ""
    stable: bool = True
    # Physical/logical pixel ratio of the captured monitor (1.0 at 100% scaling).
    # Presentation-only: the debugger divides by it to show the screenshot at its
    # logical size. Kept out of to_prompt() so the planner never sees it.
    scale: float = 1.0
    # Optional base64 PNG of the (redacted) region, attached only when the
    # planner needs vision. Excluded from to_prompt() — sent as an image block.
    image_b64: str | None = None

    def by_id(self, element_ref: str) -> Element | None:
        for el in self.elements:
            if el.id == element_ref:
                return el
        return None

    def resolve(self, element_ref: str) -> Region:
        el = self.by_id(element_ref)
        if el is None:
            known = ", ".join(e.id for e in self.elements) or "(none)"
            raise GroundingError(f"unknown element_ref {element_ref!r}; known ids: {known}")
        return el.box

    def center(self, element_ref: str) -> tuple[int, int]:
        x, y, w, h = self.resolve(element_ref)
        return (x + w // 2, y + h // 2)

    def to_prompt(self) -> dict:
        """Compact, deterministic dict for the planner prompt (no image).

        Password fields never expose their value. Key order is fixed so the
        serialized prompt is byte-stable across identical screens (prompt cache).
        """
        return {
            "region": list(self.region),
            "stable": self.stable,
            "elements": [
                {
                    "id": e.id,
                    "role": e.role,
                    "name": e.name,
                    "text": "" if e.is_password else e.text,
                    "box": list(e.box),
                    "is_password": e.is_password,
                }
                for e in self.elements
            ],
        }

    def to_view(self) -> dict:
        """Recording/debug view: the planner prompt dict plus presentation-only
        fields (the device ``scale``) the debugger needs but the planner must not see.
        """
        return {**self.to_prompt(), "scale": self.scale}
