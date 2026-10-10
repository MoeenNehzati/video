# Project instructions

This project turns sheet music into children's music videos. The README provides
an overview; selected skills own their domain methods and execution details.

## Workflow and bookkeeping

- Default workflow: `score-to-musicxml` → `song-arrangement-research` →
  `barnsang-video`. Acquisition and analysis/vocal skills are optional. Read the
  selected skill's prerequisites and preserve proven musical/visual methods;
  do not restore retired implementations without evidence of improvement.
- Load `.agents/skills/artifact-bookkeeping/SKILL.md` before starting or resuming
  song-artifact work, including after compaction. All artifact access goes through
  it, including implicit reads/writes by tools, subprocesses, GUI actions, downloads
  and APIs. Repository source/configuration inspection is outside the song ledger.
- Each production skill's minimal Bookkeeping block names artifact-bookkeeping
  and declares local I/O, resources, settings and constraints. Keep organizational procedures
  in artifact-bookkeeping. Production scripts expose ordinary domain interfaces
  without bookkeeping imports, calls, flags, callbacks or runtime registration.
  See [the README example](README.md#adding-a-skill-bookkeeping).
- Follow [cross-stage contracts](docs/artifact-contracts.md) and
  [supported routes](docs/artifact-ledger-entrypoints.md). Unavailable routes stop
  before production; synthetic tests do not establish practical or human acceptance.

## Runtime and configuration

- Reuse compatible Python 3.11+ and repo-root `env/`. Follow
  [requirements](requirements/README.md) when creating it or changing dependencies.
  Reuse compatible tools; install only missing or incompatible requirements for
  the selected operation. Do not guess model, sample-library or musical-preset choices.
- Invoke `env/bin/python` on POSIX or `env/Scripts/python.exe` on Windows, using
  canonical `.agents/skills/` script paths. No shell launchers or host-discovery
  symlinks; child project scripts use `sys.executable`.
- At session start, run that Python with `-m scripts.read_config` from the repo root.
  Resolve missing settings/prerequisites before pipeline work. Use its `--run`
  option when a command needs configuration environment variables; see
  [configuration](docs/configuration.md) for setup, invocation and verification.
- Keep machine settings and verified dependency paths/versions in ignored
  `config.local.toml`, preserving existing values. Never alter shared `config.toml`
  to repair one host. Discover existing settings/installations before asking for
  missing information. Keep installation guidance under `requirements/`.

## Repository and data boundary

- Skills own their scripts and tests. Root `scripts/` contains shared configuration
  helpers and the test runner; root `tests/` contains shared fixtures, cross-skill
  integration and repository checks. Run `env/bin/python scripts/run_tests.py`
  (Windows: `env/Scripts/python.exe scripts/run_tests.py`).
- Retain instructions, skill-used code and required schemas, templates, tests,
  configuration and dependency support. Remove orphan code; update ownership and
  provenance in `docs/skill-imports.json` when changing retained code.
- All song/run artifacts, including prompts, logs, reports and one-off builders,
  belong under resolved `paths.data_root`. Preserve existing shared data and
  reviewed inputs; use bookkeeping for selection, import and revision decisions.
- Reproducible repository reports and build intermediates belong in ignored
  `_build/`. A clean checkout must work without them. Required source files remain
  versioned; song artifacts do not belong in `_build/`.
- Keep external software, native libraries, sound banks and models outside the
  checkout, referenced in local TOML. Do not vendor them or hide them in ignored
  project folders. Synthetic tests may use temporary directories.
