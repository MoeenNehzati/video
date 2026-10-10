# Artifact bookkeeping plan

> Historical planning baseline (2026-10-08). Implementation-status statements below
> describe that snapshot. For current capabilities and execution instructions, use
> [the usage guide](artifact-ledger-usage.md) and
> [the execution coverage documentation](artifact-ledger-entrypoints.md).

Updated 2026-10-08. Implementation design; no ledger, skill integration or data
migration is implemented. Layout, event semantics and current entrypoints are
specified below and in the linked contracts.

Build one bookkeeping skill with shared Python helpers to organize artifacts,
preserve their provenance and retrieve them across sessions. Adapt file handling
in every retained skill; preserve the collaborator skills' musical/visual methods.
See [workflow contracts](artifact-contracts.md) for production-specific requirements,
[the event contract](artifact-ledger-contract.md) for state transitions, and
[the entrypoint inventory](artifact-ledger-entrypoints.md) for integration coverage.
[Worked examples](artifact-ledger-examples.md) show the nested layout and expected
behavior; turn their checks into fixtures during implementation.

## 1. Storage and identity

Resolve `paths.data_root` through `scripts.read_config`; machine settings stay in
`config.local.toml`. The global ledger lives at `<data_root>/ledger/`, with one
immutable JSON file per event. It is the only provenance authority. Search indexes
and browsing views are rebuildable; no authoritative per-artifact sidecars or
shared SQL database are needed.

Each artifact has its own directory. Derived artifacts nest under a chosen primary
input; the ledger records **all** inputs, including those elsewhere in the tree.

| Location under `data_root` | Purpose |
| --- | --- |
| `ledger/<event_id>.json` | Immutable event records; single provenance authority. |
| `history/<artifact_id>/<revision_id>/` | Immutable owned files, independent of browsing paths. |
| `work/<run_id>/{inputs,outputs,scratch}/` | Isolated operation workspace; durable intent and publication journal alongside these directories. |
| `songs/<song-dir>/...` | Browsable source and derived artifact directories, including sibling experiments. |
| `shared/<artifact-dir>/...` | Reusable or multi-song artifacts; explicit song associations. |
| `catalogue/<host_id>/` | Disposable indexes keyed to the observed event frontier; never authoritative. |

For example, `songs/ekorrn--<suffix>/source--<suffix>/xml--<suffix>/`
contains a score and sibling arrangement directories; each arrangement can contain
several render directories. Human labels remain unrestricted metadata. The directory
suffix is the first 12 hex characters of its UUID; generated slugs are at most eight
ASCII characters. Full UUIDs identify records; short suffixes are only names.

Generated directory slugs are lowercase. Owned file components allow ASCII letters
in either case, digits, `.`, `_` and `-`,
start with a letter/digit, and are at most 64 characters. Reject device names,
trailing dots/spaces and case-insensitive collisions. Record original import names.
Limit data-root-relative paths to 200 characters and resolved absolute paths to
240 UTF-16 code units, including workspace/history paths. External adapters may
require stricter limits. Check before side effects and on root relocation; an
unsupported path stops with an actionable error, never a silent move or truncation.
Use short input slots such as `inputs/i0001/`, mapped to exact revisions in intent.
Preserve tool-required file spelling (for example `PROMPT.md`); validate casefold
uniqueness. An import needing renamed files must map embedded references in an
execution copy, preserving original bytes in history and original names in provenance.

Sources go under their song; derived outputs name an explicit primary dependency
and nest under that artifact's browsing directory. A multi-input video may use its
storyboard as primary; all audio, image and clip inputs remain dependencies.
Shared/multi-song roots have no storage parent. Creation fixes placement: a changed
input does not move an existing artifact. Alternatives normally share the same
primary parent; branch ancestry need not be the storage parent.

| Identity/action | Rule |
| --- | --- |
| Song | Stable `song_id`; may have several sources. Shared resources can have zero or several song associations. |
| Artifact | Stable `artifact_id`; owns a directory and an explicit file list, excluding descendant artifacts. |
| Revision | Same artifact/directory, new `revision_id`; replaces visible owned files and preserves previous bytes. |
| Version | New artifact/directory, retained alongside the original; records the source artifact/revision. |
| Dependency | Exact artifact/revision plus selected file or role. Changing a parent never changes an existing child's recorded inputs. |

