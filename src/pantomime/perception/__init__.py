"""Perception: screenshot -> structured ScreenState (elements + text + roles).

Windows UI Automation is the primary, precise, local source of truth. A local
OpenCV + OCR grounder is the fallback for screens UIA can't see. Both feed ONE
uniform ScreenState, so the grounding contract is identical regardless of origin:
the planner references element ids, we resolve id -> box -> center.
"""

from pantomime.perception.screen_state import Element, GroundingError, ScreenState

__all__ = ["Element", "GroundingError", "ScreenState"]
