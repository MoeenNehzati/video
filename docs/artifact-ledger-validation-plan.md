# Interactive artifact-workflow validation

Protocol for full source-to-film acceptance after automated implementation checks
pass. Practical acceptance remains incomplete; this file is not a result report.
Use the current [bookkeeping skill](../.agents/skills/artifact-bookkeeping/SKILL.md)
and [supported routes](artifact-ledger-entrypoints.md). The narrower
[decoupling protocol](artifact-bookkeeping-decoupling-validation.md) tests agent
integration without requiring a complete creative production.

## Unattended execution mode

When unattended validation is requested, retain checkpoints and actual evidence,
keep producers uncoached, and continue independent authorized cases when another
case lacks resources, manual actions, spending authorization or human review.
Those cases remain BLOCKED; adviser opinions and test-only assumptions are not
human approval. Do not invent creative choices or weaken acceptance gates. Report
unresolved needs and preserve interrupted work for resumption.

## 1. What is being tested

Use black-box end-to-end tasks: source sheet → reviewed XML → arrangements → audio
renders → storyboard/images → clip takes → assembled film. Make alternatives and
handoff between fresh agents throughout. Check both the production result and its
file placement, preserved history, exact dependencies and later discoverability.

The hypothesis is that **AGENTS.md and the skills alone provide enough procedural
information**. Producers receive no artifact-contract explanation, expected layout,
ledger terminology, command recipe, implementation-plan link or acceptance checklist.
Do not explicitly name the bookkeeping skill or tell them to run the configuration
reader. They must discover those requirements through normal project instructions.

Separate worker tasks from the evaluator's oracle. The evaluator may use the
[event contract](../.agents/skills/artifact-bookkeeping/references/event-contract.md), [worked examples](../.agents/skills/artifact-bookkeeping/references/examples.md)
and [entrypoint inventory](artifact-ledger-entrypoints.md); never pass those as test
instructions to producers. Ordinary production documentation reached through the
repository's own instructions remains available. If a producer reads evaluator-only
case answers or receives procedural help, mark the attempt contaminated and rerun
fresh after correcting the test isolation; do not credit it as independent success.

## 2. Roles and isolation

| Role | Context and responsibility |
| --- | --- |
| Coordinator | Owns cases, resource readiness, initial snapshots, human checkpoints and verdicts. Does not perform the worker's missing bookkeeping. |
| Producer | New subagent for each stage/attempt, `fork_turns="none"`, ordinary task only. Works from the tested repo and reads its actual AGENTS.md; uses its skills through normal discovery. |
| Fresh consumer | Another context-free subagent asked to find/use a prior result by song and normal creative description, with no transcript, file map or artifact IDs handed over. |
| Independent verifier | Separate fresh agent given the case expectations and baseline evidence. Checks public interfaces and actual bytes; never coaches the producer. |
| Human collaborator | Answers musical/source choices, provides required external/manual actions and listens/views at checkpoints. The coordinator relays ordinary user decisions unchanged. |

Use a disposable test checkout of the exact implementation snapshot, with the
same AGENTS.md/skills/code, normal repo Python setup and its own local TOML.
Configure a confirmed isolated data root outside the checkout and a separate local
resource cache. Shared production inputs are copied/imported explicitly; do not
conduct failure experiments in accepted production directories. No hidden shell
wrapper or injected environment may bypass the normal initialization workflow.
Before any production, the coordinator must qualify the fresh host's **effective**
instruction files, skill catalog, executable paths and default config resolution.
A different CWD alone is insufficient: a catalog entry may point to the original
checkout, and scripts resolve config from their own source location. Inspect host
metadata and a separate qualification trace; prove code/instruction hashes match
the tested checkout and default paths resolve to its isolated data root. Do not
compensate with extra path/config recipes in producer prompts. If the host cannot
bind normal discovery to the test checkout, validation is BLOCKED before generation.

Also prove tool availability and permissions for the chosen data/cache roots,
recording traces, and controlling only the test's own workers. Record observed
agent model/version and runtime/tool versions where exposed; mark unknown fields.
Retain the source snapshot (including dirty/untracked files used), configuration
restoration reference, resource identities, and relevant pre-case bytes, not just
hashes. Keep credential-bearing config backup private; evidence uses redacted values.
Verify that another evaluator can retrieve the saved snapshots/transcripts. Preserve
unrelated work and state any external resource/provider state that cannot be replayed.

Evaluator case answers and reports must not become artifacts that a fresh consumer
can discover as production guidance. Keep them in a separate configured evaluator
data root, outside the producer root and checkout, with no links in producer-visible
catalogues or handoffs. Prefer access controls; if unavailable, complete read/tool
traces must establish no evaluator access. Incomplete traces or detected access make
the attempt contaminated/unevaluable, not PASS. Ordinary production specifications
reached through AGENTS.md/skills are allowed; live test-case answers are not.

