"""Implementation of ``panto init`` (project scaffold).

Pantomime is a framework you install into your own project. Your tests are
plain YAML files that live in your repo, version-controlled next to your app.
``panto init`` drops a working starting point into the current directory so a
freshly-installed user has something valid to run and adapt.
"""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path

from pantomime.schema.export import CONFIG_MODELINE, TESTCASE_MODELINE

# The scaffolded files are kept as readable, editable YAML templates under
# pantomime/templates/ rather than inlined here. _PROJECT_NAME_TOKEN is replaced
# with the chosen project name when the config is written.
_PROJECT_NAME_TOKEN = "__PROJECT_NAME__"


def _template(filename: str) -> str:
    """Read a packaged template from pantomime/templates/."""
    return (files("pantomime") / "templates" / filename).read_text(encoding="utf-8")


# A generic, schema-valid starter test. It exercises every field the loader
# accepts so it doubles as a reference. The schema modeline (a hosted URL, the
# same for every test regardless of folder depth) is prepended here.
def _example_yaml() -> str:
    return f"{TESTCASE_MODELINE}\n{_template('example_test.yaml')}"


# The whole project config: an identity (name), runner settings, the reasoning
# api_key, and the vars and secrets that tests reference. Because it holds the key
# and secrets, the real file (pantomime.yaml) is gitignored; this template is
# committed as pantomime.example.yaml AND seeded into pantomime.yaml for the user
# to fill in. The modeline (prepended here) gives editors validation/autocomplete
# from pantomime.schema.json. Commented values show the defaults the loader uses.
def _config_yaml(name: str) -> str:
    body = _template("pantomime.yaml").replace(_PROJECT_NAME_TOKEN, name)
    return f"{CONFIG_MODELINE}\n{body}"

# Lines ensured (append-only) in .gitignore. Run artifacts are state, not source.
# config/pantomime.yaml holds the api_key and secrets, so it must never be committed
# — the committed config/pantomime.example.yaml is the shared template.
_GITIGNORE_ENTRIES = ["runs/", "config/pantomime.yaml"]


def _write_file(path: Path, content: str, *, force: bool) -> bool:
    """Write ``content`` to ``path``. Returns True if written, False if skipped.

    Existing files are never clobbered unless ``force`` is set.
    """
    if path.exists() and not force:
        print(f"  exists, skipping: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote: {path}")
    return True


def _merge_gitignore(path: Path, entries: list[str]) -> None:
    """Append any missing ``entries`` to .gitignore without rewriting it."""
    existing_lines: set[str] = set()
    original = ""
    if path.exists():
        original = path.read_text(encoding="utf-8")
        existing_lines = {line.strip() for line in original.splitlines()}

    missing = [e for e in entries if e not in existing_lines]
    if not missing:
        print(f"  up to date: {path}")
        return

    block = ""
    if original and not original.endswith("\n"):
        block += "\n"
    if original:
        block += "\n# Pantomime run state and secrets\n"
    else:
        block += "# Pantomime run state and secrets\n"
    block += "\n".join(missing) + "\n"

    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    verb = "updated" if original else "created"
    print(f"  {verb}: {path} (added {', '.join(missing)})")


def _resolve_name(name: str | None, default: str) -> str:
    """The project name: the flag, else an interactive prompt, else the default."""
    if name:
        return name
    if sys.stdin.isatty():
        try:
            entered = input(f"Project name [{default}]: ").strip()
        except EOFError:
            entered = ""
        return entered or default
    return default


def run_init(target_dir: str = "tests", *, force: bool = False, name: str | None = None) -> int:
    """Scaffold a starter test layout into the current directory.

    Creates ``<target_dir>/example.yaml``, the committed ``pantomime.example.yaml``
    template, a gitignored ``pantomime.yaml`` (seeded from the template), and a
    ``.gitignore`` (merged). The project ``name`` is taken from the flag, an
    interactive prompt, or the directory name. Returns 0 on success (including when
    files were skipped), 1 on an OS-level write error.

    No schema files are written: the scaffolded YAML references the schemas hosted
    on GitHub (see pantomime.schema.export.SCHEMA_BASE_URL), so there is nothing
    local to keep in sync.
    """
    from pantomime.runtime.config import CONFIG_DIR

    cwd = Path.cwd()
    config_dir = cwd / CONFIG_DIR
    project_name = _resolve_name(name, cwd.name)
    config_yaml = _config_yaml(project_name)
    print(f"Scaffolding a Pantomime project in {cwd}")
    try:
        # The example test; its modeline points at the hosted test schema.
        _write_file(cwd / target_dir / "example.yaml", _example_yaml(), force=force)
        # Committed config template (config/ keeps the project root clean).
        _write_file(config_dir / "pantomime.example.yaml", config_yaml, force=force)
        # The working config, gitignored. Seeded from the template; the user fills
        # in the real api_key/secrets here.
        _write_file(config_dir / "pantomime.yaml", config_yaml, force=force)
        _merge_gitignore(cwd / ".gitignore", _GITIGNORE_ENTRIES)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print()
    print("Next steps:")
    print(f"  1. Edit {CONFIG_DIR}/pantomime.yaml (gitignored): set api_key and your vars/secrets.")
    print(f"  2. Edit {target_dir}/example.yaml for your app.")
    print(f"  3. Validate:  panto validate {target_dir}")
    print(f"  4. Run:       panto run {target_dir}")
    return 0
