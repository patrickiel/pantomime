"""Load YAML test files into validated :class:`TestCase` objects.

A test file is YAML with a top-level ``test:`` mapping (the ``test:`` wrapper is
optional — a bare mapping is also accepted)::

    test:
      id: TC-LOGIN-001
      title: "Login with valid credentials"
      region: [0, 0, 1280, 800]
      steps:
        - action: "Type '${data.user}' into the 'Username' field."
          expect: "The 'Username' field shows 'testuser'."
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from pantomime.schema.models import TestCase


class ParseError(Exception):
    """Raised when a file cannot be read, parsed, or validated."""


def load_testcase(path: str | Path) -> TestCase:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"cannot read {path}: {exc}") from exc

    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ParseError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(doc, dict):
        raise ParseError(f"{path}: top-level document must be a mapping")

    # Accept either {test: {...}} or a bare {...}.
    body = doc.get("test", doc)

    try:
        return TestCase.model_validate(body)
    except ValidationError as exc:
        raise ParseError(f"{path}: {exc}") from exc


def load_dir(path: str | Path) -> list[TestCase]:
    """Load every ``*.yaml`` / ``*.yml`` file under ``path`` (sorted by name)."""
    path = Path(path)
    files = sorted(
        [*path.rglob("*.yaml"), *path.rglob("*.yml")],
        key=lambda p: str(p).lower(),
    )
    return [load_testcase(f) for f in files]
