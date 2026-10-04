# Artifact bookkeeping plan

Updated 2026-10-04. Design only; no ledger, skill integration or Dropbox migration
has been implemented. The remaining decisions are listed once at the end.

Build one bookkeeping skill with shared Python helpers to organize artifacts,
preserve their provenance and retrieve them across sessions. Adapt file handling
in every retained skill; preserve the collaborator skills' musical/visual methods.
See [workflow contracts](artifact-contracts.md) for production-specific requirements.

## 1. Storage and identity

Resolve `paths.data_root` through `bin.read_config`; machine settings stay in
`config.local.toml`. The global ledger lives at `<data_root>/ledger/`, with one
immutable JSON file per event. It is the only provenance authority. Search indexes
and browsing views are rebuildable; no authoritative per-artifact sidecars or
shared SQL database are needed.

Each artifact has its own directory. Derived artifacts nest under a chosen primary
input; the ledger records **all** inputs, including those elsewhere in the tree.

~~~text
song/
  x/
    source.pdf
    xml-a/
      score.musicxml
      arrangement-a/
        arrangement.mid
        render-a/
          full.wav
          backing.wav
    xml-b/
      score.musicxml
  y/
    source.pdf
~~~

| Identity/action | Rule |
| --- | --- |
| Song | Stable `song_id`; may have several sources. Shared resources can have zero or several song associations. |
| Artifact | Stable `artifact_id`; owns a directory and an explicit file list, excluding descendant artifacts. |
| Revision | Same artifact/directory, new `revision_id`; replaces visible owned files and preserves previous bytes. |
| Version | New artifact/directory, retained alongside the original; records the source artifact/revision. |
| Dependency | Exact artifact/revision plus selected file or role. Changing a parent never changes an existing child's recorded inputs. |

Bundle files only when they share direct inputs and are revised together.
Otherwise use separate artifacts—for example, editable projects, exported MIDI
and verification reports. A report depends on the revision it checks. Full/backing
audio may form one render bundle when produced together from the same inputs.

Storage rules:

- Preserve immutable bytes for every revision, including imports. Current browsing
  files are a replaceable view; historical lookups never resolve through them.
- Choose storage placement on creation; changing dependencies does not move an
  artifact. A managed move records the complete subtree path mapping and preserves
  identities. Relocating the data root requires no ledger path changes.
- Store `path` and `history_path` relative to the data root; `files[].path` is
  relative to the artifact/revision directory. Use `/` separators. Reject absolute/drive/UNC paths,
  traversal, escaping links, reserved management locations, overlapping ownership,
  and file/directory or case-insensitive collisions. Use collision-resistant IDs,
  not locally allocated “next version” numbers.
- Revision replacement touches only owned files. Retire removed files from the
  old manifest after preserving them; leave descendants and unknown files intact.
- Withdrawal preserves history. Permanent history deletion is outside the initial
  implementation; workspace cleanup cannot delete registered bytes or events.

## 2. Ledger contract

Implement JSON Schema plus semantic validation. The following is the draft record
shape; field meanings must stay consistent across Python, CLI and skill instructions.

| Record | Fields |
| --- | --- |
| Event envelope | `schema_version`, `event_id`, `event_type`, `recorded_at` (UTC), `actor`, `previous_events` (causal predecessors), `expected_heads` (state being changed), `data`. |
| Artifact update | `action` (create/revise), `artifact_id`, `kind`, `label`, `song_ids`, `path` at this event, `storage_parent`. |
| Revision | `revision_id`, immutable `history_path`, `files` (bundle-relative path, role, SHA-256), `dependencies`, `producer`; `previous_revision_id` or `branched_from` where applicable. |
| Dependency | `artifact_id`, `revision_id`, selected files/roles, purpose. |
| Producer | `run_id`, operation, skill/entrypoint, actual code snapshot, command, effective settings, tool/model/resource identities. |

An `operation.completed` event contains **all** artifact updates from one bounded
run. Other events cover start/failure/abandonment, song creation, metadata/provenance
corrections, subtree moves, reviews, selections, withdrawal and conflict resolution.

