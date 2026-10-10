---
name: score-to-musicxml
description: Transcribe scanned or photographed sheet music into carefully verified MusicXML, especially single-staff melodies with Swedish lyrics and chord symbols. Use when converting score images, correcting optical music recognition, preserving source notation and verse text, or reviewing MusicXML against a scan. Includes slope-aware staff geometry, per-song evidence, independent source review, engraving and playback checks.
---

# Scanned score to MusicXML

## Bookkeeping

Use [artifact-bookkeeping](../artifact-bookkeeping/SKILL.md) with these local declarations.
The ordinary script interfaces are documented below:

- Geometry: inputs `source`, `seeds`; outputs geometry JSON and overlays;
  resources OpenCV/NumPy. The source preview is 1600 pixels wide; each system
  emits source, grid and dewarped PNGs plus the shared geometry JSON. Transcription also consumes every inspected crop, grid
  and `geometry.json` file, plus source pages and applicable editorial decisions.
- Verification: input `score`, optional `expectations` and `reference`; resource
  lxml and bundled schema files. Settings include the independently reviewed
  file hash; reference and hash must be supplied together. Stdout-only verification is inspection; `--output` produces a report.
- PDF review pages: `render_pdf.py` consumes input `pdf` and resource `pdftoppm`,
  publishing page PNGs and its tool log. Persisted visual reviews pin this bundle
  and the exact PDF; the renderer needs a reviewed font/data closure, inherited
  native-tool environment and 150 dpi. Output bounds are 1–256 pages plus one log.
- Manual transcription/review: deliverables are listed below. Persisted reviews
  consume completed verification reports; executed helpers are code dependencies.

## Repository paths and Python

Read [adoption notes](../../../docs/skill-adoption.md) and
[artifact contracts](../../../docs/artifact-contracts.md). Run the repo environment's
Python (`env/bin/python` on POSIX; `env/Scripts/python.exe` on Windows) and resolve
configuration with `python -m scripts.read_config`. The commands below use `python` to
mean that interpreter. Artifact arguments resolve relative to `paths.data_root`;
absolute paths must also stay inside that root. All generated score data, builders,
geometry and review records belong there. External tool locations belong in
`config.local.toml`. `--config-root` optionally selects a repository configuration
root; the default works independently of the current directory.

Treat the supplied edition as the authority. A familiar melody, plausible harmony, successful schema validation, or convincing playback does not establish source fidelity. Preserve unusual source readings; flag unresolved ambiguity rather than silently substituting a conventional version.

## Scope and user decisions

Do not treat uncertainty as permission to remove lyrics, replace notation, or otherwise broaden a requested edit. A request to remove confirmed protected lyrics authorizes that subset only. Retain unresolved material and ask before changing it; an unanswered optional question is not authorization. Respect the user’s prior rights research and explicit scope.

## Resuming an existing collection

Read the project’s `AGENTS.md`, `CONTEXT.md`, `HISTORY.md` and recorded user decisions before editing. Use those files to recover the accepted state and outstanding items; do not assume a new session should restart completed work. After accepted changes, update the handoff and decision history.

Preserve later user edits even when they differ from an old reviewed file: expose
that accepted reference separately, investigate the change, and record which version
is primary. PDF/XML agreement alone is not independent source review. A renderer
may omit grace attacks or rewrite beams; preserve source-correct notation and
record the rendering difference. Do not run a melody-only builder over a later
chord-bearing score without checking its scope.

## Workflow