Freeze a raw before/after capture **before** verifier queries, cache refreshes or
report registration. Verify against read-only copies where possible and record any
observer-caused writes separately. Store captures in a preallocated observer
workspace under the evaluator data root; keep host session evidence as an independent
source. Normally register finalized reports through the managed workflow. If that
workflow fails, retain the raw, hashed capture and writer error as explicitly
unregistered forensic evidence, then import it unchanged after repair. Never backfill
producer records to turn a failed case into a pass. A collection failure is a
harness/observability fault, distinct from the product failure it may obscure.

## 3. Preconditions and scope

Before spawning producers, confirm:

- Ledger, schemas, public operations and all claimed-enabled skill boundaries are
  implemented; implementation fixtures pass. This plan does not run against a
  documentation-only ledger and call existing path validation a success.
- A real, manageable source song and required source pages are available, with
  existing reviewed inputs and creative choices clearly identified. No empty-root
  test or arbitrary synthetic melody stands in for real source-to-film validation.
- Required commands, libraries, models, account access and missing prerequisites
  have been checked live. Reuse configured compatible resources; do not silently
  replace the selected tools, musical methods or samples to make a test pass.
- Required human creative/model decisions and paid-generation authorization are
  recorded. Carry existing authorization forward. In unattended mode, advisers may
  supply labelled, reversible test-only creative assumptions within existing
  capabilities and authorization; decisions reserved for the human block dependent
  cases. In attended mode ask only for genuinely missing choices, access or spending
  limits; unattended work continues with other eligible tasks.
- The report names the exact scope: main route, additional skills, recovery cases,
  and what is deliberately not being exercised. All nine production skills plus
  bookkeeping get an explicit coverage entry, including untested modes. Freeze the
  required case/mode list and exclusions before running: map each to its invariant,
  setup, evidence and pass predicate. Do not downgrade failed cases to optional.
- Qualify the verifier on a known-good capture and separate copies with a removed
  event, corrupted historical file and an unregistered output. It must detect and
  locate each seeded defect. These evaluator-only controls are not producer tasks;
  a failing control blocks reliance on that verifier's PASS verdicts.

The current arrangement skill varies an approved baseline; it does not create an
initial pitched arrangement. Recheck this boundary at validation time. Either observe
a real managed manual/external baseline-creation stage consuming the new reviewed
score, or explicitly label the route **baseline-assisted** using a verified compatible
baseline. Never count a seeded baseline as successful initial-arrangement generation.
An arrangement test must actually consume the newly selected XML and its required
musical inputs, not merely reuse an unrelated earlier MIDI.

Flow remains a real manual generation/import handoff unless the production skill
has acquired a verified replacement. Preexisting clips can test import/assembly but
cannot establish live image-to-video generation. An instrumental/demo film does not
prove final recorded-vocal alignment or mixing. Record those limits in the verdict.

## 4. Stage-by-stage interactive protocol

For every case:

1. Freeze the case's code/config snapshot and take an independent before-inventory,
   including relevant file hashes and public history/selection query results.
   Retain retrievable relevant input/history/event/workspace bytes and a restoration
   recipe. Changes made to set up a negative case have their own before/after record.
2. Spawn a new producer with no inherited conversation. Its prompt contains only
   repo location when needed, the ordinary task, source/song identity or a normal
   initial source attachment/location, and user preferences/authorization. Never
   append contract hints, output paths chosen by the evaluator or expected IDs.
3. Let it operate using repository guidance. Record prompt, messages, tool calls,
   questions, exit results and resulting files without steering its implementation.
   Relay legitimate artistic/source choices. If it asks for organizational mechanics
   that the instructions should supply, record the failure instead of giving the
   answer and treating the assisted attempt as passed.
4. At completion or blockage, a fresh verifier collects evidence independently.
   First freeze the producer's post-state before any recovery or report writes.
   Compare actual files/hashes, public queries and declared manifests against the
   pre-state and expected outcome. A producer saying "registered" is not evidence
   of registration; matching hashes copied from that same ledger are insufficient.
   Recorded dependencies alone also do not prove consumption: correlate the actual
   invocation/input-slot mapping with independently hashed bytes and the output.
   Use distinguishable source/arrangement/render alternatives for wrong-version
   cases; identical-byte acquisition is a separate identity test. If command/tool
   traces cannot establish which inputs were used, report that observation gap.
5. Present a short stage checkpoint to the human: outputs to inspect/listen to,
   bookkeeping verdict, quality verdict and any material question or blocker.
   Obtain actual required source/listening/visual review before passing that gate;
   never infer approval from silence or successful encoding. Existing recorded
   decisions need not be asked again. In unattended mode, record the checkpoint
   and continue independent tasks; missing required human review remains BLOCKED.
