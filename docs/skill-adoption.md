# Collaborator skill adoption

The default workflow retains the collaborator's reviewed transcription, arrangement
research and video methods. This cleanup keeps their used code, adapts configuration
and I/O, and excludes historical experiments and song artifacts. It does not merge
retired local musical algorithms into them.

## Sources and retained scope

The supplied `Skills` bundle is dated 2026-09-29; its 187 imported files were
hash-verified before cleanup on 2026-10-05. The original Dropbox bundle remains
untouched. [skill-imports.json](skill-imports.json) records original relative paths
and hashes, retained/adapted/extracted/excluded decisions, current source hashes,
and ownership of all retained implementation code. Imported text uses LF line
endings; schema layout whitespace is normalized without changing definitions. Required MusicXML schema
provenance stays with the schemas. External resource licenses stay with those
resources and are required for publication.

| Skill | Retained implementation |
| --- | --- |
| [score-to-musicxml](../.agents/skills/score-to-musicxml/SKILL.md) | Staff geometry, MusicXML schema/musical audit and reviewed-state hash checking; independent source and engraving review remain required. |
| [song-arrangement-research](../.agents/skills/song-arrangement-research/SKILL.md) | Brief compilation, baseline percussion variations, source-built Java adapter, sample routing/rendering, invariant checks and publication/delivery helpers. |
| [barnsang-video](../.agents/skills/barnsang-video/SKILL.md) | Image generation/editing, sequential continuity instructions, data-driven Flow handoff and timeline/assembly. Flow generation remains manual. |

Acquisition and the five analysis/vocal skills remain optional. Their I/O now uses
the same local configuration/path boundary. Synthesis retains the Nishiren ONNX
adapter; unsupported timing, missing phonemes/models and unavailable backends fail
explicitly. RVC remains instructions for an external tool.

The five overlapping skills `sheet2xml`, `arrange-score`, `xml2midi`, `midi2music`
and `mix_validate` are retired in Git history. All seven orphan root scripts, Bash
launchers, machine-specific Claude settings, vendored toolkit materials, historical
experiment code and imported song/run examples are removed. No archive of unused
implementations is maintained inside the repo.

## Shared boundary

Follow [configuration](configuration.md) and [the local TOML example](../config.local.example.toml).
Canonical Python entrypoints load the shared reader, take explicit artifact paths,
and validate containment beneath `paths.data_root`. External executable argument
lists and resources come from local TOML; missing prerequisites stop the stage.
Artifacts include JSON, prompts, reports and song builders, not just binary media.

Path validation alone does not record provenance or revision history. The
[implemented ledger](artifact-ledger-usage.md) adds those records through managed
operations; [adapter coverage](artifact-ledger-entrypoints.md) remains partial. It does
not sandbox arbitrary third-party software. Existing shared-data folders and
files were not migrated.
Legacy execution payloads can still contain absolute paths and must be regenerated
or validated on another machine.

## Known production gaps

- Deterministic arrangement execution needs an approved baseline; initial pitched
  arrangement creation is not supplied by this retained route.
- The upstream MIDI audit helper is absent. Execution/rendering require a configured,
  proven helper with the expected contract and stop if it is unavailable.
- No JDK/toolkit JAR was available here for actual Java compilation. Tests exercise
  command construction with stubs; toolkit compatibility remains unverified.
- Final recorded-vocal alignment/mixing remains open. Optional synthesis does not
  implement a complete vocal-production pipeline; its accepted event timing is
  narrower than the planner's general output.
- Production sample rendering, paid image APIs, manual Flow generation and a full
  representative-song run require their real resources and source/listening/visual
  review. Linux fixture tests do not certify Windows/macOS external installations.

## Validation

All 34 synthetic tests pass and exercise the configured direct entrypoints from another working
directory with spaces, input preservation, invalid-path/resource rejection, score
schema/geometry checks, arrangement hashes/invariants, optional vocal contracts and
two different video configurations. External commands/APIs use test doubles.
A fresh temporary Python environment and a staged-only checkout passed these checks
on 2026-10-05; neither used the current machine's local TOML or production assets.
