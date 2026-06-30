"""Unit tests for Settings.load: defaults filled in by config/pantomime.yaml."""

from __future__ import annotations

import pytest

from pantomime.runtime.config import ConfigError, Settings, config_path


def _write_config(root, text: str) -> None:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_defaults_when_no_file(tmp_path):
    s = Settings.load(start=tmp_path)
    # YAML-controlled fields have no built-in default: unset until the file sets them.
    assert s.planner_model == ""
    assert s.provider == ""
    assert s.grounding_enabled is None
    # Identity/secrets/inputs still default to their empty forms.
    assert s.api_key == ""
    assert s.name == ""
    assert s.vars == {}
    assert s.secrets == {}


def test_load_reads_name(tmp_path):
    _write_config(tmp_path, "name: My Project\n")
    assert Settings.load(start=tmp_path).name == "My Project"


def test_load_reads_config_file(tmp_path):
    _write_config(
        tmp_path,
        "planner_model: my-model\n"
        "grounding_enabled: false\n"
        "pricing:\n  my-model:\n    input_per_mtok: 1.5\n    output_per_mtok: 3.0\n"
        "api_key: sk-test\n"
        "vars:\n  USER: demo_user\n"
        "secrets:\n  PW: hunter2\n",
    )
    s = Settings.load(start=tmp_path)
    assert s.planner_model == "my-model"
    assert s.grounding_enabled is False
    assert s.pricing["my-model"].input_per_mtok == 1.5
    assert s.api_key == "sk-test"
    assert s.vars == {"USER": "demo_user"}
    assert s.secrets == {"PW": "hunter2"}


def test_load_finds_config_in_parent(tmp_path):
    _write_config(tmp_path, "planner_model: parent-model\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    s = Settings.load(start=nested)
    assert s.planner_model == "parent-model"
    assert s.project_root == tmp_path.resolve()


def test_runs_anchored_to_project_root(tmp_path):
    # config/ lives at the project root; runs land at the root even when `panto` is
    # invoked from a subdirectory deep inside the project.
    _write_config(tmp_path, "runs_dir: runs\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    s = Settings.load(start=nested)
    assert s.project_root == tmp_path.resolve()
    assert s.resolved_runs_dir() == tmp_path.resolve() / "runs"
    assert s.resolved_db_path() == str(tmp_path.resolve() / "runs" / "pantomime.db")


def test_runs_absolute_path_kept(tmp_path):
    abs_runs = (tmp_path / "elsewhere").resolve()
    _write_config(tmp_path, f"runs_dir: {abs_runs.as_posix()}\n")
    s = Settings.load(start=tmp_path)
    assert s.resolved_runs_dir() == abs_runs


def test_runs_root_when_no_config(tmp_path):
    s = Settings.load(start=tmp_path)
    assert s.project_root == tmp_path.resolve()
    assert s.resolved_runs_dir() == tmp_path.resolve() / "runs"


# --- pricing: each role billed at its own model's rate -------------------


def _priced(**overrides) -> Settings:
    """A complete, runnable Settings: backend + grounding set, two priced models."""
    base = dict(
        provider="deepseek",
        planner_model="big",
        judge_model="small",
        effort="high",
        grounding_enabled=True,
        pricing={
            "big": {"input_per_mtok": 10.0, "output_per_mtok": 20.0},
            "small": {"input_per_mtok": 1.0, "output_per_mtok": 2.0},
        },
    )
    base.update(overrides)
    return Settings(**base)


def test_cost_usd_prices_each_role_by_its_model():
    s = _priced()
    usage = {
        "planner": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},  # 10 + 20 = 30
        "judge": {"input_tokens": 2_000_000, "output_tokens": 0},  # 2 + 0 = 2
    }
    assert s.cost_usd(usage) == 32.0


def test_cost_usd_zero_without_usage():
    assert _priced().cost_usd({}) == 0.0


# --- require_runnable: models + pricing are mandatory --------------------


def test_require_runnable_errors_on_missing_model():
    with pytest.raises(ConfigError, match="planner_model"):
        _priced(planner_model="").require_runnable()


def test_require_runnable_errors_on_missing_effort():
    with pytest.raises(ConfigError, match="effort"):
        _priced(effort="").require_runnable()


def test_require_runnable_errors_on_missing_provider():
    with pytest.raises(ConfigError, match="provider"):
        _priced(provider="").require_runnable()


def test_require_runnable_errors_on_missing_grounding():
    with pytest.raises(ConfigError, match="grounding_enabled"):
        _priced(grounding_enabled=None).require_runnable()


def test_require_runnable_allows_explicit_grounding_false():
    _priced(grounding_enabled=False).require_runnable()  # an explicit false is a valid choice


def test_require_runnable_errors_on_unpriced_model():
    # 'small' is referenced as judge_model but absent from pricing.
    with pytest.raises(ConfigError, match="small"):
        _priced(pricing={"big": {"input_per_mtok": 1, "output_per_mtok": 1}}).require_runnable()


def test_require_runnable_ok_for_complete_config():
    _priced().require_runnable()  # must not raise