**Experimentation is the default at every stage.** Another transcription,
arrangement, render, prompt, image, clip take or video assembly allocates a new
`run_id`, new artifact IDs and new revision IDs. Earlier attempts remain browsable,
including unselected results. A variant records `branched_from` when based on an
existing attempt, separately from its actual consumed inputs. Only an explicit
`revise` request replaces visible owned files. A new tool execution is a new run;
recovery reuses IDs solely to finish the same interrupted publication.

Each stage/purpose can select an exact revision within a song or artifact scope.
Selection never removes alternatives; no query silently selects the newest result.
A downstream operation may explicitly choose an unselected experiment, recording
that exact input. Changing a selection never rewrites existing downstream inputs.

Bundle files only when they share direct inputs and are revised together.
Otherwise use separate artifacts—for example, editable projects, exported MIDI
and verification reports. A report depends on the revision it checks. Full/backing
audio may form one render bundle when produced together from the same inputs.

Storage rules:

- Preserve immutable bytes for every revision, including imports. Current browsing
  files are a replaceable view; historical lookups never resolve through them.
  External installations use the resource-descriptor exception below.
- Choose storage placement on creation; changing dependencies does not move an
  artifact. A managed move records the complete subtree path mapping and preserves
  identities. V1 moves rename a subtree while preserving storage-parent relations
  and its song/shared root; reparenting is out of scope. Relocating the data root
  requires no ledger path changes, subject to the path-length checks above.
- Store `path` and `history_path` relative to the data root; `files[].path` is
  relative to the artifact/revision directory. Use `/` separators. Reject absolute/drive/UNC paths,
  traversal, escaping links, reserved management locations, overlapping ownership,
  and file/directory or case-insensitive collisions. Use collision-resistant IDs,
  not locally allocated “next version” numbers.
- Revision replacement touches only owned files. Retire removed files from the
  old manifest after preserving them; leave descendants and unknown files intact.
- Withdrawal preserves history. Permanent history deletion is outside the initial
  implementation; workspace cleanup cannot delete registered bytes or events.

External tools, models and libraries remain outside the repository. Register a
shared resource descriptor containing a portable TOML key, version/source evidence
and a complete manifest of the files the adapter consumes, with sizes and hashes.
Its revision preserves the descriptor, not the installed binaries. Configure the
actor label in `bookkeeping.actor_id` and a machine-stable random UUIDv4 in
`bookkeeping.host_id` in local TOML; the latter namespaces local caches/journals. Resolve local
installations through TOML; never put machine-specific absolute paths in identities.
Before production, copy/reflink and verify the consumed resource set into a private
cache at `paths.resource_cache`, configured outside the repo and synchronized data
root. Never hardlink mutable installations. Use only that snapshot and verify it
afterwards; tools needing undisclosed mutable files are unavailable until adapted.
A cached descriptor is not proof that historical resource bytes are available:
missing/mismatched resources stop reuse without substituting a newer installation.
Preserve resource-internal case and filenames required by the tool; generated-name
rules apply to cache containers, not to rewriting installed resources. Reject unsafe
or platform-incompatible resource paths rather than renaming them. Credentials and
mutable tool preferences are not part of the resource snapshot.

## 2. Ledger contract

Implement JSON Schema plus semantic validation from the [event contract](artifact-ledger-contract.md).
These records share one meaning across Python, CLI and skill instructions:

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

- Apply causal order, never timestamp/filename/arrival order. Validate expected heads
  against each event's causal ancestors, not replay arrival order. Check expected state
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
4. Cover canonical Python entrypoints, shared helpers, nested adapters and configured
   external tools. A caller is not covered until its callees are. Unavailable routes
   stop before writes or external generation calls.
5. Classify every current mode and call edge in the [entrypoint inventory](artifact-ledger-entrypoints.md).
   The removed `analyze_inputs` and `clear_downloads` commands are not integrations.
   Internal Java writers accept allocated workspaces only; raw external invocations
   are not automatically protected by `scripts.read_config --run`.

Instructions guide agents; Python and entrypoint tests enforce supported workflows.
They cannot prevent arbitrary shell writes. Reconciliation detects unmanaged or
altered files and offers explicit import/revision without inventing missing history.

