# Project instructions

This project turns sheet music into children's music videos.

## Workflow

- Use `score-to-musicxml`, `song-arrangement-research`, and `barnsang-video` as the
  default workflow. Preserve the collaborator's proven musical/visual methods;
  do not reintroduce retired implementations without evidence of improvement.
- Acquisition and the five analysis/vocal skills are optional. Read the selected
  skill's prerequisites and limitations. See `docs/skill-adoption.md` and
  `docs/artifact-contracts.md` for workflow boundaries.
- Route all song-artifact access through
  `.agents/skills/artifact-bookkeeping/SKILL.md`, including implicit reads and writes
  by scripts, subprocesses, GUI actions, downloads and API calls. Load it before
  starting or resuming artifact work, including after context compaction.
  Each production skill's minimal Bookkeeping block names that skill and supplies
  only local inputs, outputs, resources, settings and domain constraints. Skill
  instructions must not call bookkeeping scripts, specify its API/CLI or duplicate
  its procedure. Artifact-bookkeeping translates those declarations into the actual
  execution and owns organizational policy and recovery.
  Production scripts expose ordinary domain CLIs without bookkeeping imports,
  flags, callbacks or registration; bookkeeping invokes their captured code.
  Repository source/configuration inspection is outside the song ledger.

## Python and configuration

- Reuse the repo-root `env/` environment (Python 3.11+) when compatible. If absent,
  create it with
  `python3 -m venv env` (Windows: `py -3 -m venv env`), then install
  `requirements/requirements-python.txt` with that environment's Python.
  Rerun pip after requirements change; reuse satisfied packages. Install
  `requirements/requirements-vocals.txt` only for requested Nishiren synthesis.
- Invoke Python directly: `env/bin/python` on POSIX or `env/Scripts/python.exe`
  on Windows. Use canonical `.agents/skills/` script paths, not shell launchers
  or host-discovery symlinks. Child project scripts use `sys.executable`.
- At session start, run that Python with `-m scripts.read_config` from the repo root
  and resolve missing configuration before pipeline work. This is the agent's
  initialization task; collaborators launch Codex/Claude normally.
- For commands needing configuration as environment variables, use
  `env/bin/python -m scripts.read_config --run COMMAND ARG...` (Windows:
  `env/Scripts/python.exe -m scripts.read_config --run COMMAND ARG...`). It reloads TOML
  and sets `MUSIC_VIDEO_DATA_ROOT`, `MUSIC_VIDEO_CONFIG_ROOT`, and
  `MUSIC_VIDEO_CONFIG_JSON` for that command and its children, preserving other
  inherited variables. Repeat for each independent tool call; it cannot modify
  the parent agent's environment. Python reads these via `os.environ`; shell
  expansion requires explicitly launching that shell. See `docs/configuration.md`.
- Scripts continue to use the resolved configuration through
  `scripts.project_runtime`; `--config-root` supports an explicit config directory.
- Persist machine settings only in `config.local.toml`, preserving other local
  settings. Never change shared `config.toml` for local configuration.
- If `paths.data_root` is invalid, reuse a confirmed existing project-data path
  or ask for one, verify it, update the local file and rerun the reader.
- If configuration lacks information needed for the requested stage, follow
  `docs/configuration.md` and `config.local.example.toml`: inspect available tools,
  reuse confirmed paths, and ask only for information that cannot be discovered.
  Add only that stage's settings to local TOML, preserving other settings; verify
  the configured paths/commands and rerun the reader. Do not guess a model, sample
  library or musical preset, install software in the repo, or change shared defaults
  to make one computer work.
- Use `requirements/requirements-python.txt` for Python packages and
  `requirements/requirements.md` for non-Python requirements/installations;
  keep any new installation guidance under `requirements/`. First identify the
  selected operation's actual dependencies and discover existing installations;
  reuse compatible ones, and install only missing or demonstrably incompatible
  requirements. Skip unused optional backends. Verify each command/resource and
  record its path plus observed version in `config.local.toml` (`tools.NAME.version`
  or `resource_versions.NAME`), preserving other settings. Follow
  `docs/configuration.md` for TOML conventions, rerun the reader, and test the selected
  skill's operation. Report missing prerequisites before producing artifacts.

## Repository and data boundary

- Skills own their implementation and tests. Keep bookkeeping implementation in
  `.agents/skills/artifact-bookkeeping/scripts/`; other skill instructions depend on
  the bookkeeping skill and its local configuration declarations. Root `scripts/`
  holds only repository-wide configuration
  helpers and the test runner. Root `tests/` holds shared fixtures, cross-skill
  integration and repository checks. Run all suites with
  `env/bin/python scripts/run_tests.py` (Windows:
  `env/Scripts/python.exe scripts/run_tests.py`).
- Retain only instructions, skill-used code, and required schemas, tests,
  configuration and dependency support. Remove orphan code, including unused
  branches inside retained files. Maintain ownership/provenance in
  `docs/skill-imports.json` when changing retained code.
- All song/run artifacts belong under resolved `paths.data_root`: source sheets,
  XML, MIDI, media, JSON, prompts, logs, reviews and one-off song builders.
  Pass explicit inputs/outputs; do not write artifacts beside source code.
- Put reproducible repository audit reports and build intermediates in `_build/`
  (Git-ignored). A clean checkout must work without them. Keep required schemas,
  reusable templates and source provenance versioned; song artifacts still belong
  under `paths.data_root`.
- Keep external software, native libraries, sound banks and models outside the
  checkout; reference them in local TOML. Do not vendor or hide them in ignored
  project folders. Synthetic tests may use temporary directories.
- Preserve existing shared organization and reviewed inputs. Do not infer the
  accepted version from modification time, label, directory or newest revision.
  Resolve explicit selections or ask for an ambiguous creative choice. Import
  existing files explicitly, preserving their originals and unknown provenance;
  never bulk-migrate existing data. The ledger specifications remain in
  `docs/artifact-ledger-plan.md`; implementation usage and limitations are in
  `docs/artifact-ledger-usage.md`.
