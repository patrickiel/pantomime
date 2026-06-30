"""Secret resolution for ``${SECRET:NAME}`` references.

Secrets are read from the ``secrets:`` map in ``pantomime.yaml`` (which is
gitignored). They are *never* written to logs, traces, or prompts — see
:mod:`pantomime.parser.resolve` for the redaction path that runs everywhere a
value might be displayed.
"""

from __future__ import annotations


class SecretStore:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def get(self, name: str) -> str | None:
        """Return the secret value, or ``None`` if it is not configured."""
        return self._secrets.get(name)
