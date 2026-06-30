"""Emit a JSON Schema for the test-case format from the Pydantic models.

YAML has no schema language of its own, but it is a superset of JSON, so the
de-facto standard is **JSON Schema**. The Pydantic models in
:mod:`pantomime.schema.models` stay the single source of truth: this module
derives the JSON Schema from them, so the two can never drift. Editors (via
``yaml-language-server``) consume the emitted file for author-time validation,
autocomplete, and hover docs; the same models enforce it again at load time.

Regenerate the file with ``panto schema -o <path>`` after changing a model.
"""

from __future__ import annotations

import json
from typing import Any

from pantomime.runtime.config import Settings
from pantomime.schema.models import TestCase

# The generated schemas are committed to this repo's schemas/v1/ folder and served
# raw from GitHub, so every YAML — test or config, at any folder depth — references
# the same absolute URL. That keeps the modeline identical everywhere (no "../"
# depth math) and means scaffolded projects carry no local schema copy to maintain.
SCHEMA_BASE_URL = "https://raw.githubusercontent.com/patrickiel/pantomime/main/schemas/v1"

SCHEMA_FILENAME = "testcase.schema.json"
CONFIG_SCHEMA_FILENAME = "pantomime.schema.json"

SCHEMA_URL = f"{SCHEMA_BASE_URL}/{SCHEMA_FILENAME}"
CONFIG_SCHEMA_URL = f"{SCHEMA_BASE_URL}/{CONFIG_SCHEMA_FILENAME}"

# Prepended to the first line of scaffolded YAML so editors (via yaml-language-server)
# get author-time validation, autocomplete, and hover docs from the hosted schema.
TESTCASE_MODELINE = f"# yaml-language-server: $schema={SCHEMA_URL}"
CONFIG_MODELINE = f"# yaml-language-server: $schema={CONFIG_SCHEMA_URL}"


def build_json_schema() -> dict[str, Any]:
    """Return the JSON Schema describing a Pantomime test document.

    The loader accepts a test as either a bare mapping or one wrapped in a
    top-level ``test:`` key, so the document schema allows both. Note that the
    ``steps`` XOR ``flow`` rule and the ``${...}`` reference syntax are enforced
    by Pydantic at load time, not here — JSON Schema sees them as plain strings.
    """
    testcase = TestCase.model_json_schema()
    # model_json_schema() puts Step/Assertion under $defs and TestCase at the
    # root. Move TestCase into $defs too so the document can $ref both forms.
    defs = testcase.pop("$defs", {})
    defs["TestCase"] = testcase

    # Assertion accepts a bare string too (its `_coerce_string` validator runs
    # before schema generation can see it), so widen the generated object schema
    # to a string-or-object union. Otherwise editors flag every string assertion.
    assertion = defs["Assertion"]
    defs["Assertion"] = {
        "title": assertion.get("title", "Assertion"),
        "description": assertion.get("description", ""),
        "anyOf": [
            {"type": "string", "description": "Natural-language check, or 'absent:<text>'."},
            assertion,
        ],
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pantomime.dev/schema/v1/testcase.schema.json",
        "title": "Pantomime test case",
        "description": "A natural-language GUI test (see pantomime.schema.models).",
        "$defs": defs,
        "anyOf": [
            {"$ref": "#/$defs/TestCase"},
            {
                "type": "object",
                "properties": {"test": {"$ref": "#/$defs/TestCase"}},
                "required": ["test"],
                "additionalProperties": False,
            },
        ],
    }


def render_json_schema() -> str:
    """The test-case schema as a pretty-printed JSON string with a trailing newline."""
    return json.dumps(build_json_schema(), indent=2) + "\n"


def build_config_json_schema() -> dict[str, Any]:
    """Return the JSON Schema describing ``pantomime.yaml`` (the runner config).

    Derived from the :class:`~pantomime.runtime.config.Settings` model, so the
    file format and the loaded settings can never drift.
    """
    schema = Settings.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://pantomime.dev/schema/v1/pantomime.schema.json"
    schema.setdefault("title", "Pantomime project config")
    schema["description"] = "Runner-host config for a Pantomime project (see pantomime.runtime.config)."
    return schema


def render_config_json_schema() -> str:
    """The config schema as a pretty-printed JSON string with a trailing newline."""
    return json.dumps(build_config_json_schema(), indent=2) + "\n"
