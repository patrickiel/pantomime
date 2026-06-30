<p align="center">
  <img src="design/icon.svg" alt="Pantomime" width="128" />
</p>

<h1 align="center">Pantomime</h1>

<p align="center"><em>Natural-language end-to-end testing for anything on screen.</em></p>

Pantomime is an end-to-end GUI testing framework where test cases are written in
plain **natural language**. You describe what a user would do ("Type the
username, click Sign in, confirm the welcome screen"), and Pantomime carries it
out on the real screen.

<p align="center">
  <video src="https://github.com/patrickiel/pantomime/raw/main/design/screencast.mp4" controls muted loop playsinline width="900">
    <a href="https://github.com/patrickiel/pantomime/raw/main/design/screencast.mp4">Watch the screencast</a>
  </video>
</p>

Under the hood, local perception "sees" the screen (Windows UI Automation, plus
a local OpenCV and OCR grounder for screens UI Automation cannot read), a
reasoning model plans and judges each step, and one content-agnostic driver acts
out the clicks and keystrokes on a screen region without knowing or caring what
is inside it.

This README has two parts:

- **[Writing and running tests](#writing-and-running-tests)** is for anyone who
  authors tests. Start here.
- **[How it works](#how-it-works)** and the sections after it explain the
  internals and how to develop Pantomime itself.

---

## Writing and running tests

This section is the complete guide for an end user who writes tests. It takes you
from an empty project to a passing run you can step through in a browser.

### 1. Requirements

- **Windows.** Pantomime drives the desktop through Windows UI Automation, win32
  input, and Windows OCR. It is Windows-only.
- **Python 3.12**, managed by [uv](https://docs.astral.sh/uv/).
- **An API key for a reasoning model**, used to plan steps and judge
  natural-language checks. One exception: `--dry-run` plans without a key.
- For your first run, set the display to **100% scaling** to avoid DPI edge
  cases.

### 2. Install the `panto` command

Pantomime is a framework you install into your own project; your tests are YAML
files that live in your repo next to your app. Install the `panto` command from a
local checkout (it is not published to PyPI yet):

```powershell
uv tool install --editable "C:\path\to\pantomime"
```

If the shell cannot find `panto` afterward, run `uv tool update-shell` and open a
new terminal. For a one-off run without installing, use
`uvx --from "C:\path\to\pantomime" panto ...`.

> Working **inside this repository** instead? Run `uv sync` once, then prefix
> every command with `uv run` (for example `uv run panto run tests`). The rest of
> this guide writes `panto` for brevity.

### 3. Scaffold a project

From the root of your project:

```powershell
panto init           # scaffolds into ./tests (pass a different dir to override)
```

`init` is append-only and never overwrites existing files (pass `--force` to
replace them). It creates these things:

Pantomime's own files are grouped under a `config/` folder so the project root
stays clean:

| Path                            | Purpose                                                                                                                          |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `tests/example.yaml`            | A valid starter test that exercises every field. Edit it for your app.                                                           |
| `config/pantomime.yaml`         | Your project config: name, models, grounding, the `api_key`, and the `vars`/`secrets` tests use. **Gitignored** (holds the key). |
| `config/pantomime.example.yaml` | Committed template with placeholders. A fresh clone copies it to `config/pantomime.yaml`.                                        |
| `.gitignore`                    | Updated (append-only) to ignore `runs/` and `config/pantomime.yaml`.                                                             |

The schemas are not scaffolded into your project. They are generated from
Pantomime's models and hosted in this repo's [`schemas/v1/`](schemas/v1/) folder, so
every project on the same version references the same files.

**Editor support.** The generated test and config start with a modeline pointing
at the hosted schema. It is the same URL for every YAML file, regardless of folder
depth:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/patrickiel/pantomime/main/schemas/v1/testcase.schema.json
```

With that line and the VS Code YAML extension, you get live validation,
autocomplete, and hover docs while editing. The same schemas are enforced when a
test or the config is loaded, so a misspelled field fails fast. Regenerate the
hosted copies any time with `panto schema -o schemas/v1/testcase.schema.json` and
`panto schema --config -o schemas/v1/pantomime.schema.json`.

Everything a project needs lives in **`config/pantomime.yaml`**: a name, which
models to use, grounding, pricing, the reasoning `api_key`, and the `vars`/`secrets`
your tests reference. Because it holds the key and secrets it is **gitignored**; the
committed `config/pantomime.example.yaml` is the shared template a fresh clone
copies. `panto init` asks for a project name and seeds `config/pantomime.yaml` for
you — open it and fill in your values:

```yaml
# config/pantomime.yaml  (gitignored)
name: my-app             # shown in the web debugger header
api_key: sk-...
provider: deepseek       # required: reasoning backend (deepseek | anthropic | openai)
planner_model: deepseek-v4-pro
judge_model: deepseek-v4-flash
effort: medium           # required: low | medium | high | xhigh | max
grounding_enabled: true  # required: local OpenCV/OCR grounder (false = UIA-only)
pricing:                   # required: price every model the planner/judge use
  deepseek-v4-pro:   { input_per_mtok: 0.435, output_per_mtok: 0.87 }
  deepseek-v4-flash: { input_per_mtok: 0.07,  output_per_mtok: 0.14 }
vars:
  USER: demo_user          # referenced in tests as ${VAR:USER}
secrets:
  DEMO_PASSWORD: hunter2   # referenced in tests as ${SECRET:DEMO_PASSWORD}
```

Set your reasoning provider's `api_key` (the provider is swappable; see
[Configuration](#configuration)). Pantomime loads `config/pantomime.yaml`
automatically on every command, walking up from the working directory; built-in
defaults fill in anything you omit, except `provider`, `planner_model`, `judge_model`,
`effort`, `grounding_enabled`, and `pricing`, which have no default: the YAML alone
chooses the backend, which model runs, how hard it thinks, whether the local grounder
is on, and what it costs, so a run refuses to start until they are set.

### 4. Write a test

A test is a single YAML file. The smallest valid test needs only an `id`, a
`title`, and either a list of `steps` or a free-text `flow`:

```yaml
test:
  id: open-app
  title: "App launches"
  steps:
    - action: "Double-click the 'My App' icon on the desktop."
```

There is intentionally no field for the application or platform. Launching the
app is just another step. Here is a fuller example showing every common field:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/patrickiel/pantomime/main/schemas/v1/testcase.schema.json
test:
  id: login-happy-path
  title: "Login with valid credentials"
  description: >
    A registered user signs in and lands on the welcome screen.
  tags: [smoke, auth]
  priority: high

  # Scope the run to a window whose title contains this text.
  # The CLI --window flag overrides it. Omit to use the foreground window.
  window: Login

  # Test data. Reference values as ${data.NAME}. Pull public values with
  # ${VAR:NAME} (from the vars: map in pantomime.yaml) and secrets with
  # ${SECRET:NAME} (from the secrets: map) so neither sits in the test file.
  data:
    user: "${VAR:USER}"
    password: "${SECRET:DEMO_PASSWORD}"

  preconditions:
    - "The 'Login' window is open and showing the Username and Password fields."

  steps:
    - action: "Type the username '${data.user}' into the 'Username' field."
      expect: "The 'Username' field shows 'demo_user'."

    - action: "Type the password into the 'Password' field."

    - action: "Click the 'Sign in' button."
      expect: "The screen has navigated past the login form to a welcome message."
      timeout_s: 15
      retries: 2

  assertions:
    - "absent:Invalid credentials"
    - "The welcome message indicates the user is logged in."

  teardown:
    - "Click the 'Sign out' button to return to the login form."
```

**Fields**

Required:

| Field               | Type             | Notes                                                                                                         |
| ------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------- |
| `id`                | string           | Unique id; also joins to run history.                                                                         |
| `title`             | string           | Human-readable name.                                                                                          |
| `steps` *or* `flow` | list *or* string | Exactly one. `steps` is structured; `flow` is one free-text scenario. Defining neither, or both, is an error. |

Optional:

| Field           | Type                    | Notes                                                                     |
| --------------- | ----------------------- | ------------------------------------------------------------------------- |
| `description`   | string                  | Free text.                                                                |
| `tags`          | list of strings         | For grouping.                                                             |
| `priority`      | string                  | Free-form, for example `high`.                                            |
| `window`        | string                  | Target a window by title **substring**.                                   |
| `region`        | `[x, y, w, h]`          | Absolute screen rectangle. Omit for the whole screen / foreground window. |
| `data`          | map of string to string | Values referenced as `${data.NAME}`.                                      |
| `preconditions` | list of strings         | Checked before the steps run.                                             |
| `assertions`    | list                    | Final hard checks (see below).                                            |
| `teardown`      | list of strings         | Always runs, even after a failure.                                        |

Each item under `steps` defines **either** a natural-language `action` **or** one
deterministic action field (`key` / `type` / `wait` / `scroll`) — exactly one:

| Field       | Type           | Notes                                                                |
| ----------- | -------------- | -------------------------------------------------------------------- |
| `action`    | string         | The instruction, in natural language (driven by the model).          |
| `key`       | string         | Deterministic: press a key combo, e.g. `Tab`, `ctrl+a`.              |
| `type`      | string         | Deterministic: type literal text into the focused field. Supports `${data.x}` / `${SECRET:NAME}`. |
| `wait`      | number         | Deterministic: pause this many seconds.                              |
| `scroll`    | string         | Deterministic: scroll `up` or `down` (optional `amount:` companion). |
| `expect`    | string         | Optional. A check run right after the action.                        |
| `region`    | `[x, y, w, h]` | Optional. Restrict this step to a rectangle.                         |
| `timeout_s` | int            | Optional. Per-step time budget.                                      |
| `retries`   | int            | Optional. Retries for the whole step attempt.                        |

The deterministic fields run **without any model call or screen sense** — the
action is fixed up front and executed straight away, so a mechanical step like a
keystroke is fast and free. Use them for unambiguous mechanical actions; use
`action` when the agent needs to look at the screen to decide what to do (for
example, clicking a button it has to locate). An `expect` check still runs after
a deterministic action.

The schema is strict: unknown or misspelled fields are rejected.

### 5. Expectations and variables

This is the heart of natural-language authoring.

**Expectations** (used in a step's `expect` and in `assertions`). Three prefixes
are checked deterministically, for free and instantly:

- `contains:<text>` passes if the text appears anywhere on screen
  (case-insensitive).
- `absent:<text>` passes if the text is **not** on screen.
- `prop:<Role>:<Name>` passes if an accessibility element with that role exists
  (name is an optional substring), for example `prop:Button:Sign in`.

Anything else is treated as a natural-language expectation and judged by the
reasoning model against what is on screen, for example
`"The welcome message indicates the user is logged in."` (Fuzzy expectations
need a configured model; they fail if none is available.)

**Variables.** Three reference forms are supported, and only these three:

- `${data.NAME}` substitutes a value from the test's own `data` map.
- `${VAR:NAME}` substitutes a **public** value from the `vars:` map in
  `config/pantomime.yaml`. Not a secret: it is shown in logs and prompts like
  ordinary data. Use it for non-sensitive per-user values such as a username, so
  they stay out of the test file.
- `${SECRET:NAME}` substitutes a secret from the `secrets:` map in
  `config/pantomime.yaml`.

Secrets are redacted everywhere they could leak: logs, the text sent to the
model, and saved screenshots. They are resolved to plaintext only at the instant
they are typed. Put every password or token in a secret and reference it with
`${SECRET:...}`.

### 6. Validate and preview before running

Check a test (or a whole folder) without running it. The summary is printed with
secrets redacted:

```powershell
panto validate tests              # a file or a directory of *.yaml / *.yml
```

See exactly what the planner will see. `sense` prints the current ScreenState,
the list of elements with their `eN` ids, plus a footer with the element count
and target region:

```powershell
panto sense --window Login        # target a window by title substring
panto sense --vision              # also capture a (redacted) screenshot
```

> With no `--window`, no `--region`, and no `window:` field, `sense` and `run`
> target the **foreground window**, which is usually your terminal. Always point
> them at your app.

### 7. Run a test

```powershell
panto run examples/login/tests/login.yaml --window Login
```

- `panto run` accepts a single file or a directory (a suite of all `*.yaml` /
  `*.yml` files, searched recursively).
- `--window <text>` targets a window by title substring and **overrides** the
  test's `window:` field.
- `--dry-run` plans the first action without clicking or typing, and needs no API
  key. Good for sanity-checking a new test.
- Press `Ctrl-C` to cancel; the run stops cleanly at the next safe point.

**Try it with the bundled demo.** See [`examples/login/README.md`](examples/login/README.md) to run the sample Login app and its test.

### 8. Read the results

After each test, the CLI prints a plain-language `PASSED` / `FAILED` explanation:
per step, what was expected, what was observed, and the last action taken, plus a
token and estimated-cost line.

Exit codes (the CI contract):

| Code  | Meaning                                                            |
| ----- | ------------------------------------------------------------------ |
| `0`   | All tests passed.                                                  |
| `1`   | A test ran but failed.                                             |
| `2`   | Parse error (`INVALID:`) or target/region error (`TARGET ERROR:`). |
| `130` | Canceled.                                                          |

Every run also writes artifacts to `runs/<test-id>/<timestamp>/`:

- `result.json` is the full machine-readable result (steps, actions, verdicts,
  token usage, and a USD cost estimate).
- `junit.xml` is a standard JUnit report, the integration point for any CI
  (Jenkins, GitLab, GitHub Actions, and others).
- `step1.png`, `step2.png`, ... are screenshots captured at each check, with
  secret fields blacked out.

### 9. Step through a run in the web debugger

A small web app lets you launch, stop, and replay tests from the browser instead
of the terminal. From inside your project:

```powershell
panto runner          # serves http://localhost:5173 and opens it
```

`panto runner` resolves the project from the current directory (the one whose
`config/pantomime.yaml` it finds by walking up) and starts the debugger scoped to
just that project: one runner instance per project, no shared state. Add `--port`
to change the port or `--no-open` to skip opening a browser tab. The first launch
needs the runner's dependencies installed (`cd runner; pnpm install`).

It lists the project's tests, runs or dry-runs them (it spawns the same `panto run`
under the hood), and lets you replay each run beat by beat: the Sense, Plan, Act,
Verify timeline with the redacted screenshot the loop saw at each step. Each test
keeps a history of past runs with status, duration, tokens, and cost. Navigate
steps with the arrow keys or `j` / `k`. The project's name (from
`config/pantomime.yaml`) shows in the header, and its runs live in
`runs/pantomime.db`. Recording is on by default, and the timeline can follow a run
live.

---

## How it works

Every goal (a precondition, a step, a prose flow, or a teardown line) runs a
four-beat **Sense, Plan, Act, Verify** loop:

1. **Sense** captures the target region and lists the on-screen elements (id,
   role, name, text, box) as a `ScreenState`. Windows UI Automation provides the
   elements; for screens it cannot read (Tkinter fields, custom-drawn UIs), a
   local **OpenCV and OCR grounder** adds the input boxes and visible text. It is
   on by default.
2. **Plan** sends the goal and the ScreenState to the reasoning model, which
   calls a single `act` tool with one action, referencing an element **by id**.
3. **Act** resolves that id to a box and clicks its center, types, or presses
   keys. The model never emits pixel coordinates. This is the *grounding
   contract*: it points at elements, the harness does the geometry.
4. **Verify** runs a deterministic check (`contains:` / `absent:` / `prop:`) or,
   for a natural-language expectation, asks the model to judge the screen.

The loop re-senses after every action and repeats until the model reports done
(or an action budget is reached), then verifies. Assertions are verify-only.
Teardown always runs.

### Perception and the driver

Pantomime perceives and acts on one rectangular screen region and is
content-agnostic: it does not know whether a native app, a browser, or a remote
desktop is inside the rectangle. Element boxes are region-local, so they map
directly onto the screenshots. The driver captures pixels and sends mouse and
keyboard input, doing the single region-local to absolute coordinate conversion
in one place. Password fields are masked in the text and blacked out in any
screenshot before it leaves the machine.

### Reasoning

Planning and judging both call a reasoning model through a configurable
`provider`: `deepseek` or `anthropic` (or any Anthropic-compatible endpoint via
the `anthropic` SDK), or `openai` (the OpenAI SDK behind a thin adapter; install
with `pantomime[openai]`). The model is text-only by default: it reasons over the
structured element list, not a screenshot. The provider and model ids are
configuration, not hard-wired, and are meant to be swapped. Token usage from
every call is accumulated and turned into an estimated USD cost.

---

## Configuration

All configuration lives in **`config/pantomime.yaml`** (the `config/` folder is
discovered by walking up from the working directory). Built-in defaults fill in
anything you omit, so you only set what you want to change. It is gitignored
because it holds `api_key` and `secrets`; commit `config/pantomime.example.yaml`
(placeholders) as the shared template.

| Key                     | Purpose                                                                                                                                                                                |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                  | Project name, shown in the web debugger header (defaults to the directory name).                                                                                                       |
| `api_key`               | API key for the reasoning model. Required to run (not for `--dry-run`).                                                                                                                |
| `provider`              | Reasoning backend: `deepseek`, `anthropic`, or `openai`. Required (no default).                                                                                                         |
| `base_url`              | Override the endpoint URL (a self-hosted proxy or gateway). Defaults to the provider's.                                                                                                |
| `planner_model`         | Planner model id. Required (no default); must have a `pricing` entry.                                                                                                                   |
| `judge_model`           | Judge model id. Required (no default); must have a `pricing` entry.                                                                                                                     |
| `effort`                | Reasoning effort, from low to max. Required (no default).                                                                                                                               |
| `grounding_enabled`     | Toggle the OpenCV and OCR grounder (`true`/`false`). Required (no default).                                                                                                             |
| `pricing`               | USD per 1M tokens, keyed by model id (`input_per_mtok` / `output_per_mtok`). Required: every model the planner/judge use must be priced, so each role is billed at its own rate.        |
| `runs_dir`              | Where run artifacts are written. Relative paths are anchored to the project root (the parent of `config/`), so runs always land under the project regardless of the working directory. |
| `db_path`               | The debugger SQLite database.                                                                                                                                                          |
| `debug_record`          | Record the debugger database (on by default).                                                                                                                                          |
| `vars`                  | Map of public values for `${VAR:NAME}` references (shown in logs).                                                                                                                     |
| `secrets`               | Map of secret values for `${SECRET:NAME}` references (redacted everywhere).                                                                                                            |

---

## CLI reference

```
panto init [dir] [--force]              Scaffold a starter project (default dir: tests).
panto schema [-o path]                  Emit the test-format JSON Schema (stdout, or to a file).
panto validate <path>                   Parse and validate a file or directory; print a redacted summary.
panto sense [--region x,y,w,h]          Print the current ScreenState.
            [--window text] [--vision]
panto run <path> [--window text]        Execute a file or directory of tests.
          [--dry-run]
```

---

## Developing Pantomime

Work inside the repository with uv:

```powershell
uv sync                 # install dependencies into a managed virtualenv
uv run pytest           # run the unit and component suite (offline, no display or API key)
```

The web debugger has its own toolchain:

```powershell
cd runner
pnpm install
pnpm dev                # http://localhost:5173
pnpm check              # type-check
pnpm db:studio          # browse the SQLite database in Drizzle Studio
```

The debugger is a thin reader and launcher around the Python CLI: the Python
side writes every beat to the SQLite database, and the SvelteKit app reads it
through Drizzle. Keep those two schemas in step.

---

## Troubleshooting

| Symptom                                             | Fix                                                                                                                   |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `panto: command not found`                          | Run `uv tool update-shell` and open a new terminal, or use `uv run panto` inside this repo.                           |
| It acts on your terminal                            | Pass `--window <title>` (or set `window:` in the test). With no target, it uses the foreground window.                |
| Fields are not detected                             | Leave grounding on (`grounding_enabled: true` in `config/pantomime.yaml`). Use `panto sense` to see what is detected. |
| Clicks land slightly off                            | Set the display to 100% scaling for the run.                                                                          |
| A fuzzy expectation fails with "no judge available" | Set your reasoning API key, or rewrite the check as `contains:` / `absent:` / `prop:`.                                |
