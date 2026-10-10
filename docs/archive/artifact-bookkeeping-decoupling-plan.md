# Decouple production scripts from artifact bookkeeping

> Archived design/implementation plan. The text below describes its historical
> baseline; obsolete paths, status claims and implementation steps are not current
> instructions. Runtime implementation exists; practical acceptance remains separate.
> Current instructions: [artifact-bookkeeping](../../.agents/skills/artifact-bookkeeping/SKILL.md), [execution coverage](../artifact-ledger-entrypoints.md), and [practical validation](../artifact-bookkeeping-decoupling-validation.md).

Status: implementation plan; no runtime changes made by this document.

## Fresh-agent handoff

Start in the live checkout at `/home/moeen/Documents/video`. Read its `AGENTS.md`,
the bookkeeping `SKILL.md`, this plan and
[the separate interactive validation protocol](../artifact-bookkeeping-decoupling-validation.md).
Inspect Git state before editing: the working tree contains uncommitted work, so
the tested baseline must include relevant dirty and untracked files, not just HEAD.
Preserve unrelated changes; do not commit, push or touch production song data
without separate authorization.

Use `docs/artifact-ledger-entrypoints.md` to locate routes and `docs/skill-imports.json`
for ownership. Start with `artifact-bookkeeping/scripts/ledger_producer.py` and
`ledger_python.py` beneath `.agents/skills/`, then the syllabification and Flow
assembly callers. Recheck current files rather than assuming this plan's baseline
still matches. This plan replaces producer-to-ledger coupling; the existing ledger
event contract and musical/visual requirements remain in force.

When implementation is explicitly assigned, complete the sequence below, run
`env/bin/python scripts/run_tests.py` (Windows:
`env/Scripts/python.exe scripts/run_tests.py`), and then conduct the separate
interactive subagent validation. Return the changes, automated results,
interactive report and remaining blockers. A static plan audit or green unit suite
alone does not establish readiness for ordinary agent use.

## Outcome and scope

A production skill integrates through one Bookkeeping block in `SKILL.md`: it
names `artifact-bookkeeping` and declares explicit I/O, resources, settings and
domain constraints. The agent loads `artifact-bookkeeping` for the procedure.
Production scripts accept ordinary arguments and perform domain work without
bookkeeping dependencies.

This replaces the current integration: eight production skills import bookkeeping
modules, and several contain lifecycle adapters. RVC remains a manual external
workflow. Preserve musical/visual behavior, validation and the existing ledger
format. Do not migrate song data, regenerate accepted artifacts, enable disabled
routes, or broaden native-tool platform support as part of this refactor.

## Responsibility boundary

| Owner | Responsibility |
| --- | --- |
| Production skill | Domain method, normal script interface, and local I/O declarations. |
| Production scripts | Compute from supplied paths/settings; write explicit outputs and scratch; report success or failure. Domain validation stays here. |
| Agent using artifact-bookkeeping | Interpret declarations, resolve choices, construct the operation and invoke the central lifecycle. |
| Artifact-bookkeeping | Resolve revisions; capture code/resources; prepare paths; execute or hand off; verify and publish; record failures and recover publication. |

The direction is **bookkeeping invokes production**, with no reverse dependency.
Use existing ledger operations and snapshot machinery. Add only the minimal
central command execution support needed to run ordinary scripts. Do not introduce
a Markdown parser, plugin registration, per-skill bookkeeping adapter requirement,
or second configuration file that every new skill must maintain.

## What the Bookkeeping block declares

Use short prose or a table, with one entry per materially different operation.
Reference the skill's normal CLI documentation rather than copying its arguments.
Declare only applicable information:

- **Inputs:** consumed files and their purpose, including indirect files named in
  manifests, inspected references, prompts and continuity inputs.
- **Outputs:** files or bounded bundles, logs/reports to retain, and which outputs
  have different dependencies or need independent revision. Distinguish scratch
  from deliverables and stdout-only inspection from a persisted report.
- **Resources and settings:** tools, packages, models, libraries, relevant options
  and environment/configuration dependencies. Credentials remain private.
- **Domain constraints:** required relationships between inputs, path resolution
  inside manifests, output dependency/order requirements, and manual or external
  effects that need a handoff rather than a local command.

For example:

```markdown
## Bookkeeping

Use artifact-bookkeeping with these declarations:
- Syllabification: input lyrics text; output lyrics JSON; setting language.
- Use the script interface documented below. No score input is consumed.
```

Video assembly additionally declares every clip referenced by its clip map, the
map's path-resolution rule, audio, timing settings, FFmpeg resources, and separate
audio/film/timeline dependencies. The central procedure resolves embedded paths.
Blocks contain no ledger identifiers, request schemas or lifecycle calls; labels,
selections and revision intent belong to each invocation.

## Central execution procedure

1. Load the production skill and artifact-bookkeeping. On resumption, reload the
   central instructions and persisted operation state before acting.
2. Resolve exact input revisions and applicable declarations. Expand indirect
   inputs according to the documented domain format; unresolved or ambiguous
   dependencies stop preparation. Read-only inspection uses resolved files and
   needs no write event; evidence used in a later artifact becomes its input.
3. Construct and validate the operation using the central interface: input and
   resource bindings, captured executable code, effective settings, output
   contracts and actual argument vector. Record the declaration source used.
   Keep bookkeeping interface/lifecycle instructions central; ordinary script
   interfaces remain documented in their production skills. Persist the effective
   operation so resumption does not reinterpret a changed block.
4. Prepare immutable inputs, resources, allocated outputs and scratch. Rewrite
   embedded paths only in execution copies; preserve originals and record the
   mapping. Break workflows into bounded stages when later inputs depend on
   discovering earlier results. Do not invent unresolved future dependencies.