1. Inventory every score and continuation page. Inspect images, existing project instructions, and the destination format. Preserve originals. Identify titles, credits, staff systems, clefs, key and time signatures, pickup measures, repeats, endings, chord symbols, lyric underlay, additional verses, and musical directions. Exclude decorative artwork.
2. Track each song with an explicit completion status. If parallel agents are authorized, use one owner per song, then another reviewer; keep shared helper edits with the coordinator. Complete all requested songs, not just examples.
3. Fit **all five staff lines locally, with slope and curvature**. Use `scripts/slope_grid.py` or an equivalent source-derived model. Seeds and measurements use a documented image coordinate system. Inspect every overlay: a numerical fit can follow the wrong ridge. Read pitches relative to the local curves at each notehead's x coordinate, including ledger lines. Record source-observed notehead centers independently of the expected pitch. Read accidentals, stems, beams, dots, ties and slurs separately. Record the source evidence and reason for any change to a geometry tolerance.
4. Transcribe the actual source measure by measure with exact rational durations and chord onsets. Inspect the source before consulting old XML or recognizer output. Preserve explicit system breaks, source meter symbols, repeat structure, text spelling and punctuation. Keep prose verses as text unless the source explicitly provides note underlay. Do not add guessed chords, notes, repeats or tempo. See [notation and evidence](references/workflow.md).
5. Generate deterministic MusicXML plus editable transcription data and a reproducible builder. Validate against the official MusicXML XSD and run musical consistency checks. Existing helper `scripts/validate.py` provides structural auditing and canonical snapshots; see [tool setup](references/tools.md). A partial measure needs a documented source-derived exception. Check counts, lyric syllabification, chord timing, accidentals, ties/slurs, repeat playback and every system boundary.
6. Obtain a separate source review. Compare every note, rhythm, chord, lyric and notation with the source; resolve discrepancies with image evidence. The reviewer must not merely endorse the builder's data. Freeze a canonical `reviewed_reference.json` only after that review. Record the exact reviewed file SHA256 alongside the canonical snapshot: canonical helpers can omit harmony or expressive details. Both must match before reporting continued acceptance. A frozen snapshot protects reviewed decisions from later changes; it is not an independent source oracle. If a later file differs, preserve it, investigate the difference and establish the user’s intent before overwriting it.
7. Render the final XML and inspect every page for clipping, missing verses, collisions, chord spelling and layout. Export it back to MusicXML and compare musical objects. Account explicitly for harmless direction-text splitting by the renderer, while requiring all ordered text to survive. Provide melody-only and melody-with-chords playback if requested or part of the established output format. Compare raw MIDI events with the XML; playback plausibility is supplementary.
8. Recheck changed files, update the project index and reviews, and report exactly which songs are complete, any source ambiguities, and layout deviations. Do not claim perfection or listening/review that did not occur. Keep uncertain songs visibly unresolved.

## Deliverables

Deliver the score `.musicxml`, `build.py`, `transcription.json`,
`source_expectations.json`, source hashes, `lyrics.txt`, `REVIEW.md`,
`INDEPENDENT_REVIEW.md`, and the reviewed canonical snapshot. Include source grids
and coordinate evidence, rendered PDF/PNG, roundtrip XML, MIDI checks and requested
playback. Provide an index with direct links and per-song status; bookkeeping
allocates the collection's storage.

Read [tool setup](references/tools.md) before configuring recognizers/renderers.

## Adding accompaniment when requested

Distinguish faithful transcription from an authorized chord-addition pass. If chords are missing and the user requests accompaniment, search separate chord sheets by title and alternate-language title, confirm the tune, transpose into the accepted melody key, and align changes to actual phrases and rational measure offsets. The chord sheet need not be the identical edition. Document source URLs, source/target keys, transposition, substitutions and adapted onsets. A source accompaniment may support a labelled harmonic reduction when printed chord letters are unavailable. Preserve the melody and lyrics; do not silently rewrite them to fit chords.

Retain the exact pre-chord MusicXML revision and add a reversible harmony layer. Validate every chord root/kind/bass/degree and its onset, and verify all non-harmony notation stays unchanged. Preserve user edits with full-file hash guards. Retain separate melody and chord previews, and make the chord-bearing version the primary download when that is the requested deliverable. Playback is supplementary; mark voicing as editorial.