6. Proceed with a fresh consumer/producer using only ordinary task context and the
   accepted creative choices. It must discover earlier work through normal repo
   guidance. Do not pass the prior agent's solution, path map or hidden IDs.

Example producer prompts (replace placeholders with ordinary song descriptions):

> Transcribe the supplied sheet for SONG into MusicXML.

> Make another transcription option for SONG using its second source sheet.

> Make two arrangement options for SONG with different percussion feels.

> Render the gentler arrangement in two sound palettes.

> Use the first piano render for a storyboard and character images for SONG.

> Make another image option for the opening shot.

> Assemble a video using the selected pictures, returned Flow clips and chosen audio.

> Find the earlier piano version of SONG and make another video cut with it.

These are templates, not a mandatory word-for-word script. Choose creative variations
within the actual supported capability and available resources; an unsupported
variation is a capability blocker, not permission to replace the workflow. Ambiguous artistic
references may prompt a normal clarifying question. Explicit revision tests use a
normal user request to correct an existing result; do not explain how to preserve
its history. Output-path and contract discovery remain the agent's responsibility.

## 5. Scenario matrix (evaluator only)

| Case | Ordinary task variation | Independent expected check |
| --- | --- | --- |
| First route | Produce one song through all selected stages, with required human/manual handoffs. | Correct outputs, stage reviews, complete owned file sets and exact cross-stage provenance; no unexplained artifacts beside code or outside the resolved root. |
| Repeated experiments | Ask for another option at transcription, arrangement, render, storyboard, image, clip take and assembly stages. | Fresh run/artifact identities and browsable siblings at every stage; older attempts retained. Same bytes do not collapse distinct attempts. |
| Explicit correction | Correct an existing XML after arrangements/renders already exist. | New revision of that artifact, preserved old bytes; descendants and their old input references unchanged. |
| Earlier choice | Choose an older render/take, then ask a fresh agent to use it. | Exact selected revision and file role consumed; no latest-file guessing or silent downstream rewriting. |
| Fresh-session lookup | Find earlier options/history and continue work without prior chat. | Correct retrieval from persistent project records; ambiguous choices surfaced, not invented. |
| Manual import | Receive two Flow takes or two acquisitions with identical bytes but distinct attempts. | Origin evidence and separate attempt identities; idempotent recovery only for the same recorded import. |
| Interruption/recovery | Exercise both required publication interruption states below, then ask a fresh worker to continue. | Same-intent recovery preserves IDs; incomplete bundles never pass, view repair creates no new revision, and a deliberate rerun is separate. |
| Altered/missing input | Alter a disposable browsing copy or withhold a required file/resource between cases. | Historical exact inputs resolve safely, or the worker reports the real blocker; no unrecorded substitute or overwrite of unexpected edits. |
| Concurrent edit/selection | Exercise competing revision heads and competing selection heads, separately, from the same recorded base. | Both contenders survive; conflicts appear and resolve explicitly. Two independent creates or serialized updates do not satisfy these cases. |

Minimum required recovery/conflict observations are:

- **Outputs complete, completion event absent:** witness saved outputs and the
  prepared publication intent, interrupt, then observe publication recovery using
  the same IDs without rerunning production.
- **Completion present, view incomplete:** witness the completion and unfinished
  browsing projection; recovery repairs only the view. Already-matching files are
  accepted without duplication; unexpected user bytes are preserved.
- **Competing revisions:** prove both contenders used the same base and that the
  combined event set contains two heads for the same artifact revision key.
- **Competing selections:** separately prove two heads for the same scope/stage/
  purpose and verify explicit resolution. Independent artifacts do not count.

Capture boundaries before interrupting; stopping before outputs exist does not
exercise publication recovery. For offline conflicts, use two isolated replicas of
the same pre-state, each through normal public workflows, then synchronize copies
of their unchanged event/history files. Keep host identities distinct and record
the exchange; this tests merge behavior, not live Dropbox-service reliability.
If actual service synchronization is claimed, test that separately. Never hand-edit
ledger events or coach workers about heads. If public observability cannot witness
the required states, mark these cases BLOCKED and improve the public surface.

For interruption and concurrency, coordinate through observable public operations
or process control of the test's own workers; do not call private publisher helpers
or insert hidden runtime switches. Preserve evidence of which boundary/base was
actually reached. If it cannot be observed or exercised, mark the case blocked,
not passed. Exhaustive crash-point and sync-order injection remains the fixture
suite; a live spot check does not replace it. Perform disruptive cases only on
isolated branches/copies, never on the only successful demonstration chain.

