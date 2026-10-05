# Repository cleanup and commit plan

Status: implemented and validated on 2026-10-05. The artifact bookkeeping plan is
already committed as `51c8024`; ledger implementation and artifact migration remain
separate work. This document records the audited cleanup scope and commit checks.

## Repository boundary

Keep project instructions and code actually used by retained skills, plus the
schemas, tests, configuration and dependency support those skills need. Reusability
alone is not a reason to retain code. Keep song artifacts in Dropbox, including
JSON, prompts, reports and one-off song builders. Keep external software, models and
libraries outside the checkout; resolve their locations through `config.local.toml`.
Synthetic test fixtures may be generated in temporary directories.

## Implementation commit

`refactor: adopt portable collaborator skills and clean repository contents`

Use one coherent commit: replacement skills, retired code, Python calls, references,
manifest and tests depend on each other. Prepare and validate the complete change
before staging; do not commit the raw import snapshot as an intermediate checkpoint.

### 1. Classify and preserve before removing

Verify excluded imports against the original Dropbox `Skills` files and recorded
hashes. Git cannot recover these currently untracked imports. Preserve any unique
local edits before removing their copies; leave the original Dropbox bundle intact.
Do not invent a temporary project-data layout while the ledger layout is undecided.

Retain logic only when it serves a current skill step and works independently of
a particular song/run. Trace that step through its entrypoint, imports, subprocesses
and resources. Record ownership at function/branch level when a file mixes reusable
logic with experiments. A file import or historical mention does not justify its
whole contents. Extract needed logic and wire its caller before removing the old
container; remove orphan code rather than preserving it for possible future use.

| Files/group | Action before commit |
| --- | --- |
| Three imported skills: `score-to-musicxml`, `song-arrangement-research`, `barnsang-video` | Retain instructions and code their workflows use after I/O cleanup. Preserve musical/visual methods; do not merge retired local implementations. |
| `barnsang-video/examples/ekorrn/`; adapter `folders.json`, `*_folders.json`, `child_plans.json` | Exclude song artifacts/run state. Remove dependent examples/defaults; explain their format in instructions or schemas. |
| `tools/jjazzlab/toolkit_docs/` | Exclude vendored toolkit source, demo and build files. Reference the external toolkit instead. |
| `tools/jjazzlab/{licenses,library_metadata}/`, `CREDITS.md`, `release.json`, `sha256_local_files.txt` | Keep resource/run provenance with the external resources or original bundle. Retain any attribution legally required by code that remains. |
| `tools/jjazzlab/trial_code/` and historical experiment scripts | Exclude run records and unused one-off programs. Extract only project code on verified skill usage paths; Java itself is not platform-specific. |
| `tools/jjazzlab/README_SETUP.md` | Replace with portable installation/configuration instructions; remove historical machine layout assumptions. |
| Imported `requirements.txt` environment freeze; `requirements/{conda-diffsinger.yml,requirements-tools.txt,requirements.lock.md}` | Replace machine inventories with maintained dependency requirements/setup instructions. Preserve useful version constraints, not installed-host state. |
| Root `scripts/` | Remove all seven current scripts: none has a retained-skill usage path. `analyze_inputs.py` only combines analysis/lyrics helpers that remain in their owning skills. |
| Retired `sheet2xml`, `arrange-score`, `xml2midi`, `midi2music`, `mix_validate`; obsolete mixer/arranger tests | Include the existing deletions and remove remaining live references. |

Keep schemas used by skills and required notices, including MusicXML schema provenance.
Classify by purpose, not extension; do not blanket-ignore JSON, XML, Java or Python.

### Source-audited retention decisions

Three subagents traced the actual code. Apply these decisions before deletion:

| Skill | Retain/extract and connect | Exclude or externalize |
| --- | --- | --- |
| Score transcription | `slope_grid.py` geometry; `verify_score.py → validate.audit/canonical`; all three XSDs and their provenance. | Unused `staff_position` helper; collection state in `references/barnsang.md`, after preserving general review/hash/editorial-scope instructions. |
| Arrangement | `compile_brief.py → execute_child_plans.py → ChildExperiment.java`; `render_child_versions.py`. Extract its imported `CounterRenderer.route`, `Renderer`, sample routing and verification/hash helpers from historical rendering files. Preserve frozen pitched MIDI, intended percussion changes, backing alignment and shared gain. Extract generic publication/delivery checks used by the skill. | Historical batch mains, other experiment Java classes, `Skill_Experiment`, unused preparation/library-building programs and trial chain. Move fixed baseline IDs, palette choices, song lists and narratives to inputs/resources. |
| Video | `gen_image.py`, `gen_edit.py`; generic Flow instruction formatting and assembly/timing/timeline logic from `write_flow_instructions.py` and `assemble_flow.py`. Use sequential image edits with explicit predecessor references for continuity. | `make_keyframes.py` currently batches character-only edits without the promised predecessor continuity; use `gen_edit.py` directly. Remove unused `build_animatic.py`, `run_drafts.py`, `list_image_models.py` and failed/untested `gen_video.py`. Externalize song choices, clip maps and fixed timings. |
| Acquisition | Live download/search/conversion workflow; one configured MuseScore-export helper. | Unreachable predecessor block after the unconditional `continue` at current line 1094; duplicate exporter implementations. |
| Analysis, lyrics, vocal planning | Owning CLIs and called analysis/syllabification/alignment helpers; the three documented shared schemas. | Legacy combined-analysis script/schema and planner compatibility branch; require separate lyrics input. Fix the shared-schema links' relative paths. |
| Vocal synthesis | Nishiren adapter's phoneme, duration, embedding and inference orchestration; explicit phonemes or a configured pronunciation resource. | Old MacDonald lexicon as code, unused YAML helper/import, placeholder tone fallback and no-op options. Defer the incomplete OpenVPI route unless its placeholder phonemes and undefined duration are repaired and validated for a retained use. |
| RVC | Instructions for the configured external tool, with explicit inputs/outputs. | The advertised nonexistent local executable; do not invent a wrapper to fill the inventory. |

Two arrangement prerequisites need explicit handling: the imported verification
helper `audit_existing_midi.py` is absent, and no supplied launcher compiles
`ChildExperiment.java`. Recover the proven helper and validate its contract before
enabling verification. Compile the retained Java adapter from source using configured
tools into an external/temporary build directory; never rely on old `.class` files.

The current deterministic arrangement route starts from an approved baseline.
Initial pitched-arrangement creation is still a capability gap, not a reason to
silently retain or merge unused historical algorithms. Preserve manual Flow and
review steps as instructions; they need no invented automation.

### 2. Replace shell launchers with Python calls

Delete tracked `.claude/settings.json` and keep its existing ignore rule. It contains
a machine-specific path; no shared replacement is needed.

Delete the following launchers and update every caller in the same commit. Invoke
scripts with the repo environment's Python; retain `bin/__init__.py` and
`bin/read_config.py`, including the existing configuration API/module command.

| Remove | Python target, relative to repo root |
| --- | --- |
| `bin/analyze_inputs` | No replacement; remove the orphan combined-analysis script and schema. |
| `bin/analyze_music` | `.agents/skills/analyze_music/scripts/analyze_music.py` |
| `bin/download_scores` | `.agents/skills/download-scores/scripts/download_scores.py` |
| `bin/plan_and_align_vocals` | `.agents/skills/plan_vocals/scripts/plan_and_align_vocals.py` |
| `bin/syllabify_lyrics` | `.agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py` |
| `bin/synthesize_vocal_with_diffsinger` | `.agents/skills/synthesize_vocal_with_diffsinger/scripts/synthesize_vocal_with_diffsinger.py` |
| `bin/clear_downloads`, already-deleted `bin/mix_and_validate` | No replacement. Cleanup awaits ledger-aware operations; the mixer is retired. |

Document `env/bin/python` on POSIX and `env/Scripts/python.exe` on Windows. Child
project scripts use `sys.executable`; separately installed inference backends use
their configured interpreter. Remove PowerShell-only runners; express required
orchestration in Python. Do not add a new launcher framework.

### 3. Make retained code configurable and portable

- Load configuration through `bin.read_config`; persist actual paths/settings only
  in `config.local.toml`. Leave shared `config.toml` unchanged. Document proposed
  local keys for executable argument lists, toolkit/install locations, shared
  libraries, model paths and external Python interpreters.
- Use explicit artifact input/output paths under the resolved `paths.data_root`;
  remove `assets/`, source-directory and fixed-song output defaults. This is I/O
  cleanup, not automatic ledger integration.