| Retained skill | Adapter work |
| --- | --- |
| `score-to-musicxml` | Register source pages, geometry, transcription/builders, XML and external editor outputs; pin exact revisions for engraving, playback and review. |
| `song-arrangement-research` | Resolve research, XML, baseline project/MIDI/parameters and libraries; register compiled plans, native projects, MIDI and renders; remap embedded paths to allocated workspaces. |
| `barnsang-video` | Pin storyboard/prompts, character/continuity references, audio and clip selections; register generated images, Flow kits/imports, timelines and films. Preserve old kits on replacement. |
| `download-scores` | Wrap current explicit-path downloads; separate source imports, conversions, extracted lyrics and reports, preserving repeated acquisitions. |
| `analyze-music` | Wrap exact score/options → analysis JSON. |
| `syllabify-lyrics` | Wrap exact lyrics/language → lyrics JSON. |
| `plan-vocals` | Register analysis, lyrics and actual score → events; require analysis and score revisions to match. |
| `synthesize-vocal-with-diffsinger` | Capture actual backend/model/resources, WAV/debug/log outputs and required intermediates; retain current fail-closed backend behavior; there is no placeholder fallback. |
| `refine-vocal-with-rvc` | Provide a managed external/manual adapter for rough vocal + model/index → refined vocal/log. No local RVC executable is provided; use the configured external/manual route. |

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
| 1. Encode contracts | Implement the specified JSON Schema, semantic checks and example fixtures; refresh the entrypoint inventory against the implementation checkout. |
| 2. Build shared core | Config resolution, validation/replay, allocation, revision resolution, publication/recovery and metadata operations pass fixture tests. |
| 3. Expose bookkeeping | Skill instructions and Python API/CLI cover the lifecycle, retrieval and reconciliation. Provide explicit import, recording known provenance and marking unknown details; no automatic bulk migration. |
| 4. Integrate all skills | Update `AGENTS.md`, inventory, examples and adapters. Enable each production entrypoint only after its boundary tests pass. |
| 5. Interactive end-to-end acceptance | Execute the [interactive validation plan](artifact-ledger-validation-plan.md) as the final implementation step: fresh, uncoached producer/consumer subagents, independent verification and human source/listening/video checkpoints. Defer unavailable human checkpoints during unattended execution; report missing stages as blocked, not passed. |

Acceptance checklist:

- All nine production skills plus the new bookkeeping skill, public modes and call edges are classified; new omissions fail.
- Alternate working directory and relocated root with spaces work; wrong paths,
  missing context, escaping links and collisions fail before production.
- Fixture: two sources, XML alternatives/revisions, project/MIDI checkpoints,
  branching arrangements/renders, shared resources and a multi-parent video.
  Include repeated attempts at every stage and both failed and successful runs.
  Historical dependencies, selections and downstream lookup remain correct; fresh
  attempts preserve siblings, while publication recovery creates no duplicate attempt.
- Changing browsing files after prepare does not change consumed inputs.
  Altered snapshots and score/analysis mismatches are rejected.
- Missing sidecars, extra outputs, hidden subprocess failures, interruptions and
  retries cannot publish partial bundles or duplicate events.
- Reordered/partial sync, duplicate/corrupt events and concurrent revisions,
  metadata, moves and selections produce explicit states and resolvable conflicts.
- Revising a parent/removing owned files preserves descendants. Subtree moves,
  root relocation and Flow-kit replacement preserve historical lookup.
- External resource snapshots detect changing installations and missing historical
  bytes; verify resource descriptors separately from resource availability.
- Catalogue/view rebuild and reconciliation preserve unknown edits. Test manual/API
  boundaries with fixtures; paid generation is unnecessary for bookkeeping tests.

Existing tests do not establish ledger enforcement. Synthetic acceptance checks
verify bookkeeping. Stage 5 verifies that ordinary agents discover and use the
project instructions and skills correctly across sessions, as well as checking
artifact behavior and musical/visual quality. Do not declare implementation
accepted until that plan's required cases pass on the final implementation snapshot.

## 7. Implementation boundaries

