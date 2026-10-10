# Interactive validation of bookkeeping decoupling

Status: practical acceptance remains incomplete. This document is the test protocol,
not a results report. Run it against the candidate implementation after automated
checks pass, using the current [bookkeeping skill](../.agents/skills/artifact-bookkeeping/SKILL.md)
and [supported routes](artifact-ledger-entrypoints.md). Plan review and unit tests
do not count as fresh-agent production trials.

## Scope and setup

Use a disposable checkout containing the exact candidate code and production
instructions, including relevant uncommitted files. Configure separate temporary
data and resource-cache roots outside the checkout. Keep evaluator evidence and
case answers outside the producer's data root and discovery surface. Record the
snapshot manifest, configuration identity, prerequisites and setup changes; redact
credentials. Do not use accepted production assets for failure experiments.

Exclude this protocol, `docs/archive/` and other evaluator-only case
documents from the producer-visible copy. Record those intentional omissions in
the coordinator's manifest; production code and operational instructions must
remain identical. Check normal discovery links do not expose the excluded oracle.

The coordinator must first verify the effective `AGENTS.md`, skill catalog, script
paths and configuration seen by a fresh worker. A different CWD alone is not
isolation: skill catalog entries may still point to the original checkout. Retain
hash evidence that code and production instructions match the candidate and that
default resolution targets the disposable roots. If the host cannot provide this
binding, stop production tests as BLOCKED rather than injecting special path or
bookkeeping instructions into worker prompts.

Reuse the roles/isolation and evidence rules in sections 2 and 6 of
[the broader validation plan](artifact-ledger-validation-plan.md). This does not
activate its overnight protocol or require a full song-to-video production. The
tests below use local fixtures and actual scripts; live paid services, musical
approval, real Flow generation and native platform qualification are separate.
Existing unavailable routes must remain unavailable.

## Agents and procedure

The coordinator prepares fixtures and case expectations. For each attempt, spawn
a fresh producer with `fork_turns="none"`, an ordinary task, the test repo location,
and only the source identities/preferences a user would normally supply. Do not
give it this protocol, the implementation plan, expected ledger IDs, output paths,
bookkeeping commands or a prior worker's solution. Supplying an ordinary production
skill name is allowed; explicitly coaching it to use bookkeeping is not.

Capture the prompt, agent/tool trace, actual invocations, results and before/after
bytes. Relay legitimate user choices; do not fix organizational mistakes for the
worker. A worker error on an available supported route is FAIL, not BLOCKED. If it
reads evaluator answers or needs procedural coaching, retain that attempt as
contaminated and rerun fresh after fixing the instructions or isolation.

At each checkpoint, freeze the post-state before inspection can change it. A
different fresh verifier receives the case oracle and evidence. It checks actual
files, independently measured hashes, execution paths and public ledger queries;
the producer's success claim alone is insufficient. Let a fresh consumer discover
earlier work using ordinary song/result descriptions rather than handed-over paths
or revision IDs. No worker receives the previous conversation context.

Run producers and verifier checks sequentially where they share case state;
independent cases may run in parallel. Keep failed attempts and their evidence.
Apply any repair to the candidate, rerun affected automated tests, then repeat
affected cases with fresh agents. Acceptance must describe the final code snapshot;
earlier evidence counts only where changed code/instructions cannot affect it.

## Required cases

The following table is evaluator-only. All cases are required for interactive
acceptance; unavailable prerequisites or observation boundaries leave that
acceptance incomplete. Use paths containing spaces and non-ASCII text in fixtures.

