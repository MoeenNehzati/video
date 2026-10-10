# Artifact ledger v1 contract

The ledger is implemented. This reference describes its event/state invariants;
[event.schema.json](../schema/event.schema.json) defines structural validation and
[ledger_replay.py](../scripts/ledger_replay.py) enforces causal state rules.
Use [the execution guide](usage.md) for current public operations. Events and
published revision bytes are immutable.

## Types and records

IDs are lowercase hyphenated UUIDv4 strings. Times are UTC RFC3339 strings ending
in `Z`; they are display evidence, never ordering. Paths follow the portable
relative-path rules in [the execution guide](usage.md#failure-recovery-and-queries). SHA-256 values are 64 lowercase hex characters. Arrays of IDs
and heads are sorted and unique. Reject duplicate JSON keys, non-finite numbers,
unknown schema versions and unknown structural fields. Free-form producer settings
and error details are JSON objects; never store credentials.

| Record | Required fields and constraints |
| --- | --- |
| Event | `schema_version: 1`, `event_id`, `event_type`, `recorded_at`, `actor: {id, host_id}`, `previous_events: [event_id]`, `expected_heads: {state_key: [event_id]}`, `data`. actor.id is a configured label; host_id is a machine-stable UUIDv4, never a label or unchecked path. These identify attribution, not authentication. |
| Exact reference | `{artifact_id, revision_id}`. The revision must belong to that artifact. |
| Dependency | Exact reference plus `files: [relative_file_path]` and nonempty `purpose`. Resolve role selectors to explicit files before recording. Every listed file must exist in the referenced manifest. |
| File | `path`, `role`, `sha256`, `size_bytes` (nonnegative integer); optional `original_name`. No child-artifact files or unlisted directory contents. |
| Artifact identity | `artifact_id`, `kind`, `label`, `song_ids`, `path`, `storage_parent` (artifact ID or null). Kind is a stable lowercase slug; labels are human text. `song_ids` must resolve. |
| Revision | `revision_id`, `history_path`, `files`, `dependencies`, `producer`, `previous_revision_id` (UUID or null), `branched_from` (exact reference or null). History path is exactly `history/<artifact_id>/<revision_id>`. |
| Producer | `run_id`, `operation`, `skill`, `entrypoint`, `command` (argv array), `settings`, `code` (captured file hashes plus snapshot reference), `resources` (descriptor revision references), `origin` (source URLs/pages/retrieval/license evidence or explicit unknowns), `unknowns` (field-to-reason object, empty when complete). Nonapplicable/unknown fields are null with reasons in `unknowns`; never invent a command or version. |
| Output intent | `action: create|revise`, `artifact_id`, `revision_id`, `identity` (create only), `base` (exact reference for revise, otherwise null), `branched_from` (create only, nullable), `output_slot`, `dependencies` (exact declared edges, including allocated same-completion outputs), `contract`. |
| Output contract | Either explicit `files: [{path, role}]`, or bounded `discovery: [{glob, role, min_count, max_count}]` within that output slot. Patterns cannot overlap or escape. Finalize enumerates all publishable files and rejects unexpected/missing files. Scratch is separate. |

The start's inputs are the union of the outputs' external dependencies. Each output
pins its own dependency edges before execution; completion must match them exactly.
For same-completion outputs with discovery contracts, intent declares role selectors;
finalize expands them to explicit files in the captured manifest. Finalization rejects changes to declared inputs. It cannot detect every
undeclared read by arbitrary software; the agent must declare all consumed inputs
before preparation rather than invent provenance afterward.

A create has a new artifact/revision ID and null `previous_revision_id`. A variant
may set `branched_from`; it still records actual consumed inputs as dependencies.
A revise keeps identity/kind/storage location, sets `previous_revision_id` to the
explicit base and has null `branched_from`. At prepare, that base must equal the
revision value of the single current `/revision` head. Freeze that output head set
in `publication_heads`; completion must reuse it, plus its run-start head. A known
new head blocks finalization rather than silently rebasing. To start from an older
revision, create a branch; an explicit merge revises the resolved current base. Labels/song associations and location
change only through their own events. New revisions are never inferred from names.

One bounded operation may create several artifacts. Its revision dependency graph
may include other outputs of that same completion, with no cycles. If a tool uses
an intermediate whose exact revision cannot be identified in the declared output
set, split the operation into stages. Reports pin the exact outputs they check.

Capture executed project code, including dirty files, as a separate managed code
snapshot before starting the production run; record the bootstrap bookkeeping
code hash for that capture. This bootstrap operation alone permits hash-only code
provenance with a null snapshot reference and an explicit bootstrap reason; ordinary
production requires the captured snapshot reference. Record effective settings with secrets redacted. A
portable command substitutes exact revision/resource/workspace tokens for absolute
machine paths; its token-to-input mapping is part of intent. Tool identity comes
from a resource descriptor, not an executable basename alone.

## Event payloads and state transitions

The common envelope is omitted below. All fields shown are required unless marked
optional; references must resolve in causal history or in the same completion.

| `event_type` | `data` and effect |
| --- | --- |
| `song.created` | `{song_id, label, path}`; create song under `songs/`, unique ID and location. |
| `operation.started` | `{run_id, operation, inputs, outputs, publication_heads, producer, workspace, input_slots, resource_slots}`; pin intent and allocated IDs. Workspace is `work/<run_id>`. Slot maps identify exact inputs/resources; no live browsing inputs. publication_heads pins the expected output-state heads for completion. |
| `operation.completed` | `{run_id, updates}`; each update has `{action, artifact_id, identity, revision}`, with identity null for revise. Updates must match the start's complete output set, dependency edges and contract. Register the whole set together. |
| `operation.failed` | `{run_id, error: {code, message, details}}`; terminal failure, no published artifact revisions. |
| `operation.abandoned` | `{run_id, reason}`; terminal cancellation, retain evidence. |
| `metadata.corrected` | `{target, changes, reason}`; target is song/artifact/revision identity. Allowed song field: label; artifact fields: label, song_ids; revision field: provenance_notes. Notes annotate the old claim; cannot replace manifests, dependencies, hashes or original producer data. |
| `artifacts.moved` | `{mapping: [{artifact_id, from, to}], reason}`; complete artifact subtree, preserving IDs/history. Validate old locations, descendants, destinations and path limits as a group. V1 renames a subtree within the same song/shared root and preserves storage-parent relations; reparenting is unsupported. |
| `review.recorded` | `{review_id, target, stage, purpose, verdict, notes, evidence, supersedes}`; exact revision target, evidence revision references, verdict `pass|fail|needs-review`, supersedes another review ID or null. Supersedes requires the same actor, target, stage and purpose. Immutable review, not approval by publication. |
| `selection.set` | `{scope, stage, purpose, target}`; scope `song:<id>`, `artifact:<id>` or `shared`; target exact revision or null to clear. Stage/purpose are lowercase slugs. Scope must match the target's song association or ancestry (shared targets have shared scope). |
| `artifact.withdrawal_set` | `{artifact_id, withdrawn, reason}`; Boolean visibility state, reversible, never deletes history or selections. |
| `conflict.resolved` | `{resolutions: [{key, heads, chosen_head}], reason}`; name all observed heads and select an existing value for each conflicted key. No synthesized bytes or timestamp winner. |

A run moves from absent → started → one of completed/failed/abandoned. A terminal
run cannot restart. A new tool attempt, changed settings or rerun after failure
always gets a new run and, by default, new artifacts. Resume only an interrupted
publication of the same prepared bytes/intent; never repeat a paid generation call
as publication recovery. Competing terminal events are a conflict, not last-write-wins.
All completed output bytes remain registered even when a run-state conflict blocks
claiming one terminal outcome; resolving it never deletes those records.

Selection does not withdraw other attempts or imply review. Selecting an older
revision is valid. A selected withdrawn/missing/conflicted result is reported as
such; do not silently choose a replacement. Explicit revision lookups can retrieve
verified historical bytes even when the artifact's current view is conflicted.

## Causality and conflicts

Use these state keys (angle brackets mean an ID or constrained slug):

- `song/<id>` for existence/location; `song/<id>/label` for label.
- `artifact/<id>/identity` for immutable existence/kind/storage parent;
  `/revision`, `/location`, `/label`, `/song_ids`, `/withdrawn` for mutable fields.
- `revision/<id>/provenance_notes` for additive correction history.
- `run/<id>/state`, `review/<id>` and `selection/<scope>/<stage>/<purpose>`.

Creation writes all its initial keys, including label/song_ids/withdrawn=false;
revision publication writes `/revision` and initializes provenance_notes to null.
Start and every terminal event write run state. Each other event writes exactly
the keys its payload changes. A completion creating a revision initializes its
revision-specific key; a correction updates that key without mutating the manifest.
Review creation uses an empty expected head set. Identity writes are create-only.

`expected_heads` covers exactly those mutated keys. An empty list means the key
must be absent. `previous_events` includes the terminal event's start, the heads
being changed, all referenced creation/revision/review events, and required input
provenance. Same-completion revision references resolve within `updates` and do not
create a predecessor edge to the completion itself. The start causally includes the
heads recorded in `publication_heads`; new output/revision keys have empty heads. IDs in expected heads must occur in that causal ancestor closure.

1. Missing predecessors make an event pending; reject causal cycles.
2. Validate the event against **heads within its own ancestor closure**. Never
   compare to whatever happened to be replayed first. Its expected heads must equal
   that closure's heads for every mutated key.
3. Ordinary changes require one head, or no head for creation. Resolution requires
   at least two heads and includes every head observed for the key. Locally reject
   stale-base mutation before appending when additional heads are already known.
4. Current heads are causally maximal valid writes per key. Concurrent sibling
   writes remain valid but conflicted. Their immutable revisions remain accessible.
5. A resolution writes a new head with the chosen existing value. A later-arriving
   competing head reopens the conflict. To merge content, resolve explicitly and
   run an explicit revision whose dependencies include every merged input.

Independent field changes can coexist; location/revision changes may commute
because historical inputs use IDs, not browsing paths. Validate the combined view:
casefold path collisions, overlapping ownership or inconsistent subtree mappings
block materialization. Resolve locations with explicit collision-free move events;
do not drop an unrelated artifact to pick a winner. A conflicted structural move
blocks its complete subtree projection, preventing half-applied moves. Conflict
resolution must preserve grouped move invariants and never resolve only a subset
that produces an inconsistent tree.

Malformed records are invalid; missing referenced records/bytes are pending;
unsupported schema is unsupported; hash mismatch or differing content under one
ID is integrity failure. Preserve all evidence and show incomplete query status.
No local scan can certify that every collaborator's offline event has synchronized.

## Publication and recovery

Prepare persists intent and starts the run before production or external calls.
Private run inputs are copies/reflinks, never writable aliases to history; recheck
consumed bytes and resource snapshots before completion. Only publishers write
history, events and managed views. Serialize local publication/view repair with a
per-data-root local OS lock; Dropbox synchronization is not a distributed lock.
Do not use a shared lockfile's presence as authority over another machine.

Finalization order is: validate complete outputs → save the intended completion
record and manifests in the run journal → preserve and verify immutable history →
atomically publish the completion JSON locally → materialize owned browsing files.
The journal retains allocated event/revision IDs and exact intended event bytes.
Publish no-clobber; existing identical content is success, different content is an
integrity error. Atomic local publication must never expose partially written JSON.
Store UTF-8 JSON with sorted keys and finite values; the saved serialization is
reused verbatim on retries. JSON whitespace alone is not a different logical event.

Replay registers a complete operation's manifest set together once references
validate; missing synchronized history makes those outputs unavailable, not absent
from history. Materialization waits for verified bytes and unambiguous relevant
state. It is a recoverable projection, not a filesystem-wide atomic transaction.
After completion, recovery only repairs that projection; no second completion or
revision. Before completion, incomplete output sets remain pending or fail; never
pretend that existing partial files satisfy the contract.

For each owned-file replacement, compare against the last materialized hash or
recorded absence, persisted in a host-specific recoverable projection journal.
An existing destination already equal to the intended target hash is an idempotent
success, including on a fresh host or after a crash before journal update. An absent
journal grants no authority to replace different existing bytes. Stop on unexpected
local edits or any other unknown destination files. Remove a retired owned
file only after its bytes were preserved and its expected hash matches. Never
recursively delete an artifact directory. A move journal records the whole mapping;
unknown descendant files block the move until explicitly handled. No initial
history garbage collector or automatic abandoned-work cleanup is included.

## Required fixtures

Use the [worked examples](examples.md) as readable acceptance cases.

Encode small synthetic files, not real song artifacts: two sources feeding an XML;
two XML alternatives; explicit revision of one; two arrangements per alternative;
two renders per arrangement; alternative storyboards/images/clip takes and video
assemblies sharing resources. Add a report pinned to an old revision, a full/backing
bundle, a Flow-kit replacement preserving old images, failed attempts and manual
imports. Test every stage's independent selection and downstream pinned inputs.

Replay every valid fixture under shuffled event/file arrival; test missing ancestors,
duplicate/corrupt IDs, concurrent revisions/selections/terminal outcomes, grouped
moves, unexpected edits and crash points before/after every publication boundary.
Verify retry idempotence versus distinct new attempts, exact consumed resource
snapshots, multi-output registration, and unavailable historical external bytes.
