# Cross-stage artifact contracts

These contracts describe what the retained score, arrangement and video workflows
exchange and what review evidence downstream stages require. Each production skill
owns its detailed method and local I/O declarations; [artifact-bookkeeping](../.agents/skills/artifact-bookkeeping/SKILL.md)
owns revision, publication and recovery rules. See [configuration](configuration.md)
for setup and [supported routes](artifact-ledger-entrypoints.md) for capability limits.

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
  exact MIDI hash. Initial pitched-arrangement creation without a baseline remains
  an open capability, not part of this automated route.
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

## Shared lineage and execution boundary

Cross-stage relationships form a graph: multiple sheets can feed one XML; an XML
can have alternative arrangements; one MIDI performance can have several renders;
and a film combines exact audio, images and clips. Each downstream artifact must
identify the revisions actually consumed, including intermediate results and
review evidence. A selected result and a reviewed result are different states.

Use [artifact-bookkeeping](../.agents/skills/artifact-bookkeeping/SKILL.md) for
identity, selection, immutable history, synchronization conflicts and publication.
Its [event contract](../.agents/skills/artifact-bookkeeping/references/event-contract.md)
and [lineage examples](../.agents/skills/artifact-bookkeeping/references/examples.md)
explain those rules. No separate per-stage sidecar is an authority for lineage.

The current automated arrangement route requires an approved baseline and a
separately configured MIDI auditor. Native tools, sample banks and optional models
need live qualification. Initial pitched-arrangement creation and final
recorded-vocal alignment/mixing remain open. Synthetic tests establish code
integration, not musical quality or [end-to-end acceptance](artifact-ledger-validation-plan.md).
Existing project data is not migrated automatically.