Record source URLs, retrieval time, source-page selections and available origin/license
evidence for imports. Register reusable prompts, builders and settings; reference
large records by revision/hash rather than duplicating them. A Git commit alone
does not describe modified working-copy code. Record unknown provenance honestly
and omit credentials. Corrections retain prior claims and cannot change bytes or
hashes under an existing revision ID.

Replay and validation:

- Apply causal order, never timestamp/filename/arrival order. Check expected state
  for revisions, locations, metadata and selections. Independent changes coexist;
  competing changes to the same entity/field remain conflicts. Resolution identifies
  all competing heads it resolves.
- Missing predecessors/files mean pending synchronization. Invalid records, hash
  mismatches and unsupported schemas are distinct errors; do not silently omit
  them and claim a complete view.
- An identical event ID/content is an idempotent duplicate; different content under
  one ID is an integrity error. Publish each JSON event atomically locally; Dropbox
  delivery is not an atomic transaction.
- Validate dependency existence and cycles between exact revisions. Depending on
  an earlier revision of the same artifact is valid.

## 3. Common operation lifecycle

| Step | Required behavior |
| --- | --- |
| **Prepare** | Resolve configuration and exact inputs; allocate run/output IDs and working paths; record intent and expected heads. Supply verified immutable inputs or isolated copies, never mutable browsing paths. Editors receive writable copies. |
| **Produce** | Run the existing tool in its prepared workspace. Record actual settings and resources. Temporary scratch files need no artifact records; reusable checkpoints do. |
| **Finalize** | Check input integrity, expected heads and the complete output contract. Preserve all output bytes, append one completion event, then update owned browsing files. Verify the view before reporting local completion. |
| **Fail/recover** | Before completion, leave the run pending or record failure. After completion, repair the browsing view without creating another revision. Retries reuse IDs and compare existing bytes/event contents. Never overwrite unexpected local edits. |
| **Later changes** | Append metadata, review, selection, move or withdrawal events when the action occurs. |

Use separate runs for reusable stages and manual handoffs, not one transaction for
an entire video. A partly written output set is not a completed run. Local stale-base
checks are not distributed locks: preserve concurrent revisions and require explicit
resolution before choosing a current browsing result.

Require explicit file inputs and either an output file or an output directory with
declared files/roles or discovery rules. Reject missing/unexpected publishable outputs.
Bookkeeping chooses paths; users can still request a song/style without filenames.
Adapt hardcoded destinations—changing working directory cannot redirect absolute
paths. Include dependencies hidden in briefs, model configuration or directory scans.
File differences alone cannot prove which inputs a tool consumed.

## 4. Enforce usage in every skill

Create the bookkeeping skill and Python API/CLI first, then add the `AGENTS.md`
rule and update every skill's instructions and command examples.

1. Maintain a machine-checkable inventory of all skills and entrypoints, classified
   as managed, manual-managed, read-only or unavailable/reference-only. New or
   unclassified entrypoints fail the coverage check; optional skills are included.
2. Every public producer enters prepare/finalize/failure itself. Internal helpers
   either do the same or accept only allocated workspaces. Only the shared publisher
   writes registered history, current files and ledger events.
3. Agent-written files, GUI edits, API generations and downloaded external results
   use the same prepare/import/finalize boundary. Read-only inspection needs no
   write event; persisted reports and review decisions do.
4. Cover `bin/*`, direct scripts, `.claude/skills` aliases, nested adapters and tool
   launchers. A wrapper is not covered until its callees are. Unavailable routes
   stop before writes or external generation calls.
5. Adapt or explicitly disable legacy writers in `scripts/`, `adapter_code/` and
   JJazzLab trials. Include the combined `analyze_inputs` command; exclude raw
   `clear_downloads` deletion from managed-data operations.

Instructions guide agents; Python and entrypoint tests enforce supported workflows.
They cannot prevent arbitrary shell writes. Reconciliation detects unmanaged or
altered files and offers explicit import/revision without inventing missing history.

