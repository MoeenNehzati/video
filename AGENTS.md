# Project instructions

This project turns sheet music into children's music videos.

## Python environment

- Use the repo-root `env/` virtual environment (Python 3.11+). If missing, run
  `python3 -m venv env`, then
  `env/bin/python -m pip install -r requirements/requirements-python.txt`.
  Reinstall requirements after they change. Run Python with `env/bin/python`;
  the `bin/` wrappers use it too.

## Configuration and data

- Before pipeline work, run `env/bin/python -m bin.read_config` from the repo root and
  use its resolved JSON. It combines `config.toml` with local overrides.
- Persist configuration changes only in `config.local.toml`, preserving other
  local settings. Never write them to shared `config.toml`.
- If `paths.data_root` is missing or invalid, ask for the absolute path to an
  existing project-data directory (reuse a path already confirmed in this
  conversation). Verify it, update the local file, and rerun the reader.
- Existing pipeline scripts do not load configuration automatically. Pass
  explicit paths; their `assets/` defaults are legacy. Preserve the data
  directory's existing organization and keep binary media and models out of Git.