| Case | Ordinary producer task and setup | Independent pass evidence |
| --- | --- | --- |
| V1 — New skill, block only | In the test checkout, add a tiny ordinary CLI, such as a text summary writer, with normal domain documentation and a Bookkeeping block. Ask a fresh agent to produce the summary. | No bookkeeping imports, flags, callbacks, per-skill adapters or registration; no central-code changes. The agent discovers bookkeeping and publishes the declared result with exact inputs, code and settings. Skill discovery metadata is allowed; inventory records are audit data, not an execution prerequisite. |
| V2 — Existing workflow and identities | Ask a fresh agent to syllabify a supplied lyric; another to make a second option; another to correct the explicitly chosen first result. | Real syllabification runs through the new boundary. The second option has fresh artifact/run IDs; explicit correction revises only its specified base. Earlier bytes and dependencies survive; output agrees with the standalone domain fixture. |
| V3 — Indirect inputs and multiple outputs | Supply a short synthetic audio track, two distinguishable local clips and the normal assembly settings/clip map. Ask a fresh agent to assemble them through the video skill. | Actual assembly consumes every declared clip and the chosen audio from prepared paths, using qualified FFmpeg resources. Audio, film and timeline have complete contracts and correct distinct dependencies. Original manifests are unchanged; published references resolve. Fake rendering is not a pass; unavailable tools make this case BLOCKED. |
| V4 — Discovery and read-only use | Ask a fresh consumer to find and inspect the explicitly selected earlier V2 or V3 result. | Correct revision/files found without prior agent context or latest-file guessing. Pure inspection creates no ledger write event; ambiguous selection triggers a question rather than a guess. |
| V5 — Agent-written artifact | Ask a fresh agent to write a short storyboard using the selected V3 result and supplied lyrics. | Preparation precedes file creation; the agent writes into allocated outputs, records exact consumed evidence, and publishes a complete artifact. No producer script is needed and no organizational recipe is supplied in the prompt. |
| V6 — Refusal and failed production | In separate disposable cases, provide conflicting input choices; then use the V1 fixture with a documented domain fault mode that exits after a partial output or emits an undeclared extra file. Ask for the normal result. | Ambiguity stops execution pending a choice. Failed/incomplete or extra-output attempts are not published as complete; failure evidence and original bytes survive. The worker reports the actual condition rather than bypassing bookkeeping. |
| V7 — Captured execution | Ask a worker to get an operation ready and wait before launching it. After observing actual persisted preparation, alter the disposable live script/package installation, then give the ordinary go-ahead. | Execution uses the prepared code/resources, not changed live versions; recorded settings and actual output/trace establish this. If the required prepare/execute boundary cannot be observed, report BLOCKED. Never alter prepared snapshots to simulate this case. |
| V8 — Fresh-agent publication recovery | Interrupt only a test worker after complete outputs exist but before completion, and separately after completion while the browsing view is unfinished. Ask a fresh agent to finish the interrupted task. | Persisted state identifies each witnessed boundary. Recovery reuses saved IDs/bytes, creates no second production attempt, and repairs only publication/view state. Unexpected user edits survive. Count actual executions independently; merely stopping before outputs exist does not cover this case. |
| V9 — External handoff uncertainty | Use a local external-tool stand-in with observable invocation count and a recorded result receipt. Withhold the return notification after its side effect, then ask a fresh agent to continue the handoff. | The worker reconciles the observed outcome or stops with uncertainty; it does not repeat the action blindly. Retain actual invocation/result evidence. This tests handoff handling, not a real provider's behavior or retry guarantees. |

For V7–V9, use documented public operations and control of the test's own workers
to witness the required states. Do not add secret hooks, hand-edit events, call
private repair helpers, or tell producers the expected bookkeeping solution. Use
ordinary pause/continue requests where appropriate. If the boundary cannot be
reached or observed, record BLOCKED rather than replacing the case with a unit
test. Additional actual host-compaction testing is separate: a fresh agent and
persisted state establish resumption behavior, not host lifecycle behavior.

These cases sample the main interaction patterns. Automated route-level tests
must still cover every claimed-enabled operation; success here does not certify
every native backend, optional model or the full creative workflow.

## Evidence and acceptance report

Retain reports and traces under the configured evaluator data root, not beside
repository code or in the producer's discoverable artifact collection. Use the
normal bookkeeping workflow for finalized evaluator reports where available;
preserve raw evidence if the workflow itself fails, identifying it as unregistered.

For each case record: tested snapshot and fixture identities; exact task prompt;
producer/consumer/verifier IDs; trace locations; before/after bytes and hashes;
actual commands/resources and outputs; independently discovered artifact/run IDs;
expected versus observed behavior; intervention/contamination; verdict and reason.
For failures, include the earliest observed divergence, reproduction evidence and
the repair/retest scope. Keep secrets out of reports.

Use PASS, FAIL, BLOCKED or NOT RUN per case. A correct refusal can pass its negative
case while the requested production remains blocked. Contaminated or insufficiently
observed attempts cannot pass. Missing subagent or fresh-host capability is a
blocker, not permission to substitute the implementer's own successful run.

Report automated implementation checks and interactive acceptance separately.
Interactive acceptance requires V1–V9 to pass on the final qualified snapshot;
otherwise list the unresolved cases explicitly. State additional platform,
live-provider, actual-compaction and human-review coverage without promoting
untested capabilities to PASS.
