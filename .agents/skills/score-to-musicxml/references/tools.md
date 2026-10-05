# Tools and setup

Reuse project environments and installed applications. The helper dependencies are Python, numpy and opencv-python-headless for slope_grid.py; lxml for XSD validation. Music21, musicdiff, Pillow, a MusicXML renderer such as MuseScore, and FluidSynth plus a compatible soundfont support additional checks. Use maintained repository requirements and record actual tool/resource versions with each run. Do not assume an OMR engine preserves lyrics, harmony, directions or source layout.

## Bundled helpers

- scripts/slope_grid.py SOURCE SEEDS_JSON OUTPUT_DIRECTORY writes geometry.json, source strips, slope-aware overlays and flattened derivatives. Source pixels remain unchanged.
- scripts/validate.py is the import-only helper supplying audit(path, schema_path, expected) and canonical(path). schema/musicxml.xsd includes the bundled xml.xsd and xlink.xsd; provenance is in schema/SOURCE.txt.
- scripts/verify_score.py SCORE [--expectations JSON] [--reference JSON --reviewed-sha256 HASH] [--output REPORT] runs XSD/structural checks and, when supplied, a frozen canonical comparison. A successful result is not a source-fidelity certificate. Counts use a {"counts": {...}} object; partial-measure exceptions follow the validator's supported contract.

The validator is a starting point, not a universal notation verifier. Extend checks for new supported notation with targeted examples (e.g. ties, tuplets, repeats, alternate endings) and source review. Do not weaken checks simply to make a score pass.

## OMR

Audiveris can generate an independent candidate from cropped/dewarped systems. Keep raw outputs and log explicit OCR language settings (swe for Swedish) and versions. Compare pitch spelling, note onset/duration, lyrics and harmony separately. A note-sequence match or symbol-count match does not establish complete accuracy. Benchmark unseen inputs before correcting output; distinguish development examples from held-out evaluation.

## Portable execution and rendering

Always read/write JSON, Python and text explicitly as UTF-8 (read utf-8-sig when a BOM is possible). Windows default encodings can corrupt å, ä and ö.

MuseScore 4 worked through Python subprocess.run with individual `-o` exports to PDF, PNG, MIDI and MusicXML. Headless settings and audio export vary by installation; configure the external executable locally and verify its behavior before batch work. Use a MIDI-to-audio renderer such as FluidSynth when appropriate. Do not terminate unrelated application processes. Do not assume a launched GUI command has completed until output and exit status are verified.

Text-only page credits were sometimes omitted or moved beside the title by MuseScore. Explicit below-staff words directions with relative-x/relative-y rendered reliably; attach separate columns to suitable measures. Visually inspect all resulting text. Document any consolidation of a physical continuation page.

A failed sandbox image viewer can be bypassed by a read-only image tool or by returning PIL-generated image bytes through the environment's image display facility. Use subprocess argument lists and explicit configured paths.

## Concrete validation call

From the repo root use `python .agents/skills/score-to-musicxml/scripts/verify_score.py song/score.musicxml --expectations song/source_expectations.json --reference song/reviewed_reference.json --reviewed-sha256 HASH` with a reference only after separate source review. This wrapper always supplies the bundled official XSD. If importing the lower-level validator, use all three arguments: `audit(score_path, schema_path, expectations_dict)`. Calling `audit(score_path)` alone does **not** perform XSD validation. Require `issues == []`; never report an XSD pass from a structural-only call.

An expectations file can contain `{"counts":{"measures":17,"notes":65,"rests":4,"harmonies":9,"lyrics":65,"system_breaks":3},"partial_measures":{"1":"3/2"}}`. Partial durations are rational quarter-note values indexed by the XML measure number as a string. These exceptions must come from the source, not from measured output alone.

For explicitly parenthesized alternative notes, preserve the printed notation and record which alternative the preview uses. Do not silently turn an alternative into a two-note sung chord. Unresolved chord semantics can retain a literal printed label with an appropriately unspecified MusicXML kind; visibly flag the unresolved meaning and leave that chord interval unvoiced in preview audio. Check whether the renderer changes such labels or assigns a semantic interpretation on export.

Helper dependencies are maintained in the repository `requirements/requirements-python.txt`. Use the repository environment. Renderer/OMR/audio installations remain external, referenced through local configuration.

Printed chord labels are part of the reviewed reference: preserve `kind@text` and any root/bass display text as well as the semantic chord kind. The canonical comparator includes these attributes, so a literal unresolved label cannot silently change while its semantic `other` kind remains unchanged.

## Geometry command

`python .agents/skills/score-to-musicxml/scripts/slope_grid.py song/source.png song/seeds.json song/geometry`

All three arguments are explicit paths under `paths.data_root`. The output directory
must be new or empty. The 1600-pixel seed coordinate contract is described in
[workflow.md](workflow.md); inspect generated overlays before using the measurements.
The verifier's optional report path must also be new. Its exit status is nonzero
when structural, canonical or reviewed-file hash checks fail.
