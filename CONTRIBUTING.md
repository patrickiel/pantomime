# Contributing to Pantomime

Thanks for your interest in improving Pantomime. This guide covers how to get a
development environment running and what we look for in a contribution.

## Development setup

Pantomime targets **Windows** and **Python 3.12**, managed by
[uv](https://docs.astral.sh/uv/).

```powershell
uv sync                 # install dependencies into a managed virtualenv
uv run pytest           # run the unit and component suite (offline, no display or API key)
```

The web debugger (`runner/`) has its own toolchain:

```powershell
cd runner
pnpm install
pnpm dev                # http://localhost:5173
pnpm check              # type-check
```

The debugger is a thin reader and launcher around the Python CLI: the Python
side writes every beat to a SQLite database, and the SvelteKit app reads it
through Drizzle. If you change one schema, keep the other in step.

## Before you open a pull request

- **Tests pass.** Run `uv run pytest`; add tests for new behavior.
- **The runner type-checks** if you touched it (`pnpm check` in `runner/`).
- **Schemas are regenerated** if you changed the test or config models:
  ```powershell
  uv run panto schema -o schemas/v1/testcase.schema.json
  uv run panto schema --config -o schemas/v1/pantomime.schema.json
  ```
- **Keep changes focused.** One logical change per pull request is easier to
  review and revert.

## Reporting bugs and requesting features

Open an issue using the templates under
[`.github/ISSUE_TEMPLATE`](.github/ISSUE_TEMPLATE). For bugs, include your
Windows version, display scaling, and the failing test plus the output (with
secrets redacted).

## Code style

Match the surrounding code: its naming, comment density, and idioms. There is no
separate style guide to memorize.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
