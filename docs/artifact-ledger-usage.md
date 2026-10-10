# Artifact bookkeeping usage

The implementation follows the preserved [plan](artifact-ledger-plan.md),
[event contract](artifact-ledger-contract.md) and
[worked examples](artifact-ledger-examples.md). Those documents describe the
design baseline. This guide describes how to use the implementation; synthetic
checks do not replace the final [interactive acceptance](artifact-ledger-validation-plan.md).

Use the [bookkeeping skill](../.agents/skills/artifact-bookkeeping/SKILL.md) with
every production stage. The [execution coverage](artifact-ledger-entrypoints.md)
states which entrypoints are enabled, manual-managed, read-only or unavailable.
An unavailable adapter stops before production; configuration alone cannot enable
an incomplete adapter. Existing song data is not migrated automatically.
The image routes remain disabled. Automated and interactive acceptance are
separate; a passing synthetic fixture does not complete fresh-agent validation.

Python computation uses the interpreter, standard library and operating-system
libraries as a recorded platform boundary. The package adapter captures selected
installed distributions and their declared dependency closure, then runs the
captured project code against private package copies in an isolated subprocess.
It checks consumed snapshots after execution and prevents repeating the same
prepared child execution. This is not an operating-system sandbox or a hermetic
machine snapshot. Configure the active package source and short private cache as
described in [configuration](configuration.md#artifact-bookkeeping).

Tool adapters accept declared self-contained static ELF executables, reviewed
standard-library Python tools, or explicit ELF loader/library closures. A resource
descriptor records `source.execution.entrypoint` and `mode`. Optional `arguments`
preserves a fixed portable prefix, such as `['-m', 'jdk.compiler/com.sun.tools.javac.Main']`
for the configured Java compiler or MuseScore's headless flags; external file paths
belong in exact input/resource bindings. A prefix can explicitly refer to a captured
file/directory with `{resource}/relative/path`; expansion verifies manifest coverage.
Native score converters additionally record `source.conversion.closure_review` and
an `environment` map of resource-relative font/Qt/data paths (`FONTCONFIG_FILE`,
`FONTCONFIG_PATH`, `FONTCONFIG_SYSROOT`, `QT_PLUGIN_PATH`, `QT_QPA_PLATFORM_PLUGIN_PATH`, `XDG_DATA_DIRS`).
Use `.` for the snapshot root. Fontconfig's compiled template directory also needs
to exist inside that sysroot; overriding its main configuration alone is insufficient.
This records the reviewed closure evidence; a candidate/startup-only installation
does not establish engraving qualification. `dynamic-elf` also
requires `loader` and `library_dirs`, while `dynamic-library` requires
`library_dirs`. The adapter checks every manifest ELF file and its recursively
needed libraries, including declared runtime-loaded libraries, and runs through
the captured loader with its cache disabled. Origin-relative ELF RPATH/RUNPATH
are accepted only when they remain within the private snapshot. This check does
not discover undeclared runtime-loaded plugins, fonts, Java modules or other data:
the reviewed manifest must include all consumed resources. Configured executable
paths alone do not qualify a closure. Do not substitute an arbitrary tool to
bypass that boundary.

Managed script routes include score inspection, music analysis, vocal planning,
lyrics syllabification, Flow instruction formatting, arrangement-brief
compilation, JJazzLab execution, FluidSynth rendering, self-contained review-bundle
publication, browser verification, acquisition and score conversion, and optional
model-backed synthesis. Assembly and external tools require reviewed resource
closures satisfying the boundary above.
Consult the inventory for the full current list and runtime prerequisites.
Brief compilation consumes five
exact inputs (`brief`, `research`, `source_xml`, `baseline_parameters`,
`baseline_midi`) and publishes `execution_plan.json` plus `PROMPT.md` together.
Bookkeeping rewrites embedded paths only in its private execution copy. Its
success does not qualify subsequent JJazzLab execution or rendering on this host;
those managed adapters still require compatible complete external resources and
real musical verification. No RVC implementation/model has been selected; use
the prepared manual handoff/import route with exact vocal and model provenance.
There is no generic automated RVC adapter.
Live image API adapters remain disabled by automatic approval review. Offline
response-publication tests do not enable API calls or certify provider output.

## Configuration and identity

Run `env/bin/python -m scripts.read_config` from the checkout. Configure
`bookkeeping.actor_id` and a machine-stable UUIDv4 `bookkeeping.host_id` in local
TOML. Resource-consuming work additionally requires the private resource cache
described in [configuration](configuration.md#artifact-bookkeeping).

The data root contains immutable `ledger/<event_id>.json` and
`history/<artifact_id>/<revision_id>/` records, isolated `work/<run_id>/`
operations, and browsing views under `songs/` and `shared/`. Full UUIDs identify
records. Directory labels and suffixes are conveniences, never revision selectors.
Indexes under `catalogue/<host_id>/` can be rebuilt. There is no authoritative
per-artifact sidecar, automatic cleanup or history garbage collector.

## Import and manual production API

Use the checkout's Python environment; examples below run from its root. All
filesystem examples belong under the configured data root unless they are the
original external import source. Imports copy files and retain the originals.

```python
from pathlib import Path
import sys
from scripts.read_config import ROOT, load_config

sys.path.insert(0, str(ROOT / '.agents/skills/artifact-bookkeeping/scripts'))
from artifact_ledger import Ledger

ledger = Ledger(load_config())
song = ledger.create_song("Example song")
completed = ledger.import_files(
    {"source.pdf": Path("/confirmed/existing/source.pdf")},
    kind="source", label="First source", song_ids=[song["song_id"]],
    origin={"source_url": None, "notes": "Existing file; earlier provenance unknown"},
)
update = completed["data"]["updates"][0]
source = {
    "artifact_id": update["artifact_id"],
    "revision_id": update["revision"]["revision_id"],
}
```

Importing the same bytes again intentionally records a new acquisition. Select a
specific source revision; multiple sources are alternatives, not a newest-wins
list. Keep known origin evidence and explicit unknowns in the producer record.

For a manual plan, builder, GUI edit or external handoff, use the same central
operation as ordinary commands, with `command: None`:

```python
dependency = {**source, "files": ["source.pdf"], "purpose": "source evidence"}
from ledger_execution import prepare, status, handoff, finish

intent = prepare(ledger, {
    "operation": "write-plan", "skill": "score-to-musicxml",
    "declaration": ".agents/skills/score-to-musicxml/SKILL.md",
    "code": [], "inputs": {"source": dependency},
    "outputs": {"plan": {
        "kind": "plan", "label": "Transcription plan",
        "song_ids": [song["song_id"]],
        "storage_parent": source["artifact_id"],
        "dependencies": ["source"],
        "contract": {"files": [{"path": "plan.json", "role": "plan"}]},
    }},
    "command": None, "handoff": "Agent writes a plan from the prepared source",
})
handoff(ledger, intent["run_id"])
bindings = status(ledger, intent["run_id"])["plan"]["bindings"]
output = Path(bindings["output:plan"])
# Inspect bindings["input:source"], then write this exact slot.
(output / "plan.json").write_text('{"decision": "record the actual plan"}\n')
handoff(ledger, intent["run_id"], {"evidence": "Observed the completed plan write"})
completed = finish(ledger, intent["run_id"])
```

Pass actual executed builder/code paths through the request's `code` list.
The helper captures a separate immutable code snapshot; a Git commit by itself
does not capture dirty code. Commands and settings must be portable and redacted.
Do not invent an executable, model version or tool identity for a manual action.
Keep reusable intermediate outputs in separate bounded operations when their exact
revision is needed by later work.

Fresh experiments use `action="create"` (the default). Only an explicit revision
uses `action="revise"`, `base={"artifact_id": ..., "revision_id": ...}` and the
new output contract. The base must still be current. A branch from older work is
a new artifact with `branched_from` and separately declared consumed dependencies.

## Ordinary commands through bookkeeping

Production scripts have no ledger imports, flags or callbacks. Load their
`SKILL.md` Bookkeeping block and translate its declarations into the following
central operation. The inventory is an audit record, not a dispatch registry.
A new ordinary CLI needs only its normal interface and Bookkeeping block.

Use `ledger_execution.py` in the bookkeeping skill's `scripts/` directory:

```text
env/bin/python .agents/skills/artifact-bookkeeping/scripts/ledger_execution.py prepare REQUEST.json
env/bin/python .agents/skills/artifact-bookkeeping/scripts/ledger_execution.py execute RUN_ID
env/bin/python .agents/skills/artifact-bookkeeping/scripts/ledger_execution.py finish RUN_ID
```

`--config-root DIR` selects an explicit test configuration. Put request files and
retained operation evidence below the resolved data root. `status RUN_ID` returns
the immutable intent, allocated bindings, execution marker, result receipt and
ledger status. Preparation never executes the producer. Execution never publishes.
Finish verifies and publishes; it never repeats execution. Store the returned run
ID and use status on resumption. Public Python equivalents are
`prepare(ledger, request)`, `execute(ledger, run_id)`, `finish(ledger, run_id)` and
`status(ledger, run_id)` from `ledger_execution`.

A syllabification request has this shape (replace the exact revision references):

```json
{
  "operation": "syllabify-lyrics",
  "skill": "syllabify_lyrics",
  "declaration": ".agents/skills/syllabify_lyrics/SKILL.md",
  "code": [
    ".agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py",
    ".agents/skills/syllabify_lyrics/scripts/lyrics_syllabify.py"
  ],
  "inputs": {
    "text": {"artifact_id": "EXACT_ARTIFACT_UUID", "revision_id": "EXACT_REVISION_UUID",
             "files": ["lyrics.txt"], "purpose": "approved lyric text"}
  },
  "outputs": {
    "lyrics": {"kind": "lyrics", "label": "First option", "song_ids": [],
               "dependencies": ["text"],
               "contract": {"files": [{"path": "lyrics.json", "role": "lyrics"}]}}
  },
  "settings": {"language": "en"},
  "command": ["{python}", "{code:.agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py}",
              "{input:text}", "--lang", "en", "--out", "{output:lyrics/lyrics.json}"]
}
```

Capture the entire executed helper tree, imported schemas/templates and declaration
source. The central configuration helpers are included automatically. `code` paths
are relative to the checkout; external packages/resources are separate snapshots.
The effective request is persisted in immutable producer settings, including local
modifications and options. The child uses captured code and declared Python
packages with `-I -S -B`, with no live package or checkout fallback. Interpreter,
standard library and operating system remain observed platform boundaries.

Bindings occupy a complete argv item or configuration value, never shell text:

| Binding | Meaning |
| --- | --- |
| `{input:name}` | Selected file, or directory for a multi-file input. `{input:name/file}` selects a declared file. |
| `{output:name/file}` | File in that output's allocated slot. For bundle writers use a new subdirectory and prefix the contract files accordingly. The slot itself already exists. |
| `{code:relative/path}` | Captured project source/schema/template. |
| `{resource:name/path}` | File/directory covered by a pinned resource descriptor. |
| `{tool:name}` | Validated private tool argv; expands as a list in commands or configuration. |
| `{scratch:relative/path}` | Disposable run-local path. |
| `{document:name}` | Execution-only JSON copy with explicit embedded path substitutions. |
| `{layout:name}` | Execution-only directory containing explicitly mapped input files. |

`resources` maps names to exact descriptor `{artifact_id, revision_id}` references.
`packages` lists consumed Python distributions; bookkeeping captures their installed
closure from `resources.python_packages`. `config` contains only the producer's
needed settings, with tools/resources bound to snapshots, for example
`{"tools":{"ffmpeg":{"command":"{tool:ffmpeg}"}}}`. It becomes the child's
`MUSIC_VIDEO_CONFIG_JSON`; data-root configuration is supplied centrally.
`environment` holds explicitly declared, nonsecret behavior settings. Loader,
Python and configuration overrides are rejected. Tool preferences and temporary
files go to scratch. Native conversion profiles supply their reviewed font/Qt
closure. Credentials must never appear in persisted operation settings; use an
external handoff for credential-bearing provider calls.

Expand every indirect input before preparation, following the production skill's
path rules. For a data-root-relative clip map, pin the map and each clip, then use:

```json
{"documents": {"clips": {"input": "clips", "bindings": {
  "/0/file": "{input:clip1}", "/1/file": "{input:clip2}"
}}}}
```

Keys are JSON pointers. Preparation checks each original path against the selected
input bytes. Only the execution copy changes; the source map stays immutable.
Directory manifests can use `layouts`, for example
`{"baseline":{"parameters.json":"{input:parameters}","song.mid":"{input:midi}"}}`.
A layout may contain a rewritten document via `{document:name}`. When a persisted
manifest references the directory, import the original directory's complete
bounded files as one bundle so the directory maps to a single immutable history
location. Do not publish a temporary layout as a sole dependency reference.

Ordinary tools that produce a directory containing several independently revised
results can write that directory to scratch. `collect` maps each declared output
file token to its exact generated scratch/output source token. Bookkeeping copies
those files without clobbering destinations only after command success, then
checks every output contract. `path_aliases` maps an explicitly generated scratch
directory to a collected output directory so persisted folder manifests resolve
there. Use a complete folder bundle depending on the separately published native,
MIDI and verification artifacts when a downstream ordinary tool requires a single
folder. Collection is generic; no per-skill extraction adapter is registered.

Each output declares its own input names in `dependencies`. A sibling edge is
`{"output":"audio","files":["audio.wav"],"purpose":"prepared soundtrack"}`.
For Flow, audio depends on settings/audio; film additionally depends on map/clips
and prepared audio; timeline depends on all those plus film. `storage_parent` may
be `{"output":"film"}` when that is an actual dependency. Ordinary ledger
`action`, `base` and `branched_from` fields retain their exact revision semantics.
For analysis/planning provenance, `relations` supports
`[{"input":"analysis","depends_on":"score"}]`; mismatches stop preparation.

`publish_json` lists output tokens whose path strings must resolve after
publication, such as `["{output:timeline/timeline.json}"]`. Bookkeeping rewrites prepared input/output/document paths to exact
immutable history paths, preserving original manifests. When a domain JSON also
stores a hash of such a path, `publish_hashes` explicitly declares its JSON pointers:
`[{"file":"{output:variant/parameters.json}","path":"/child_plan","sha256":"/child_plan_sha256"}]`.
`publish_text` separately lists declared UTF-8 output text/property files whose
prepared path strings must become immutable history references. Bookkeeping keeps
the original successful bytes and derives the permitted transformations from
those bytes and the immutable operation; changed transform journals stop before
any writes. The referenced dependency must already be published. Undeclared hashes are never
guessed or edited. Check final manifests before downstream consumption.

For manual writing, GUI edits and external operations use the same request with
`command: null`, a concrete `handoff` description, and the same I/O/resources.
Call `handoff RUN_ID` before the action; inspect status for allocated paths.
After witnessing the outcome, call `receipt RUN_ID --receipt RECEIPT.json` with
actual result identities, files/hashes and nonempty `evidence`, then `finish`.
Python API: `handoff(ledger, run_id)` and `handoff(ledger, run_id, receipt)`.
A started handoff with no receipt is uncertain: inspect the external result or
stop for the missing evidence. Never repeat it merely because a tool response
was lost. Record a failed handoff with `ledger.fail` when failure is known.

A failed command records exit status, stdout/stderr and failure, retaining partial
files without publication. Extra/missing deliverables also fail the whole output
set. A launch marker prevents rerunning the same attempt; a new attempt requires
fresh preparation. After successful execution interrupted before publication,
`finish` resumes publication. After completion it repairs the browsing view only.
Unknown edits stop repair and survive. Do not bypass execution uncertainty with
raw `ledger.finalize`; inspect and reconcile the persisted operation first.

## Failure, recovery and queries

`ledger.finalize(run_id)` validates the complete output set and publishes once.
`ledger.recover(run_id)` resumes that same publication using its saved IDs and
event bytes. It does not rerun the musical tool or repeat an external generation.
Recovering after completion repairs the browsing view only. Missing output files,
changed inputs/resources, stale bases and unexpected local edits stop publication
or repair; preserve the evidence and resolve the stated problem.

`ledger.resolve(artifact_id, revision_id)` resolves an exact immutable revision.
Omitting a revision requires an unambiguous current head. Inspect the returned
availability instead of treating registration as proof that synchronized bytes
are already present. Query history and dependencies through the ledger; filesystem
ancestry does not reveal which revision an arrangement or film consumed.

For a historical causal view, construct
`Ledger(config, frontier=["<event UUID>", ...])`. Queries include those events and
their ancestors regardless of timestamps or file arrival order. This instance is
read-only: historical state cannot serve as a stale mutation base. Use a fresh
default `Ledger(config)` for current-state changes. Exact revision lookup remains
available independently of current selection.

Reviews, selections, withdrawal and metadata changes append events. Selection
never deletes alternatives or regenerates downstream artifacts. A withdrawn,
missing or conflicted selection remains visible as that state. Explicit historical
lookup can still retrieve verified bytes when current state conflicts. Use the CLI
help (`env/bin/python .agents/skills/artifact-bookkeeping/scripts/artifact_ledger.py --help`) for retrieval, reconciliation,
catalogue and metadata commands supported by this checkout.

Portable owned filenames use ASCII letters/digits, `.`, `_` and `-`, start with a
letter/digit, and are at most 64 characters. They preserve required case (for
example `PROMPT.md`) but reject case-insensitive collisions and device names.
Paths cannot escape the data root through traversal or links. Both relative and
absolute path limits are checked before publication and after root relocation.
Rename unsupported imports explicitly; preserve original bytes and names, and
remap embedded references only in an execution copy.

## Verification scope

Synthetic tests exercise ledger contracts and supported producer boundaries using
temporary data, independent of this machine's configuration and production assets.
They do not certify external installations, human source/listening/video review,
paid image/clip services, or a fresh host's discovery of the workflow. The final
interactive plan must record each of those checks as passed, failed or blocked;
missing capabilities and human checkpoints remain blocked rather than passed.
