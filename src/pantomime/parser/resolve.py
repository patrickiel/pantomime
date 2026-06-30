"""Resolution and redaction of ``${data.x}`` / ``${VAR:NAME}`` / ``${SECRET:NAME}``
references.

Three reference forms:

* ``${data.NAME}`` — a value from the test's own ``data`` map.
* ``${VAR:NAME}`` — a *public* project value from the ``vars`` map in
  ``pantomime.yaml``. Not a secret: shown in logs and prompts like ordinary data.
* ``${SECRET:NAME}`` — a secret from the ``secrets`` map in ``pantomime.yaml``,
  resolved via :class:`SecretStore` and masked everywhere a value might leak.

Two functions, used in two different places:

* :func:`resolve_refs` — full **plaintext** resolution. Used only at the moment
  text is about to be typed into the target (driver). Never logged or prompted.
  Resolves both the raw ``${SECRET:NAME}`` (deterministic ``type`` steps) and the
  masked ``[SECRET:NAME]`` token the planner echoes back from the redacted goal.
* :func:`redact_refs` — resolves ``${data.x}`` and ``${VAR:NAME}`` (non-secret)
  for display but masks any value that flows through a secret as ``[SECRET:NAME]``.
  Used everywhere a value might be shown to a human or sent to the model.

``${data.x}`` values may themselves contain ``${VAR:NAME}`` / ``${SECRET:NAME}``
references, so resolution recurses (with cycle detection).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.runtime.secrets import SecretStore

SECRET_RE = re.compile(r"\$\{SECRET:([A-Za-z0-9_]+)\}")
# The masked form a secret takes once `redact_refs` has run. The planner only ever
# sees this token (the goal is redacted before it reaches the model), so it echoes
# `[SECRET:NAME]` back in its `type` text — which must resolve just like the raw form.
SECRET_MASKED_RE = re.compile(r"\[SECRET:([A-Za-z0-9_]+)\]")
VAR_RE = re.compile(r"\$\{VAR:([A-Za-z0-9_]+)\}")
DATA_RE = re.compile(r"\$\{data\.([A-Za-z0-9_]+)\}")


class ResolutionError(Exception):
    """Raised when a reference cannot be resolved (unknown key/secret, cycle)."""


def resolve_refs(
    value: str,
    data: dict[str, str],
    secrets: "SecretStore",
    variables: dict[str, str] | None = None,
    _seen: frozenset[str] = frozenset(),
) -> str:
    """Resolve all references in ``value`` to their plaintext values."""
    variables = variables or {}

    def _data_sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in _seen:
            raise ResolutionError(f"cyclic data reference: ${{data.{key}}}")
        if key not in data:
            raise ResolutionError(f"unknown data key: ${{data.{key}}}")
        return resolve_refs(data[key], data, secrets, variables, _seen | {key})

    def _var_sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ResolutionError(f"variable not found: ${{VAR:{name}}}")
        return variables[name]

    def _secret_sub(match: re.Match[str]) -> str:
        name = match.group(1)
        secret = secrets.get(name)
        if secret is None:
            raise ResolutionError(f"secret not found: ${{SECRET:{name}}}")
        return secret

    value = DATA_RE.sub(_data_sub, value)
    value = VAR_RE.sub(_var_sub, value)
    value = SECRET_RE.sub(_secret_sub, value)
    # Also resolve the masked `[SECRET:NAME]` form the planner sees and echoes back,
    # so a free-text step types the real secret instead of the literal token.
    value = SECRET_MASKED_RE.sub(_secret_sub, value)
    return value


def redact_refs(
    value: str,
    data: dict[str, str],
    variables: dict[str, str] | None = None,
    _seen: frozenset[str] = frozenset(),
) -> str:
    """Resolve non-secret references for display; mask anything secret-derived.

    Unknown or cyclic data keys (and unset variables) are left verbatim (this is a
    display path, not an execution path — it must never raise).
    """
    variables = variables or {}

    def _data_sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in _seen or key not in data:
            return match.group(0)
        return redact_refs(data[key], data, variables, _seen | {key})

    def _var_sub(match: re.Match[str]) -> str:
        # Public, non-secret value. Show it when set; leave the literal verbatim
        # when unset (display path must never raise — same rule as unknown data).
        name = match.group(1)
        return variables[name] if name in variables else match.group(0)

    value = DATA_RE.sub(_data_sub, value)
    value = VAR_RE.sub(_var_sub, value)
    value = SECRET_RE.sub(lambda m: f"[SECRET:{m.group(1)}]", value)
    return value
