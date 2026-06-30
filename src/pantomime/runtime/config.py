"""Project configuration.

Everything a Pantomime project needs lives in ``config/pantomime.yaml`` under the
project root (discovered by walking up from the cwd): runner-host settings (which
models to use, loop limits, settle thresholds, grounding, artifact paths), the
reasoning ``api_key``, plus the ``vars`` and ``secrets`` that tests reference as
``${VAR:NAME}`` and ``${SECRET:NAME}``.

Grouping these under ``config/`` keeps the project root clean (the schemas and the
committed template live there too). Because it holds the key and secrets,
``config/pantomime.yaml`` is **gitignored**; the committed
``config/pantomime.example.yaml`` (placeholders only) is the template a fresh clone
copies. ``panto init`` scaffolds both. There is no environment-variable or
OS-keyring layer: the file is the single source of truth. Most fields have a
built-in default that fills anything the file omits; the exceptions are the
**provider**, the reasoning **models**, the **effort**, the **pricing**, and
**grounding_enabled**, which have no default and must be set in the file (the YAML
alone chooses the backend, which model runs, how hard it thinks, what it costs, and
whether the local grounder is on).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr

# Pantomime's per-project directory and the config file inside it. The directory
# groups config + schemas so the project root stays uncluttered. Run artifacts
# (``runs/``) stay at the project root, not in here.
CONFIG_DIR = "config"
CONFIG_FILENAME = "pantomime.yaml"


def config_path(root: str | Path) -> Path:
    """Path to a project's config file: ``<root>/config/pantomime.yaml``."""
    return Path(root) / CONFIG_DIR / CONFIG_FILENAME


def _find_config_file(start: Path | None) -> Path | None:
    base = (start or Path.cwd()).resolve()
    for directory in (base, *base.parents):
        candidate = directory / CONFIG_DIR / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _read_config_file(path: Path | None) -> dict:
    """Return the mapping in ``pantomime.yaml`` (or ``{}`` if there is none)."""
    if path is None:
        return {}
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


class ConfigError(Exception):
    """Raised when ``config/pantomime.yaml`` is missing something a run requires."""


class ModelPrice(BaseModel):
    """Per-1M-token USD rates for one model (used for the per-run cost estimate)."""

    input_per_mtok: float
    output_per_mtok: float


