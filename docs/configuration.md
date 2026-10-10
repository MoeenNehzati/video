# Configuration and fresh-machine setup

`scripts.read_config` recursively merges tracked `config.toml` and ignored
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
3. Run the environment's Python with `-m scripts.read_config` from the repo root.
   Correct the named setting if validation fails. The printed JSON is the resolved
   configuration; do not commit it as an artifact.
4. Read the selected skill and [installation instructions](../requirements/README.md).
   Check configured paths and existing installations before installing anything.
   Reuse compatible dependencies; install only what that operation needs and lacks,
   outside the checkout. Record verified paths and observed versions in local TOML.
   Missing model/sample choices require an explicit selection; do not
   substitute arbitrary ones. API credentials come from environment variables.
5. Configure bookkeeping as described below. The agent uses bookkeeping to run
   the selected skill's ordinary interface with exact inputs and outputs. Read
   [artifact bookkeeping usage](../.agents/skills/artifact-bookkeeping/references/usage.md) before producing files.
   Its preflight checks the settings it uses. `--config-root DIR` selects another
   directory containing `config.toml` and an optional `config.local.toml`; by default
   configuration comes from the code checkout regardless of working directory.

## Artifact bookkeeping

Managed production requires `[bookkeeping]` with a nonempty `actor_id` label and
a lowercase UUIDv4 `host_id`. The actor attributes a collaborator; it is not
authentication. Generate the host ID once per machine, preserve it in local TOML,
and do not copy another host's ID. For example, obtain a fresh value with
`env/bin/python -c "import uuid; print(uuid.uuid4())"`, then merge it into the
existing local file. Neither identity belongs in shared defaults. The reader
validates a present bookkeeping table; inspection/configuration setup can proceed
without that table, while the ledger rejects missing managed-production identity.

Resource-consuming operations also require `paths.resource_cache`: an absolute
local directory outside both the repository and synchronized data root, with no
containing/contained relationship to either. Missing cache directories may be
created by resource preparation. Keep installed tools, sample libraries and models
in their existing external locations. The resource adapter copies the declared
consumed files into a private verified snapshot; it must never hardlink a mutable
installation or silently substitute newer bytes. A descriptor in the ledger does
not prove that its historical resource bytes are locally available.

Native tool capture currently supports Linux ELF binaries/libraries, not macOS
Mach-O or Windows PE formats. Python portability does not qualify native backends.
The bookkeeping [execution guide](../.agents/skills/artifact-bookkeeping/references/usage.md#resources-and-execution-limits)
defines descriptor fields and dependency-manifest requirements. A configured path
is setup information, not proof that a tool's full resource set is qualified.

Python-package adapters additionally require `resources.python_packages` to name
the active environment's installed package directory. Discover it with
`env/bin/python -c "import sysconfig; print(sysconfig.get_path('purelib'))"` and
record the interpreter version under `resource_versions.python_packages`. This
source directory is the deliberate exception to external-resource placement:
the project's existing `env/` stays reusable. Consumed distribution files and
their declared package dependencies are copied into the external private cache;
the producer runs from those copies with isolated import paths. Interpreter,
standard library and operating-system libraries remain the recorded platform
boundary, not a copied or sandboxed operating system.

Choose a short cache root. Every fully expanded resource path must be shorter
than 240 characters, including run identifiers and package-internal filenames.
The observed music21 dependency manifest needs a cache root of at most 41
characters; other versions may impose a tighter limit. Preflight checks the
actual manifest before copying. Do not shorten package filenames or omit files
to evade this limit.

Optional synthesis still needs a selected compatible Nishiren model and the
packages in `requirements/requirements-vocals.txt`, including the ONNX decoder.
The implemented adapter and mock tests do not establish those live prerequisites.
Do not install optional vocal packages for unrelated stages.

Keep existing data organization intact. Bookkeeping writes only newly prepared
operations and explicitly imported files; setup does not scan and migrate the
shared root. Machine caches and publication/view journals are namespaced by
`host_id`; immutable ledger events and history live under `paths.data_root`.
`scripts.read_config --run` only supplies configuration: it does not make arbitrary
external commands managed. Use the bookkeeping skill and its declared operations.

When a required setting is absent, first inspect existing local settings and
available installations, reuse confirmed paths, and ask only for information
that cannot be determined. Fix **local TOML**, verify the path/command and rerun
its reader. Do not alter shared defaults or copy software into the repository to
repair a host. Do not replace an existing configuration wholesale.

## Load configuration into a command's environment

The agent reads configuration at session start, then uses `--run` whenever a
command needs environment variables. Collaborators still launch Codex or Claude
normally; there is no client launcher, settings sync or Git hook to install.

```console
env/bin/python -m scripts.read_config --run env/bin/python -c "import os; print(os.environ['MUSIC_VIDEO_DATA_ROOT'])"
```

On Windows replace both Python paths with `env/Scripts/python.exe`.

| Variable | Value |
| --- | --- |
| `MUSIC_VIDEO_DATA_ROOT` | Validated, resolved `paths.data_root` |
| `MUSIC_VIDEO_CONFIG_ROOT` | Absolute directory containing the TOML files |
| `MUSIC_VIDEO_CONFIG_JSON` | Full merged configuration as JSON; arrays, booleans and numbers retain their types; TOML dates/times become ISO strings |

Other inherited variables are preserved; these three values replace any stale
inherited copies. Each invocation rereads TOML, validates it before launching, and
returns the child's exit status without printing configuration alongside its
output. For another configuration directory, put `--config-root DIR` **before**
`--run`. From another working directory, invoke the reader by its absolute file
path instead of `-m scripts.read_config`.

Arguments are passed directly, without shell expansion. In Python use `os.environ`
and `json.loads` for the JSON value. To use shell variables, explicitly launch the
shell, for example `--run bash -c 'printf "%s\\n" "$MUSIC_VIDEO_DATA_ROOT"'`;
expansion must occur inside that child, not in the outer tool call.
Repeat `--run` for separate commands: it changes neither the parent agent's
environment nor future independent shells. Existing skill scripts keep their
TOML reader and path checks; these environment variables do not replace validation.

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

Run `env/bin/python scripts/run_tests.py` for synthetic checks.
Those tests create their own TOML and data fixtures; they must not depend on this
machine's local configuration, production assets, credentials or model installs.
Linux fixture checks do not certify external Windows/macOS toolchains.
