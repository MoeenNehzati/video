# Retained workflows and artifact requirements

This audit records the contracts of the collaborator's three retained skills.
Their musical and visual methods remain the baseline; older repo implementations
are not being merged into them. The later [artifact ledger plan](artifact-ledger-plan.md)
records the agreed global, append-only history design and supersedes the earlier
per-artifact-manifest recommendation. The ledger is implemented, with partial
producer integration documented in [usage](artifact-ledger-usage.md) and the
[entrypoint inventory](artifact-ledger-entrypoints.md); the workflow requirements below
still apply.

Before pipeline work, resolve configuration with `env/bin/python -m scripts.read_config`.
Use its `paths.data_root` and pass explicit paths to tools. Machine settings belong
in `config.local.toml`; shared artifact references must survive different local
Dropbox mount paths. Code lives in the repo, media and project data in Dropbox.
Preserve existing organization; migration is not automatic. Managed operations
record exact dependencies and immutable revisions, while unavailable entrypoints
stop before production. Path validation alone does not provide that provenance.

## 1. Source scores to reviewed MusicXML

Source: [score-to-musicxml](../.agents/skills/score-to-musicxml/SKILL.md).

- **Inputs:** original scan/PDF/photo pages, including continuations; applicable
  collection decisions; optional existing XML explicitly identified as a draft or
  reviewed version. One song can have several source editions and XML variants.
- **Outputs:** MusicXML, editable transcription data and builder, source expectations
  and hashes, staff geometry evidence, lyrics, review records, and a reviewed canonical
  snapshot. Keep engraving, roundtrip XML, MIDI checks and requested playback with
  the version they verify.
- **Acceptance:** source comparison by an independent reviewer, schema and musical
  checks, inspected engraving, and documented ambiguities. Record the exact reviewed
  XML hash alongside the canonical snapshot; a structural pass alone is not source
  fidelity. Preserve a later user-edited XML as a distinct state until reviewed.
- **Dependencies:** a chord-bearing XML may depend on a reviewed melody XML and a
  separate chord source. Retain the exact pre-chord version and distinguish faithful
  transcription from authorized editorial harmony.

## 2. Research, arrangement, and instrumental renders

Sources: [song-arrangement-research](../.agents/skills/song-arrangement-research/SKILL.md),
[brief contract](../.agents/skills/song-arrangement-research/references/brief-contract.md),
[adapter](../.agents/skills/song-arrangement-research/references/barnsang-adapter.md),
and [external requirements](../requirements/requirements.md).

- **Inputs:** exact approved XML, melody MIDI and chord timing; research evidence;
  arrangement decisions; and, for controlled variations, a named baseline and its
  exact MIDI hash. Initial arrangement creation must also work without a baseline.
- **Outputs:** `research.json`, `arrangement_brief.json`, compiled instructions and
  execution plan; per-variant parameters, native `.sng`/`.mix`, exported MIDI,
  track maps and verification records; instrument-library provenance and licenses.
- **Rendering:** one MIDI performance can have several sample palettes, room/gain
  settings, layer selections and encodings. Identify each render configuration and
  its exact MIDI separately. Record actual output roles: full guide preview,
  backing-only, or named stem. Separate stem export is a requirement to settle,
  not a claim that every current renderer supports it.
- **Acceptance:** verify unchanged source hashes, melody/chord/meter/tempo invariants,
  intended changes, sample coverage, note pairing, loudness/peaks and actual playback.
  Backing removes precisely the guide, preserves alignment/frame count and uses the
  same master gain as the full preview. Record listening-review status independently.
- **Dependencies:** preserve native project and exact MIDI as separate deliverables.
  JJazzLab can regenerate different guitar voicings, and post-export controller
  automation may exist only in the MIDI. A native project is not an exact rendering
  recipe without its library routing and processing settings.

## 3. Storyboard, visual production, and video assembly

Source: [barnsang-video](../.agents/skills/barnsang-video/SKILL.md).

- **Inputs:** reviewed song/lyrics, exact selected audio and timing, recorded creative
  decisions, character references, and the accepted prior visual state when revising.
- **Outputs:** storyboard/timing, character sheets, continuity keyframes, Flow handoff
  kit and instructions, downloaded clip rounds, selected clips, assembly timeline,
  final film and requested delivery encodings. Preserve generation prompts/settings
  and source identities with each result.
- **Acceptance:** inspect reference consistency, first/last-frame matching, contact
  sheets, lyric/story order and joins; record chosen takes and timing transforms.
  The assembly depends on the exact audio and clips, not merely their song name.
- **Kit boundary:** the skill's clean-current-pictures rule applies to a particular
  Flow handoff kit. An archived version must remain reproducible after its replacement
  kit is produced; decide how kits and source-image history relate before automating
  deletion. Final video timing must identify whether it uses demo or final vocal audio.

## Requirements for storage and the ledger

Each result needs a stable identity, song association, kind, readable label, creator,
creation time, exact parent inputs and hashes, output files/roles, settings and tool
versions, and explicit completion/review evidence. Existing detailed parameter and
review records should be referenced rather than duplicated into a second authority.

These relationships form a graph: multiple sheets can feed one XML; one XML can have
multiple arrangements; an arrangement can inherit a baseline; one performance can
have multiple renders; a video combines audio, images and clips from different runs.
Distinguish a revision from a sibling alternative, and record superseded/accepted
decisions without choosing a version merely because its timestamp is newest.

Concurrent collaborators must create independent results without allocating the
same next version number or rewriting one shared catalogue. Discovery must recognize
partly synchronized outputs and validate files/hashes before reuse. Cross-machine
paths must resolve against configuration. A searchable catalogue can be derived;
it need not be the only durable record of artifact relationships.

The global ledger holds authoritative dependency and change records; the
catalogue derives current and historical views from its events. Per-artifact
sidecars are not authoritative. The directory layout supports
ordinary browsing without being the only record of ancestry. Compare layouts
against the branched examples in the [plan](artifact-ledger-plan.md) before changing
any Dropbox artifacts.

## Execution boundaries after cleanup

The retained scripts use the shared configuration reader and explicit data-root
paths. Machine tools/resources are configured in local TOML; see
[configuration](configuration.md). Historical song data, vendored software, shell
launchers and orphan programs are excluded. Video handoff/assembly take explicit
run inputs; FluidSynth loads its configured native library only when rendering.

The arrangement route still starts from an approved baseline. Its external MIDI
audit helper is absent from the supplied bundle and must be recovered and checked
before production execution. Java compilation and the chosen sample banks require
real toolchain validation. Initial pitched-arrangement creation and final
recorded-vocal alignment/mixing remain open capabilities.

The [ledger implementation](artifact-ledger-usage.md) supports multiple
XML/arrangement/render alternatives, relocated roots, stale hashes and concurrent
updates. Producer adapter coverage remains partial and final interactive acceptance
is blocked. Synthetic tests establish code integration, not musical or end-to-end
production acceptance. Existing Dropbox artifacts are not migrated automatically.