class Settings(BaseModel):
    # --- Identity ---
    # Human-friendly project name, shown in the web debugger's project switcher.
    # Set by `panto init`; falls back to the project directory name when empty.
    name: str = ""

    # --- Reasoning (planner + judge) ---
    # The reasoning model runs through one of the supported providers. `provider`
    # names a known backend (see pantomime.reasoning.providers): "deepseek" or
    # "anthropic" (or any Anthropic-compatible endpoint) and "openai". `base_url`
    # overrides just the endpoint — a self-hosted proxy or a gateway fronting other
    # model families. The models should be text-capable: screenshots are never sent
    # — the planner/judge reason off the structured element list (UIA + CV/OCR).
    #
    # `provider`/`planner_model`/`judge_model`/`effort` have no built-in default: the
    # YAML is the single source of truth for which backend and model run and how hard
    # they think, so they are set only in pantomime.yaml. A real run refuses to start
    # until they are set and the models are priced (see require_runnable).
    provider: str = ""
    planner_model: str = ""
    judge_model: str = ""
    effort: str = ""  # low | medium | high | xhigh | max (required; no default)
    planner_max_tokens: int = 4000
    # Explicit Anthropic-compatible endpoint. Empty -> derived from `provider`.
    base_url: str = ""
    api_key: str = ""

    def resolved_base_url(self) -> str:
        """The reasoning endpoint: explicit `base_url`, else the provider's."""
        from pantomime.reasoning.providers import resolve_base_url

        return resolve_base_url(self.provider, self.base_url)

    # --- Pricing (USD per 1M tokens; for the per-run cost estimate) ---
    # Keyed by model id: each role is billed at its own model's rate, so a pricier
    # planner + cheaper judge estimate correctly. No built-in default: a run
    # refuses to start unless every referenced model has an entry (require_runnable).
    # The figure is a close estimate, not an invoice.
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)

    def cost_usd(self, usage: dict) -> float:
        """Estimated USD cost from per-role token usage and per-model pricing.

        ``usage`` carries a per-role breakdown (``usage["planner"]`` and
        ``usage["judge"]``, each ``{input_tokens, output_tokens, ...}``); each
        role's tokens are priced by the model that role runs (``planner_model`` /
        ``judge_model``), looked up in ``pricing``. A role whose model is unpriced
        contributes nothing; ``require_runnable`` rejects that before a real run.
        """
        total = 0.0
        for role, model in (("planner", self.planner_model), ("judge", self.judge_model)):
            price = self.pricing.get(model)
            if price is None:
                continue
            tokens = usage.get(role) or {}
            total += (
                tokens.get("input_tokens", 0) / 1_000_000 * price.input_per_mtok
                + tokens.get("output_tokens", 0) / 1_000_000 * price.output_per_mtok
            )
        return total

    def require_runnable(self) -> None:
        """Refuse to start a real run unless the YAML-controlled fields are set.

        ``provider``/``planner_model``/``judge_model``/``effort``/``grounding_enabled``
        and ``pricing`` have no built-in default; the YAML is the single source of
        truth for them. This fails fast with a clear message instead of letting an
        empty model id reach the API or an unpriced model estimate $0. Read-only
        commands (``validate``, ``sense``, the web debugger) and ``--dry-run`` never
        call it, so they load fine with a partial config.
        """
        missing = [
            name
            for name, value in (
                ("provider", self.provider),
                ("planner_model", self.planner_model),
                ("judge_model", self.judge_model),
                ("effort", self.effort),
            )
            if not value
        ]
        if self.grounding_enabled is None:
            missing.append("grounding_enabled")
        if missing:
            raise ConfigError(
                f"config/pantomime.yaml must set {', '.join(missing)} "
                "(no built-in default; set these in pantomime.yaml)."
            )
        unpriced = sorted({self.planner_model, self.judge_model} - set(self.pricing))
        if unpriced:
            raise ConfigError(
                "config/pantomime.yaml has no `pricing` entry for model(s): "
                + ", ".join(unpriced)
                + " (add input_per_mtok / output_per_mtok under `pricing:`)."
            )

    # --- Orchestration ---
    max_actions_per_step: int = 12

    # --- Perception / settle ---
    settle_threshold: float = 0.01
    settle_timeout_s: float = 2.0
    settle_interval_s: float = 0.15

    # --- Grounding fallback ---
    # UIA-first; for UIA-opaque screens (Tkinter fields, custom-drawn UIs) a local
    # grounder adds elements via OpenCV input-field detection + Windows OCR. Fast,
    # local, keyless — no model/server.
    #
    # No built-in default (None until the YAML sets it): true enables the local
    # grounder, false is UIA-only. A real run refuses to start until it is chosen
    # (see require_runnable); an explicit false counts as chosen.
    grounding_enabled: bool | None = None

    # --- Artifacts ---
    # Relative paths are anchored to the project root (the directory holding
    # pantomime.yaml), not the cwd — so runs always land under the project no
    # matter where `panto` is invoked. Use resolved_runs_dir()/resolved_db_path().
    runs_dir: str = "runs"

    # --- Step-by-step web debugger (runner/) ---
    # Records every Sense/Plan/Act/Verify beat + redacted screenshots to a SQLite
    # database the SvelteKit debugger reads. `db_path` empty -> <runs_dir>/pantomime.db.
    debug_record: bool = True
    db_path: str = ""

    # --- Test inputs ---
    # Public values referenced as ${VAR:NAME} (shown in logs) and secrets
    # referenced as ${SECRET:NAME} (redacted everywhere). Keyed by NAME.
    vars: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)

    # The project root: directory containing pantomime.yaml (cwd if none found).
    # Set by load(); not part of the file/schema. Anchors relative artifact paths.
    _project_root: Path = PrivateAttr(default_factory=Path.cwd)

    @property
    def project_root(self) -> Path:
        return self._project_root

    def _anchor(self, p: str | Path) -> Path:
        """Resolve ``p`` against the project root unless it is already absolute."""
        path = Path(p)
        return path if path.is_absolute() else (self._project_root / path)

    def resolved_runs_dir(self) -> Path:
        """Absolute runs directory, anchored under the project root."""
        return self._anchor(self.runs_dir)

    def resolved_db_path(self) -> str:
        from pantomime.reporting.recorder import default_db_path

        if self.db_path:
            return str(self._anchor(self.db_path))
        return str(default_db_path(self.resolved_runs_dir()))

    @classmethod
    def load(cls, start: Path | None = None) -> "Settings":
        """Build settings from ``pantomime.yaml`` (defaults fill anything omitted).

        The file is discovered by walking up from ``start`` (default: the current
        working directory). Keys are validated by Pydantic. The project root (for
        anchoring run artifacts) is the directory that holds the file, or ``start``
        / the cwd when there is no file.
        """
        path = _find_config_file(start)
        settings = cls(**_read_config_file(path))
        # path is <root>/config/pantomime.yaml -> project root is two levels up.
        settings._project_root = path.parent.parent if path is not None else (start or Path.cwd()).resolve()
        return settings
