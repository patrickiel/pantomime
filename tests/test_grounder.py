"""Unit tests for the CV + OCR grounder (synthetic image; OCR monkeypatched)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from pantomime.perception import grounder as G
from pantomime.perception.grounder import Grounder, _detect_fields, _label_above, build_grounder
from pantomime.runtime.config import Settings


def _form_image() -> Image.Image:
    """A 200x120 light-gray form with two white input rectangles."""
    img = Image.new("RGB", (200, 120), (240, 240, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 30, 140, 48], fill=(255, 255, 255))  # field 1 (120x18)
    d.rectangle([20, 70, 140, 88], fill=(255, 255, 255))  # field 2 (120x18)
    return img


# --- build_grounder ------------------------------------------------------


def test_disabled_returns_none():
    assert build_grounder(Settings(grounding_enabled=False)) is None


def test_enabled_returns_grounder():
    assert isinstance(build_grounder(Settings(grounding_enabled=True)), Grounder)


# --- OpenCV field detection ----------------------------------------------


def test_detect_fields_finds_white_rectangles():
    fields = _detect_fields(_form_image())
    # both white input rectangles are found, top-to-bottom
    ys = sorted(y for _, y, _, _ in fields)
    assert len(fields) == 2
    assert any(28 <= y <= 32 for y in ys) and any(68 <= y <= 72 for y in ys)
    for x, y, w, h in fields:
        assert w >= 60 and 12 <= h <= 64  # input-field shape


# --- label association ---------------------------------------------------


def test_label_above_picks_closest_overlapping():
    field = (20, 30, 120, 18)
    lines = [
        ((20, 14, 60, 10), "Username"),  # directly above -> the label
        ((20, 0, 40, 8), "Login"),  # higher up -> ignored
        ((400, 16, 50, 10), "Far"),  # no horizontal overlap -> ignored
    ]
    assert _label_above(field, lines) == "Username"


# --- end-to-end parse (OCR faked) ----------------------------------------


def test_parse_names_fields_and_flags_password(monkeypatch):
    lines = [
        ((20, 14, 60, 10), "Username"),
        ((20, 54, 60, 10), "p assword"),  # OCR spacing artifact -> still detected as password
        ((20, 100, 90, 10), "Invalid credentials"),
    ]
    monkeypatch.setattr(G, "_ocr_lines", lambda img: lines)

    els = Grounder().parse(_form_image(), (0, 0, 200, 120))
    edits = {e.name: e for e in els if e.role == "Edit"}
    assert set(edits) == {"Username", "p assword"}
    assert edits["Username"].is_password is False
    assert edits["p assword"].is_password is True
    assert all(e.source == "cv" for e in edits.values())

    # the non-label OCR line becomes a Text element
    texts = [e.name for e in els if e.role == "Text"]
    assert "Invalid credentials" in texts


def test_parse_fails_soft_on_error(monkeypatch):
    def _boom(img):
        raise RuntimeError("cv blew up")

    monkeypatch.setattr(G, "_detect_fields", _boom)
    assert Grounder().parse(_form_image(), (0, 0, 200, 120)) == []