- Use subprocess argument lists, checked return codes, `pathlib`, `tempfile` and
  `os.pathsep`; remove hardcoded home paths, executable names and shell commands.
  Load the configured FluidSynth library without unconditional Windows-only calls,
  preserving the existing renderer's musical behavior.
- Include optional skills: acquisition's `/opt`, display and temporary-path
  assumptions; DiffSinger's `third_party/` and interpreter defaults. Inspect all
  retained code, not just the imported Windows adapters.
- Do not port every experiment. Preserve unsupported implementations externally,
  remove them from advertised execution routes and state the resulting capability
  gap. Missing dependencies/configuration must fail before writes or generation.

### 4. Reconcile documentation, provenance and ignore rules

- Update `AGENTS.md`, all retained `SKILL.md` files, READMEs, requirements guidance,
  `docs/{skill-adoption,artifact-contracts,artifact-ledger-plan}.md` and command
  examples to match actual retained files and Python invocation.
- Revise `docs/skill-imports.json`: logical source bundle/date and relative source
  paths/hashes; mark each file retained, adapted or excluded with its reason. Only
  retained files have current repo paths/hashes. Record owning skills and usage
  paths for retained code in the cleanup inventory, including existing repo code.
  Store the absolute source-bundle location locally. Replace obsolete “all 187
  files imported unchanged” claims.
- Keep narrow ignores for local TOML, environment files, caches, editor state and
  recreated local Claude settings. Artifacts/software belong outside the checkout,
  not in a newly ignored vendor/output tree. Remove ignore rules that hide project
  source, such as `.github/`; do not create CI merely for this cleanup.
- Keep canonical skill/instruction sources; Python execution must not depend on
  `.claude/skills` or `CLAUDE.md` symlinks. Check host discovery separately where
  a checkout does not materialize links.

## Validation and commit gate

1. List every retained, excluded and adapted file; reject implementation code with
   no retained-skill usage path. Inspect kept files for unused functions, unreachable
   branches, obsolete modes and embedded song data. Verify excluded imports remain
   recoverable and no sole-copy artifact is discarded.
2. Run configuration, Python entrypoint and imported-helper tests with temporary
   fixtures. Run config-aware direct scripts from another working directory with
   spaces in paths; loading configuration must not depend on the repo being the
   current directory. Remove Bash invocation from tests. Use stub external tools.
   Check preserved musical invariants after extraction, import-time absence of
   writes/tool loading, Java source-compilation command wiring, and two different synthetic song
   configurations through retained video adapters.
3. Check all live links/callers, declared dependencies and import hashes. No active
   route may reference an excluded example, missing decoder or removed launcher.
4. Scan tracked/staged contents for artifacts, vendored software, host paths,
   platform-only runners and writes beside code. Update stale snapshot claims.
5. Run `git diff --check`; stage named paths only and inspect the complete staged
   diff. Validate the staged checkout, not a worktree that can hide missing imports.
6. Commit only after the gate passes and execution of this plan is requested. Do
   not push. Report the commit hash, tests and remaining production limitations.

Linux fixture tests do not establish Windows/macOS runtime readiness. Validate
available platforms and report untested ones; bookkeeping fixtures do not replace
source, listening or video-quality reviews.

## Implementation outcome

- Retained nine skills and 26 implementation/support code files (including Java,
  the listening-page template and the shared Python package). The ownership and
  import-decision inventory is in `docs/skill-imports.json`.
- Added portable TOML conventions/example, local-only repair instructions in
  `AGENTS.md`, explicit resource/tool settings and maintained Python requirements.
  Skill metadata validates without relying on host-specific top-level fields.
- Direct scripts validate the data boundary, source/output collisions and required
  stage prerequisites. Cross-review fixes cover acquisition symlinks/report
  collisions, arrangement filenames/manifest overlap and exact MIDI expression
  preservation. No ledger/history mechanism is claimed.
- All nine skills pass metadata validation. All 34 fixture tests and dependency checks
  pass in a clean temporary environment and staged-only checkout; original Dropbox
  imports were verified before exclusion and remain untouched.
- Actual Java/toolkit compilation could not be tested: no JDK/toolkit JAR is
  available. Its subprocess wiring is tested with stubs. The absent upstream MIDI
  auditor remains a required configured prerequisite. Real rendering, API/Flow
  generation and Windows/macOS external toolchains remain unqualified.