Create `.agents/skills/artifact-bookkeeping/SKILL.md` and its `schema/event.schema.json`.
Use `.agents/skills/artifact-bookkeeping/scripts/artifact_ledger.py` as the shared Python API and CLI (`python
.agents/skills/artifact-bookkeeping/scripts/artifact_ledger.py`), reusing `scripts.read_config` and `scripts.project_runtime`; no shell
launcher or duplicate wrapper. Commands cover song creation, prepare, finalize,
fail/abandon, import, list/resolve/history/inputs/consumers, review/select, metadata,
move/withdraw/resolve-conflict, reconcile and rebuild. Prepare requires an operation
and output contract; create is default, revise requires an exact base revision.

Maintain route restrictions in `docs/artifact-ledger-entrypoints.md`; generate
source inventories under ignored `_build/`. Update existing ownership/provenance
records and repository tests when code is introduced. Keep
current output contracts and musical methods; split multi-stage writers into
bounded managed operations when outputs consume intermediate results.

Implement read-only legacy discovery first. Import selected existing bytes by
copying them into history and the new managed view, leaving originals untouched,
recording unknown provenance and original paths. Resume an import idempotently only
for the same recorded run/intent. Separate imports or experiments can have identical
bytes and still retain distinct identities, sources and provenance.
Bulk relocation, deleting originals, history garbage collection and automatic
"best take" selection are outside the initial implementation. A later migration
requires a reviewed source-to-destination map; this planning change authorizes none.

Do not enable a producer until its declared inputs, outputs, resource dependencies,
negative boundary tests and recovery tests pass. Missing production resources can
block that route without blocking bookkeeping fixtures or other integrations.
No production run or data migration occurs during this planning step.

## 8. Unattended overnight execution

Once launched, continue without routine user questions or stage-by-stage permission.
Consult subagents, fix failures and keep advancing ready tasks. This protocol does
not itself launch a job or provide background execution.

Keep a durable task board under the evaluator data root, separate from producer
inputs; mirror it in session task tools when available. Record status, owner,
dependencies, source snapshot, acceptance evidence, next action and blocker/unblock
condition. Until bookkeeping works, retain it as unregistered coordinator evidence.

| Task | Work; depends on |
| --- | --- |
| T01 | Capture config, Git state, resources and scope; preserve unrelated work. |
| T02 | Schema and worked-example fixtures; T01. |
| T03 | Ledger, queries and conflict handling; T02. |
| T04 | Publication, immutable storage and recovery; T03. |
| T05 | Bookkeeping API/CLI and skill; T03–T04. |
| T06 | Integrate each skill/mode, instructions and ownership; T05. |
| T07 | Independent audits, fixes and rechecks; T02–T06. |
| T08 | Full implementation checks on the frozen snapshot; T07. |
| T09 | Execute the validation plan, recording every case verdict; T08. |
| T10 | Report completed work, evidence, unresolved blockers and next actions. |

Use the acceptance checks above; written code alone does not complete a task.
Update the board after changes, tests, audits and blockers, and before handoff.
On resumption, reconcile Git/config and running workers with the checkpoint before
continuing. Do not duplicate in-flight generation. Parallel work needs disjoint
owners; validation failures create repair tasks and trigger affected requalification.

For unresolved choices, consult two independent advisers; use a third for substantive
disagreement. Choose the smallest contract-compatible solution and record why.
Prefer reversible decisions; missing facts block only dependent tasks. Reuse recorded
choices and confirmed resources. Label any adviser-chosen test-only creative assumptions.

Keep validation producers fresh and uncoached. Repair missing guidance in the repo,
then retest with new agents. Advisers cannot invent facts, grant spending authority,
replace unavailable manual actions or turn their assessments into human approval.
Record missing access/resources/reviews as blockers and continue independent work.
Preserve existing scope, data and permission boundaries; no unsolicited commit/push.

Stop only when work is complete, no authorized task can advance, or the host forces
a stop. Save a resumable checkpoint and batch unresolved needs into the final report;
do not spin on identical failures. Distinguish implementation from validated acceptance:
blocked human/manual gates remain blocked, even after an otherwise successful night.

## Review status

On 2026-10-08, three independent subagent reviews covered event/state semantics,
storage/resources/recovery, and current entrypoints/integration. All three accepted
the revised design after resolving their findings, including per-output dependency
pinning, current-base revision checks, repeated imports, subtree-move limits and
idempotent view recovery. This is design consensus, not runtime certification.
