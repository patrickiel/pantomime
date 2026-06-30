"""Unit tests for ${data.x} / ${VAR:NAME} / ${SECRET:NAME} resolution and redaction."""

from __future__ import annotations

import pytest

from pantomime.parser.resolve import (
    ResolutionError,
    redact_refs,
    resolve_refs,
)


class FakeSecrets:
    def __init__(self, **values: str) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name)


def test_resolve_data_and_secret():
    data = {"user": "demo_user", "password": "${SECRET:DEMO_PASSWORD}"}
    secrets = FakeSecrets(DEMO_PASSWORD="hunter2")
    assert resolve_refs("login ${data.user}", data, secrets) == "login demo_user"
    # data value that itself references a secret resolves transitively
    assert resolve_refs("${data.password}", data, secrets) == "hunter2"
    assert resolve_refs("${SECRET:DEMO_PASSWORD}", data, secrets) == "hunter2"


def test_resolve_masked_secret_token():
    # The planner only ever sees the redacted goal, so it echoes back the masked
    # [SECRET:NAME] token; resolution must turn that into the real secret too.
    secrets = FakeSecrets(DEMO_PASSWORD="hunter2")
    assert resolve_refs("[SECRET:DEMO_PASSWORD]", {}, secrets) == "hunter2"
    # round-trip: redact then resolve yields the plaintext
    assert resolve_refs(redact_refs("${SECRET:DEMO_PASSWORD}", {}), {}, secrets) == "hunter2"


def test_resolve_unknown_key_and_secret():
    secrets = FakeSecrets()
    with pytest.raises(ResolutionError):
        resolve_refs("${data.missing}", {}, secrets)
    with pytest.raises(ResolutionError):
        resolve_refs("${SECRET:MISSING}", {}, secrets)


def test_resolve_var_from_map():
    secrets = FakeSecrets()
    variables = {"USER": "demo_user"}
    assert resolve_refs("login ${VAR:USER}", {}, secrets, variables) == "login demo_user"
    # a data value may itself reference a public variable
    data = {"who": "${VAR:USER}"}
    assert resolve_refs("${data.who}", data, secrets, variables) == "demo_user"


def test_resolve_unknown_var_raises():
    secrets = FakeSecrets()
    with pytest.raises(ResolutionError):
        resolve_refs("${VAR:MISSING}", {}, secrets, {})


def test_resolve_cycle_detected():
    data = {"a": "${data.b}", "b": "${data.a}"}
    secrets = FakeSecrets()
    with pytest.raises(ResolutionError):
        resolve_refs("${data.a}", data, secrets)


def test_redact_masks_secrets_but_shows_data():
    data = {"user": "demo_user", "password": "${SECRET:DEMO_PASSWORD}"}
    assert redact_refs("user ${data.user}", data) == "user demo_user"
    # a data value that flows through a secret stays masked
    assert redact_refs("${data.password}", data) == "[SECRET:DEMO_PASSWORD]"
    assert redact_refs("${SECRET:DEMO_PASSWORD}", data) == "[SECRET:DEMO_PASSWORD]"
    # redaction never raises on unknown keys (display path)
    assert redact_refs("${data.unknown}", data) == "${data.unknown}"


def test_redact_shows_public_var():
    variables = {"USER": "demo_user"}
    # public variables are shown, not masked
    assert redact_refs("user ${VAR:USER}", {}, variables) == "user demo_user"
    # unset variable is left verbatim (display path never raises)
    assert redact_refs("${VAR:MISSING}", {}, {}) == "${VAR:MISSING}"
