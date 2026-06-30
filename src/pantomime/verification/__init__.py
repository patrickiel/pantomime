"""Verification: deterministic fast-path checks, then an LLM judge if fuzzy."""

from pantomime.verification.verify import deterministic, verify

__all__ = ["deterministic", "verify"]
