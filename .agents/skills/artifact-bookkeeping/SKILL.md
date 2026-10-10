---
name: artifact-bookkeeping
description: Prepare, publish, import, find and review song artifacts with immutable revisions and exact provenance. Required for every producer, including manual and external operations; read-only inspection needs no write event.
---

# Artifact bookkeeping

Use this skill for all song-artifact access, including reads and implicit I/O by
scripts, subprocesses, GUI actions, downloads and API calls. Preserve the production
skill's musical and visual method; bookkeeping owns artifact resolution, storage,
provenance, revisions, publication and recovery. Local bookkeeping blocks declare
inputs, outputs, resources, settings and domain constraints; they do not override
this lifecycle. Repository source/configuration inspection is outside the song
ledger. Read
[usage and API examples](references/usage.md) and the selected
entrypoint's classification in
[the coverage inventory](../../../docs/artifact-ledger-entrypoints.md).

The implementation lives in this skill's `scripts/`, with its schema in `schema/`
and tests in `tests/`. Other skill instructions name this skill and provide local
configuration; they never call its scripts or specify its API/CLI. This skill owns
those implementation details. The CLI is `scripts/artifact_ledger.py` relative to
this skill.

## Access and execution

For read-only inspection, use ledger discovery/resolution to identify the exact
revision files; no write event is required. Once an inspection informs a produced
artifact or persisted review, include those exact files in that operation's inputs.
Production consumes prepared copies. An undeclared additional input requires a new
prepared attempt; another declared file from the same revision does not cover it.

Production scripts expose ordinary domain arguments and have no bookkeeping
imports, flags or callbacks. Translate the production skill's Bookkeeping block
into the generic command operation in the usage guide. Resolve its exact I/O,
capture its declaration and executed helper tree, bind resources and effective
settings, then use the central prepare/execute/finish operations. The inventory is
an audit record, never a registration requirement for a new skill.
An unavailable route cannot be bypassed with an ordinary command or manual import.
Agent-written files, GUI edits and external actions use a prepared handoff with
actual outcome receipts and the same exact dependency/output contracts.

When resuming after interruption or context compaction, reload this skill and read
the persisted operation intent and ledger status before further artifact access.
Recover exact inputs, allocated slots and execution/publication state from those
records. Do not reconstruct them from a conversation summary or repeat production
merely because the previous tool result is absent. If an external call's outcome
is unknown, reconcile that handoff before deciding on another attempt.

## Before production

1. Run the repository environment's Python with `-m scripts.read_config`. Resolve the
   data root and local `bookkeeping.actor_id`/`bookkeeping.host_id`; see
   [configuration](../../../docs/configuration.md). Resource-consuming operations
   additionally need a private `paths.resource_cache` and matching resource bytes.
   Python operations with third-party imports also need the active
   `resources.python_packages` installation; bookkeeping snapshots the consumed
   distributions before running.
   Runtime platform records and resource manifests are provenance evidence, not
   an operating-system sandbox or automatic proof of dependency closure.
2. Find the song and candidate artifacts through the ledger. Resolve exact
   artifact/revision IDs, selected files and purpose. A selection pins a revision;
   a passing review does not select it. Multiple candidates without a clear user
   choice are ambiguous: never infer newest, preferred or accepted from filenames,
   timestamps or storage ancestry. Explicit historical inputs remain valid.
3. Import required unmanaged files explicitly. Keep originals; record original
   names, known source/retrieval/license evidence and unknowns honestly. Do not
   bulk-migrate existing directories or invent their production history.
4. Declare every consumed input, including briefs, prompts, settings, builders,
   continuity references, audio, library/model files and embedded path targets.
   Capture executed project code including local modifications. Separate artifacts
   whose dependencies differ or whose files will be revised independently.
5. Prepare a bounded operation before any file production, GUI edit or generation
   call. Use the generic command operation, with `command: null` and a concrete
   handoff description for manual/external work. Check the entrypoint inventory: `unavailable/reference-only`
   routes stop before writes or external calls. `scripts.read_config --run` alone
   grants no managed context.

## Produce and publish

Prepare allocates a new run, artifact IDs, revision IDs and
`work/<run_id>/{inputs,outputs,scratch}`. Read only verified prepared input copies;
edit those copies when an editor needs writable inputs. Never pass mutable browsing
paths or installed resource files to a producer. Resource-consuming operations use verified private resource snapshots and
recheck them after production.

Write declared deliverables into their allocated output slots. Use scratch for
disposable intermediates. Declare explicit owned filenames/roles or bounded,
nonoverlapping discovery rules; missing or unexpected files prevent publication.
For an agent-written plan/prompt/builder, prepare and mark the handoff before
writing, record the observed receipt, then finish. External results belong to the prepared operation and must be imported
from that exact generation/handoff, never a guessed latest file.

Finalize verifies consumed bytes, output contracts and expected state; preserves
immutable history; appends one completion for the complete output set; and repairs
the owned browsing view. Only this publisher writes `history/`, `ledger/` and
registered browsing files. Check finalization succeeded before reporting a result
as locally complete. Registered, available, current, reviewed and selected are
different properties.

Another attempt always gets a new run and new artifacts, even for identical bytes.
Record `branched_from` separately from actual dependencies. Only an explicit user
revision request may prepare `action=revise` with an exact current base. That changes
owned files only; descendants, earlier revisions and their pinned inputs survive.

## Interruptions and later decisions

On a production failure, record failure without publishing a partial bundle. A new
production attempt gets new IDs. Resume/recover only the same interrupted
publication, reusing its saved intent and bytes; never repeat a paid generation
call as recovery. After completion, recovery repairs the view without another
revision. Unexpected local edits stop repair; preserve them for explicit import or
revision. Never delete workspaces, history, events or unknown files to force retry.
Inspect the generic operation status and finish known successful results. An
execution marker without a successful receipt is uncertain, not permission to
rerun or finalize. Use only public ledger operations for repair. Never edit projection/publication
journals or call private helpers to bypass a refusal; preserve the failure evidence.

Record reviews against exact revisions, with stage, purpose and evidence. Record
selection changes separately; they leave existing downstream inputs untouched.
Use managed metadata/move/withdrawal operations for later changes. Withdrawal
preserves history. Resolve every named competing head explicitly; timestamp order
is never conflict resolution. Move only a complete subtree within its existing
parent/root; reparenting and permanent history deletion are outside v1.

## Retrieval and reconciliation

Use ledger queries for exact history, producer, direct/transitive inputs and
downstream consumers. Report pending synchronization, missing bytes, corrupt
records, conflicts and unsupported schemas separately. A cached catalogue is
disposable; immutable events and history are authoritative. Historical lookups
must resolve preserved bytes, even when today's browsing file differs.

Reconcile unknown or altered files and show explicit import/revision choices.
Never backfill fictitious provenance, silently choose a conflict winner, overwrite
unrecognized files or claim complete synchronization from a local scan. Human
source/listening/video review remains a human checkpoint; bookkeeping or synthetic
fixtures cannot grant it.