| Retained skill | Adapter work |
| --- | --- |
| `score-to-musicxml` | Register source pages, geometry, transcription/builders, XML and external editor outputs; pin exact revisions for engraving, playback and review. |
| `song-arrangement-research` | Resolve research, XML, baseline project/MIDI/parameters and libraries; register compiled plans, native projects, MIDI and renders; adapt historical destinations. |
| `barnsang-video` | Pin storyboard/prompts, character/continuity references, audio and clip selections; register generated images, Flow kits/imports, timelines and films. Preserve old kits on replacement. |
| `download-scores` | Replace `assets/` defaults and direct overwrite/reuse; separate source imports from conversions, extracted lyrics and reports. |
| `analyze-music` | Wrap exact score/options → analysis JSON. |
| `syllabify-lyrics` | Wrap exact lyrics/language → lyrics JSON. |
| `plan-vocals` | Register analysis, lyrics and actual score → events; require analysis and score revisions to match. |
| `synthesize-vocal-with-diffsinger` | Capture actual backend/model/resources, WAV/debug/log outputs and required intermediates; identify placeholder results explicitly. |
| `refine-vocal-with-rvc` | Provide a managed external/manual adapter for rough vocal + model/index → refined vocal/log. The suggested CLI is not implemented in the repo. |

## 5. Retrieval

Provide human-readable and JSON results for:

- List/filter by song, kind, label, role, review, selection and availability.
- Resolve an ID or registered path to an exact revision; reject ambiguous choices.
- Show history, producer, direct/transitive inputs and downstream consumers.
- Report pending, conflicted, missing, altered and unmanaged artifacts.
- Rebuild the catalogue and browsing view from ledger events and preserved bytes.

Keep registered, available/verified, current, reviewed and selected as separate
properties. Reviews/selections pin revisions and purpose; publishing does not imply
approval. Show when a render uses an older input without silently regenerating it.
Historical queries use causal event state rather than assuming clocks define order.

## 6. Build order and acceptance

| Stage | Deliverable and exit check |
| --- | --- |
| 1. Freeze layout/schema | Resolve the decisions below; write JSON Schema and representative event examples. |
| 2. Build shared core | Config resolution, validation/replay, allocation, revision resolution, publication/recovery and metadata operations pass fixture tests. |
| 3. Expose bookkeeping | Skill instructions and Python API/CLI cover the lifecycle, retrieval and reconciliation. Import existing files, recording known provenance and marking unknown details. |
| 4. Integrate all skills | Update `AGENTS.md`, inventory, examples and adapters. Enable each production entrypoint only after its boundary tests pass. |
| 5. Validate production | Run one representative song with the required source, listening and video reviews. |

Acceptance checklist:

- All nine skills and public entrypoints are classified; new omissions fail.
- Alternate working directory and relocated root with spaces work; wrong paths,
  missing context, escaping links and collisions fail before production.
- Fixture: two sources, XML alternatives/revisions, project/MIDI checkpoints,
  branching arrangements/renders, shared resources and a multi-parent video.
  Historical dependencies, selections and downstream lookup remain correct.
- Changing browsing files after prepare does not change consumed inputs.
  Altered snapshots and score/analysis mismatches are rejected.
- Missing sidecars, extra outputs, hidden subprocess failures, interruptions and
  retries cannot publish partial bundles or duplicate events.
- Reordered/partial sync, duplicate/corrupt events and concurrent revisions,
  metadata, moves and selections produce explicit states and resolvable conflicts.
- Revising a parent/removing owned files preserves descendants. Subtree moves,
  root relocation and Flow-kit replacement preserve historical lookup.
- Catalogue/view rebuild and reconciliation preserve unknown edits. Test manual/API
  boundaries with fixtures; paid generation is unnecessary for bookkeeping tests.

Existing tests do not establish ledger enforcement. Synthetic acceptance checks
verify bookkeeping; stage 5 verifies musical/visual quality.

## 7. Decisions to settle before coding

1. **Layout:** exact song/shared-resource/history/work/catalogue locations, portable
   naming and path-length rules, multi-input placement, and how externally installed
   models/libraries become shared pinned resources. Use a simple revision directory
   for `history_path`; deduplication is optional. `ledger/` at the root is fixed.
2. **Schema:** exact event names/payloads and expected-state rules; distinguish causal
   `previous_events` from mutation preconditions in `expected_heads`. Confirm bundle
   boundaries using the stage-1 examples, including checks, clips and Flow kits.

No artifact migration or pipeline execution occurs during this planning step.
