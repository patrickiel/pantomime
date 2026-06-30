"""The reasoning client factory.

Builds the client the planner + judge call. Which backend depends on the
configured ``provider`` (see :mod:`pantomime.reasoning.providers`):

- an Anthropic-compatible endpoint (DeepSeek, Anthropic, a proxy/gateway) -> the
  ``anthropic`` SDK pointed at the resolved ``base_url``;
- OpenAI -> a thin adapter that speaks the same interface over the ``openai`` SDK.

Either way the rest of the reasoning code sees one interface. The endpoint comes
from the provider (or an explicit ``base_url`` override) and the ``api_key`` from
``pantomime.yaml`` via :class:`~pantomime.runtime.config.Settings`. Kept tiny so
the reasoning code is easy to test with a fake client.
"""

from __future__ import annotations

from pantomime.reasoning.providers import provider_kind, resolve_base_url


def make_client(settings=None):
    provider = getattr(settings, "provider", None)
    base_url = resolve_base_url(provider, getattr(settings, "base_url", None))
    api_key = getattr(settings, "api_key", None) or None

    if provider_kind(provider) == "openai":
        from pantomime.reasoning.openai_backend import OpenAIClient

        return OpenAIClient(base_url=base_url, api_key=api_key)

    import anthropic

    return anthropic.Anthropic(base_url=base_url, api_key=api_key)
