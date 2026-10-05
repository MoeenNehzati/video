# Configuration and fresh-machine setup

`bin.read_config` recursively merges tracked `config.toml` and ignored
`config.local.toml`. Local scalars/lists replace defaults; nested tables merge.
It never edits either file. The shared defaults contain no machine paths.

## Set up a new checkout

1. Find and reuse compatible Python 3.11+ and `env/`; create them only if missing.
   Satisfy the default
   [requirements-python.txt](../requirements/requirements-python.txt). Use
   `env/bin/python` on POSIX or `env/Scripts/python.exe` on Windows. No Bash
   launchers, shell activation or discovery symlinks are needed to run scripts.
2. Copy [config.local.example.toml](../config.local.example.toml) to
   `config.local.toml` **only if no local file exists**. Otherwise merge the needed
   settings, preserving existing values. Set `paths.data_root` to an existing
   local copy of the shared project-data directory separate from the checkout
   (neither inside it nor containing it).
3. Run the environment's Python with `-m bin.read_config` from the repo root.
   Correct the named setting if validation fails. The printed JSON is the resolved
   configuration; do not commit it as an artifact.
4. Read the selected skill and [installation instructions](../requirements/README.md).
   Check configured paths and existing installations before installing anything.
   Reuse compatible dependencies; install only what that operation needs and lacks,
   outside the checkout. Record verified paths and observed versions in local TOML.
   Missing model/sample choices require an explicit selection; do not
   substitute arbitrary ones. API credentials come from environment variables.
5. Invoke the skill's canonical Python script with explicit inputs and outputs.
   Its preflight checks the settings it uses. `--config-root DIR` selects another
   directory containing `config.toml` and an optional `config.local.toml`; by default
   configuration comes from the code checkout regardless of working directory.

When a required setting is absent, first inspect existing local settings and
available installations, reuse confirmed paths, and ask only for information
that cannot be determined. Fix **local TOML**, verify the path/command and rerun
its reader. Do not alter shared defaults or copy software into the repository to
repair a host. Do not replace an existing configuration wholesale.

## Conventions

- Configuration paths are absolute strings. `~` and environment-variable syntax
  are not expanded. On Windows use forward slashes or TOML single-quoted literal
  strings to avoid backslash escapes. Resolve symlinks when checking boundaries.
- `paths.data_root` is the only project artifact root. Script artifact arguments
  may be absolute beneath it or relative to it, never to the current directory.
  Validation rejects escapes, including symlinks. Some legacy plan payloads still
  contain absolute execution paths; rebuild/validate them after relocating data.
- `[tools.NAME].command` is a nonempty argv list: executable, then optional fixed
  arguments. A configured name on `PATH` is allowed; use an absolute executable
  when several versions exist. No shell quoting, pipes, redirection or implicit
  shell expansion. Paths containing spaces are single arguments.
- `[resources]` contains absolute external file/directory paths. Resource-internal
  paths follow that resource's documented format. Keep models, sample banks,
  license/credit records and third-party implementations outside the checkout.
- `tools.NAME.version` and `resource_versions.NAME` record verified installed
  versions (or a resource release/commit/SHA-256 identity). Match resource names to
  `[resources]`. `tools.NAME.bundled_versions` can record bundled runtimes/engines;
  `tools.audiveris.ocr_data_version` identifies installed OCR data. These are setup
  metadata, not automatically enforced pins; recheck after changing installations.
- Requirements are conditional on the selected stage; unused tools need no local
  entry. Run-only options belong in explicit artifact inputs/CLI arguments.
  Secrets do not belong in TOML examples, committed files or run logs.
- Optional `provenance.skill_source_bundle` records the local original collaborator
  bundle location for import audits. Shared provenance uses relative source paths
  and hashes, never this machine-specific location.

## Dependency requirements

The canonical [non-Python requirements and installation list](../requirements/requirements.md)
maps each dependency to its configuration keys and owning workflow. Follow it
when installing or repairing missing prerequisites. That guide includes toolkit/sample requirements; the synthesis skill defines compatible
voicebank files. A successful config read verifies the data root, not every
optional installation or musical quality.

Run `env/bin/python -m unittest discover -s tests -v` for synthetic checks.
Those tests create their own TOML and data fixtures; they must not depend on this
machine's local configuration, production assets, credentials or model installs.
Linux fixture checks do not certify external Windows/macOS toolchains.
