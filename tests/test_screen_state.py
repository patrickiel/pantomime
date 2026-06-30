"""Unit tests for ScreenState grounding and prompt serialization."""

from __future__ import annotations

import pytest

from pantomime.perception.screen_state import Element, GroundingError, ScreenState


def _state() -> ScreenState:
    return ScreenState(
        region=(100, 200, 400, 300),
        elements=[
            Element(id="e1", role="Edit", name="Username", text="demo_user", box=(20, 40, 200, 30)),
            Element(id="e2", role="Edit", name="Password", text="hunter2", box=(20, 90, 200, 30), is_password=True),
            Element(id="e3", role="Button", name="Sign in", text="Sign in", box=(20, 140, 100, 36)),
        ],
    )


def test_resolve_and_center():
    s = _state()
    assert s.resolve("e3") == (20, 140, 100, 36)
    # center is region-local (origin added later by the driver)
    assert s.center("e3") == (70, 158)


def test_resolve_unknown_raises():
    s = _state()
    with pytest.raises(GroundingError):
        s.resolve("e99")


def test_to_prompt_blanks_password_and_is_deterministic():
    s = _state()
    prompt = s.to_prompt()
    assert prompt["region"] == [100, 200, 400, 300]
    pw = next(e for e in prompt["elements"] if e["id"] == "e2")
    assert pw["is_password"] is True
    assert pw["text"] == ""  # never leak the value
    # key order within each element is fixed
    assert list(prompt["elements"][0].keys()) == ["id", "role", "name", "text", "box", "is_password"]


def test_to_prompt_excludes_image():
    s = _state()
    s.image_b64 = "AAAA"
    assert "image_b64" not in s.to_prompt()
