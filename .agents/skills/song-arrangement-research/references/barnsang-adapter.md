# Configured arrangement adapter

The retained adapter starts with an approved arrangement. Creating that baseline
is a manual/external step; no historical song builder is retained.

## Prerequisites

Install tools outside the repository and set their local paths. See the repository
[configuration guide](../../../../docs/configuration.md). Required keys:

| Stage | Configuration |
| --- | --- |
| Native projects | `tools.java.command`, `tools.javac.command` (Java 25+); `resources.jjazzlab_toolkit` (Toolkit 5.2.1 jar), `resources.jjazzlab_rhythms` (directory) |
| Verification | `resources.midi_audit`: the proven external `audit_existing_midi.py`, exporting `read_midi(path)` and `triples(track, ppq)` |
| Audio | `resources.fluidsynth_library`, `resources.soundfont_manifest`, `resources.soundfont_credits`; `tools.ffmpeg.command` |
| Listening-page check | `tools.browser.command` (Chromium-family executable); Python Playwright package |

The upstream MIDI decoder was absent from the imported bundle and has not been
recovered locally. Execution and rendering stop before generating artifacts when
it is not configured. Merely supplying two callable names does not establish that
a replacement decoder is correct; recover and validate the proven implementation
before enabling this route. Python dependencies are in repository requirements.
The Java source is compiled into a temporary directory; Java/toolkit execution has
not been qualified against a real installation in this cleanup.

`soundfont_manifest` is an external JSON object mapping bank names to
`{"path": "path/to/bank.sf2", "credits": "source and license attribution"}`.
Relative SF2 paths resolve beside the manifest; all libraries stay outside Git.
Required routing names are `generaluser`, `salamander`, `nylon`, `steel`, `bass`,
`clarinet`, `drums`, plus the baseline's `counter_library` if different. Presets
are inspected from the SF2; the supporting part uses its selected library's first
preset. `soundfont_credits` must contain the full required attribution/license text
for the selected resources and is copied to each rendered delivery.

## Preserved behavior

- Pitched notes, baseline expression, program changes and tempo remain frozen;
  only declared percussion note events change. Native projects regenerate style
  voicings and do not reproduce all post-export controller automation.
- Melody/source hashes, chord timing, meter, tempo, note pairing and native reload
  checks run before rendering. Child-note and backing-removal checks are separate.
- Missing pitched samples fail. Missing dedicated percussion samples route to
  documented GeneralUser percussion; logs name those pitches.
- Full preview includes the guide melody. Backing removes precisely that track,
  shares the full mix gain and has an identical frame count. No independent backing
  loudness normalization occurs.
- Defaults remain 48 kHz stereo, 24-bit WAV, 320 kbps MP3, target -18.3 LUFS and
  true peak at most -1.5 dBTP (measurement tolerance .01 dB). Explicit render CLI
  arguments can change the target/ceiling, which are recorded in logs.
- Publishing produces a local A/B page and catalogue from explicit reports.
  Delivery checks verify hashes, WAV format/alignment, preview loading, A/B tempo
  position and mobile layout using the configured browser. Human listening stays
  pending until actually performed.

All project inputs/outputs use configured data-root paths. Failed generation may
leave partial outputs; inspect them and allocate a fresh version before retrying.
There is no transaction or ledger integration in this cleanup.
