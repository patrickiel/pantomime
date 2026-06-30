"""Reporting: JUnit XML, run trace + screenshots, NL failure explanation."""

from pantomime.reporting.explain import explain_result
from pantomime.reporting.junit import build_junit, write_junit
from pantomime.reporting.trace import TraceRecorder

__all__ = ["TraceRecorder", "build_junit", "explain_result", "write_junit"]
