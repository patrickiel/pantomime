"""JUnit XML output — each step/assertion becomes a <testcase> for CI."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pantomime.orchestrator.results import TestResult


def build_junit(result: "TestResult") -> str:
    failures = sum(1 for s in result.steps if not s.passed)
    suites = ET.Element("testsuites")
    suite = ET.SubElement(
        suites,
        "testsuite",
        name=result.id,
        tests=str(len(result.steps)),
        failures=str(failures),
        time=f"{result.duration_s:.3f}",
    )
    for s in result.steps:
        case = ET.SubElement(
            suite,
            "testcase",
            classname=result.id,
            name=f"{s.kind}: {s.goal}"[:250],
        )
        if not s.passed:
            failure = ET.SubElement(case, "failure", message=(s.error or "failed")[:300])
            failure.text = s.verdict_reasoning or s.error or ""
    ET.indent(suites)
    return ET.tostring(suites, encoding="unicode")


def write_junit(result: "TestResult", path: str | Path) -> Path:
    path = Path(path)
    path.write_text(build_junit(result), encoding="utf-8")
    return path