5. Execute the captured script/helper tree with prepared paths, configuration,
   working directory and environment, using the captured package/tool resources
   without live-checkout or live-package fallback. Use argument lists and the
   selected Python interpreter, not shell interpolation. Capture exit status and logs.
   Agent-written files, GUI actions and external calls use the corresponding
   prepared handoff; their actual returned identities and outputs are recorded.
6. Recheck executed code/resource snapshots, consumed inputs and complete output
   contracts before publication.
   Record failures without partial publication. Persist execution state so an
   interrupted or uncertain execution is not automatically repeated. Recovery
   repairs publication of known results; a fresh production attempt gets new IDs.

Keep explicit `revise`, exact dependency edges, conflict handling, immutable
history and idempotent publication. When output B consumes output A, preserve
that relationship through supported multi-output contracts or separate completed
stages. Persisted manifests must remain usable after publication: temporary
execution paths cannot become the only references to their dependencies.

## Script requirements and enforcement limits

Scripts need ordinary explicit interfaces for their inputs, output destinations,
scratch, tools and behavior-affecting configuration. Remove hard-coded browsing
destinations and undeclared discovery where necessary. A domain helper may expand
its own manifest or validate a score without knowing anything about the ledger.
Such helpers stay with their owning skill; central lifecycle code moves into
artifact-bookkeeping. Test placement follows that ownership.

Standalone scripts no longer require ledger context. Move that requirement's
tests to the central managed entrypoint; retain domain validation, explicit-path
checks and no-clobber protections. Where fresh ledger allocation supplied the only
overwrite protection, add ordinary destination-exists and input/output-alias checks
before standalone writes.

Central checks enforce declared contracts, not arbitrary subprocess behavior.
Account for implicit I/O through declarations and inspected interfaces; OS-level
confinement remains separate. Preserve resource-closure checks without claiming
a hermetic machine or cross-platform certification.

## Implementation sequence

1. **Map the current behavior.** Use `docs/artifact-ledger-entrypoints.md`, actual callers
   and tests to list each operation's direct/indirect I/O, resources, validation,
   effects and enablement. Identify lifecycle code separately from domain code.
   Preserve the current dirty source snapshot and synthetic behavior fixtures.
2. **Establish the central boundary.** Adapt `artifact-bookkeeping/scripts/`
   lifecycle and Python/tool execution helpers to invoke ordinary commands.
   Document the central operation interface and its error/recovery behavior.
   Keep internal requests inside bookkeeping; reuse existing ledger schemas.
3. **Prove both simple and complex cases.** Convert syllabification, then Flow
   assembly. Remove reverse imports and bookkeeping flags; express their contracts
   in the Bookkeeping blocks. Demonstrate ordinary execution and managed execution
   with matching domain results, including clip-map expansion and separate output
   dependencies. Revise the design here before converting every producer.
4. **Convert the remaining routes.** Cover score inspection/rendering, analysis,
   vocal planning, acquisition/conversion, arrangement execution/rendering/delivery
   and browser checks, optional synthesis, and manual/GUI/external operations.
   Split mixed adapters into domain helpers and central lifecycle logic. Existing
   unavailable image routes stay unavailable; missing resources remain explicit.
5. **Remove the old integration and align guidance.** Delete superseded lifecycle
   adapters, flags, imports and test mocks after replacing their coverage. Update
   `AGENTS.md`, skill blocks/references, ledger usage/entrypoint documentation,
   `docs/artifact-ledger-entrypoints.md`, and ownership/provenance in `docs/skill-imports.json`.
   Change only fields needed by this refactor; preserve unrelated work. Update
   tests that currently require each producer to call its own lifecycle adapter.

Each converted route must have one active managed path before its old path is
removed. During transition the central inventory identifies the applicable path;
do not wrap an already-managed producer in a second prepare/finalize lifecycle.
Keep old/new differences out of the final production instructions.

## Acceptance checks

- **Dependency boundary:** inspect imports and subprocess/dynamic invocation paths.
  No production implementation calls bookkeeping code or requires ledger flags,
  callbacks, special imports or registration. Integration tests may call both
  sides; skill-local domain tests must work without loading bookkeeping.
- **Domain parity:** retain meaningful algorithm/CLI fixtures. Compare standalone
  and managed results; explain intended differences such as allocated paths and
  recorded provenance. All claimed-enabled operations get coverage, not just the
  two initial examples. Verify that existing destinations and input/output aliases
  are rejected without changing original bytes.
- **Lifecycle parity:** exercise invalid/ambiguous inputs before execution, exact
  indirect input binding, changed snapshots, missing/extra outputs, conflicting
  revisions, failure without partial publication, interrupted finalization and
  recovery without rerunning production. Include uncertain external outcomes.
  Change live code/packages after preparation and verify execution still uses the
  prepared versions.
- **Declaration sufficiency and fresh-agent behavior:** run the required cases in
  [the interactive protocol](../artifact-bookkeeping-decoupling-validation.md) after
  implementation. It tests real agent execution, block-only onboarding, indirect
  inputs, manual work and recovery separately from automated fixtures. Require no
  central-code changes or adapter registration for the new test skill; inventory
  updates remain audit records.
- **Portability and scope:** run applicable tests with paths containing spaces and
  Unicode; test the generic execution boundary on Linux, macOS and Windows where
  hosts are available. Mark unavailable host/resource/manual gates untested or
  blocked. Native backend portability and human creative acceptance remain
  separate from this refactor's success.

Require the dependency, domain, lifecycle, declaration and fresh-agent checks
above for acceptance. Report missing host/resource/manual checks as blocked or
untested, never passed, and identify any required check preventing acceptance.
This plan authorizes no implementation or live production by itself.
