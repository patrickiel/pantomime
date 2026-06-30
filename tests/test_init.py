"""Unit tests for ``panto init`` (the project scaffold)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pantomime.cli import main
from pantomime.cli_init import run_init
from pantomime.parser.loader import load_testcase


def test_init_creates_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    rc = run_init()
    assert rc == 0
    assert (tmp_path / "tests" / "example.yaml").exists()
    # Config files are grouped under config/ to keep the project root clean.
    assert (tmp_path / "config" / "pantomime.yaml").exists()
    assert (tmp_path / "config" / "pantomime.example.yaml").exists()
    assert not (tmp_path / "pantomime.yaml").exists()  # not loose at the root
    # Schemas are hosted on GitHub, not scaffolded into the project.
    assert not (tmp_path / "config" / "pantomime.schema.json").exists()
    assert not (tmp_path / "config" / "testcase.schema.json").exists()
    assert (tmp_path / ".gitignore").exists()
    # The example's modeline points to the hosted test schema (same URL everywhere).
    from pantomime.schema.export import TESTCASE_MODELINE

    first_line = (tmp_path / "tests" / "example.yaml").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == TESTCASE_MODELINE


def test_generated_example_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    run_init()
    tc = load_testcase(tmp_path / "tests" / "example.yaml")
    assert tc.id == "example-smoke"
    assert tc.data["user"] == "${VAR:MY_USER}"
    assert tc.data["password"] == "${SECRET:MY_PASSWORD}"
    assert len(tc.steps) == 4
    # The scaffold demonstrates a deterministic (LLM-free) keystroke step.
    assert any(s.deterministic_field == "key" for s in tc.steps)


def test_generated_config_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from pantomime.runtime.config import Settings

    monkeypatch.chdir(tmp_path)
    run_init(name="My App")
    s = Settings.load(start=tmp_path)
    assert s.name == "My App"
    assert s.grounding_enabled is True
    assert s.vars == {"MY_USER": "demo_user"}
    assert s.secrets == {"MY_PASSWORD": "change-me"}
    # Models live only in the YAML; assert the scaffold is internally consistent and
    # runnable rather than pinning a specific id (which would just reintroduce drift).
    assert s.planner_model and s.judge_model
    assert s.planner_model in s.pricing
    assert s.judge_model in s.pricing
    s.require_runnable()  # the scaffolded config must start a real run without error


def test_init_name_defaults_to_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from pantomime.runtime.config import Settings

    monkeypatch.chdir(tmp_path)
    run_init()  # no name, non-interactive -> directory name
    assert Settings.load(start=tmp_path).name == tmp_path.name


def test_init_does_not_clobber(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    example = tmp_path / "tests" / "example.yaml"
    example.parent.mkdir()
    example.write_text("SENTINEL", encoding="utf-8")

    run_init()  # no --force
    assert example.read_text(encoding="utf-8") == "SENTINEL"

    run_init(force=True)
    assert example.read_text(encoding="utf-8") != "SENTINEL"
    assert load_testcase(example).id == "example-smoke"


def test_gitignore_merge_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    run_init()
    run_init()  # second run must not duplicate entries
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("runs/") == 1
    assert lines.count("config/pantomime.yaml") == 1


def test_gitignore_preserves_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\nruns/\n", encoding="utf-8")

    run_init()
    text = gitignore.read_text(encoding="utf-8")
    assert "*.pyc" in text  # original kept
    assert text.count("runs/") == 1  # already present, not re-added
    assert "config/pantomime.yaml" in text  # missing entry appended


def test_init_cli_entrypoint_custom_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["init", "e2e"])
    assert rc == 0
    assert (tmp_path / "e2e" / "example.yaml").exists()
