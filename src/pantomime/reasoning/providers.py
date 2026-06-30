"""Known reasoning providers and how to resolve a backend + base URL.

The reasoning code (planner + judge) is written once against the Anthropic wire
format. A provider's ``kind`` says how to reach it:

- ``anthropic`` — talk that format directly (the ``anthropic`` SDK). Works for any
  Anthropic-compatible endpoint: Anthropic itself, DeepSeek's ``/anthropic``
  endpoint, a self-hosted proxy, or a gateway that fronts other model families.
- ``openai`` — talk the OpenAI Chat Completions format (the ``openai`` SDK), which
  a thin adapter maps to the same interface the reasoning code already uses
  (see :mod:`pantomime.reasoning.openai_backend`). Also covers OpenAI-compatible
  gateways via a ``base_url`` override.

``provider`` picks an entry below; ``base_url`` overrides just the URL (keeping the
provider's kind) to point at an unlisted or self-hosted endpoint. The default
provider is ``deepseek``.
"""

from __future__ import annotations

DEFAULT_PROVIDER = "deepseek"

# provider name -> (kind, default base URL). A None base URL means "use the SDK's
# own default" (e.g. OpenAI's hosted API).
PROVIDERS: dict[str, tuple[str, str | None]] = {
    "deepseek": ("anthropic", "https://api.deepseek.com/anthropic"),
    "anthropic": ("anthropic", "https://api.anthropic.com"),
    "openai": ("openai", None),
}


def _info(provider: str | None) -> tuple[str, str | None]:
    key = (provider or DEFAULT_PROVIDER).strip().lower()
    return PROVIDERS.get(key, PROVIDERS[DEFAULT_PROVIDER])


def provider_kind(provider: str | None) -> str:
    """Which backend talks to ``provider`` — ``"anthropic"`` or ``"openai"``."""
    return _info(provider)[0]


def resolve_base_url(provider: str | None = None, base_url: str | None = None) -> str | None:
    """The endpoint to call: an explicit ``base_url`` wins, else the provider's default."""
    if base_url and base_url.strip():
        return base_url.strip()
    return _info(provider)[1]