Additional skill coverage: exercise acquisition, analysis, syllabification, vocal
planning, Nishiren synthesis and external RVC separately when applicable. Preserve
the actual source: do not remove rests/slurs or alter approved music to fit a backend.
Use a separately identified suitable test song where required. Missing resources or
unsupported inputs yield BLOCKED/NOT RUN entries, not a passed all-skills claim.
Source review and file-only score audit, generation and import, and each producer's
read-only versus write modes remain distinct coverage items.

## 6. Evidence and acceptance

The verifier uses public documented commands/APIs and artifact formats plus read-only
filesystem checks. It may inspect recorded events and history but cannot import
private ledger functions, repair records or rewrite outputs. Root containment alone
is insufficient: verify nested placement, IDs, event completeness, preserved bytes,
actual dependency file selection, resources, reviews and selections. Compare the
before/after repository inventory and available tool traces for misplaced artifacts;
state observation limits rather than claiming to have monitored the whole machine.

For each attempt, retain one result record with:

- Case/stage, exact ordinary prompt, agent/session IDs, implementation/config identity,
  initial inputs and independently measured hashes, plus retrievable restoration
  references for the before-state and frozen post-failure state.
- Tool/transcript references, questions and human answers, any intervention or
  contamination, invocation argv/API request identity, cwd, relevant redacted
  environment/config, timestamps, stdout/stderr, exit code or signal and observable
  child-process boundaries. Retain raw outputs and mark truncated/missing traces.
  Link every agent/tool/provider retry, including automatic retries where observable;
  absence of retry telemetry cannot prove that only one remote request occurred.
- Output artifact/run/revision IDs discovered by the verifier, actual files/hashes,
  relevant public query results, before/after differences and review evidence.
- Separate instruction-following, artifact-contract and musical/visual outcomes,
  verdict/reason and links to blockers. Redact secrets from all persisted evidence.

For each FAIL/BLOCKED result add a compact **failure packet**: violated invariant;
expected versus observed values; earliest observed divergence and its command or
boundary; relevant input/output IDs, paths and independent hashes; raw evidence
locations; reproduction steps using public interfaces (or why not reproducible);
suspected cause and supporting evidence; alternative explanations and uncertainty;
proposed repair location and the cases needed to verify it. Separate symptoms from
confirmed root cause. Preserve failed workspaces, journals and event bytes before
recovery; a hash without recoverable bytes is not a reproduction package.

Use PASS, FAIL, BLOCKED and NOT RUN. Missing observational evidence is not PASS.
A correct refusal can pass its specific negative case while production remains
blocked. A technically correct ledger does not establish musical/visual approval;
a pleasing film does not excuse missing history. Optional tracks not run cannot
support an all-skills acceptance claim.

Main-route acceptance requires all its required stages, fresh-context handoffs,
repeated attempts, explicit correction/selection cases and actual human reviews to
pass on the final snapshot. Required recovery/conflict cases must also pass for
full artifact-workflow acceptance. Report baseline assistance, manual steps and
unvalidated capabilities explicitly; do not give an unqualified end-to-end PASS
when a required stage was replaced, coached, skipped or blocked.

## 7. Fail, fix, rerun, close

Stop advancing a failed branch; preserve its artifacts, transcript and failure
record. Diagnose whether the cause is instructions/discovery, implementation,
configuration, missing external capability, musical quality or the test harness.
Do not call a ready supported route BLOCKED merely because the agent misused it:
that is FAIL. A missing prerequisite or observation capability is BLOCKED with its
exact missing evidence/resource. Contaminated attempts remain unqualified and require
fresh execution. Fix the repository instruction or implementation at the source; do not compensate with a richer worker
prompt. Source/config changes happen between attempts and create a new recorded
implementation identity, never during a supposedly frozen passing run. First derive
an evaluator-only minimal reproduction from the captured state when feasible; do
not feed that recipe to later producers. Reproduce local bookkeeping faults without
repeating paid generation. Record a causal explanation of the fix and verify the
failed invariant again. If a fresh run passes but the failure cannot be reproduced
or explained, retain it as intermittent/unresolved rather than declaring it fixed.

After a fix, use new producer and verifier contexts. Rerun the failed case and its
affected downstream/boundary cases, then run one complete final demonstration with
fresh handoffs on the final snapshot, including the required branching, correction
and selection cases. Required recovery/conflict cases must also have passing
evidence on that snapshot; a linear happy-path run alone is insufficient.
Retain prior results under their original snapshot; do not carry earlier passes forward silently. End with the case/mode
coverage matrix, independently supported verdicts, human decisions and remaining
blockers. No automatic deletion of validation history or commit/push is implied.

Initial design reviewed on 2026-10-08. A further independent audit of false-pass
risks, diagnostic sufficiency and host execution found gaps in discovery isolation,
evaluator contamination, recovery coverage and failure evidence; the changes above
address those findings. All three reviewers rechecked the revision and passed it
with no remaining design blockers in their assigned scopes. No live validation has
been executed.
