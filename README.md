# Children's music videos

Skills and reusable code for turning sheet music into children's music videos.
Git holds instructions, reusable code and required support files. Song artifacts
live under configured `paths.data_root`; external software and models stay outside
the checkout. Reproducible repository reports and build intermediates go in ignored
`_build/`.

## Skills

Default workflow: `score-to-musicxml` → `song-arrangement-research` → `barnsang-video`.
Score acquisition and the analysis/vocal steps are optional.

| Skill | What it does | Tools / pipeline |
| --- | --- | --- |
| [score-to-musicxml](.agents/skills/score-to-musicxml/SKILL.md) | Transcribes scanned sheet music into reviewed MusicXML. | Visual transcription + OpenCV staff geometry → schema checks, independent source review and MuseScore engraving. |
| [song-arrangement-research](.agents/skills/song-arrangement-research/SKILL.md) | Researches a song and varies an approved arrangement. | Research brief → JJazzLab Toolkit/MIDI percussion variants → FluidSynth + FFmpeg audio. |
| [barnsang-video](.agents/skills/barnsang-video/SKILL.md) | Creates an animated music video. | Storyboard → OpenAI images/edits → manual Google Flow clips → FFmpeg assembly. |
| [download-scores](.agents/skills/download-scores/SKILL.md) | Finds and downloads scores, MIDI and lyrics. | Web search/direct URLs; MuseScore format conversion and optional Audiveris score recognition. |
| [analyze-music](.agents/skills/analyze_music/SKILL.md) | Extracts melody, harmony, rhythm and phrase information. | Python/music21 parses MusicXML → `music_analysis.json`. |
| [syllabify-lyrics](.agents/skills/syllabify_lyrics/SKILL.md) | Splits lyric text into words and syllables. | Explicit hyphens + Python syllable heuristics → `lyrics.json`. |
| [plan-vocals](.agents/skills/plan_vocals/SKILL.md) | Aligns lyric syllables to melody notes. | music21 note extraction + Python alignment heuristics → musical review of `vocal_events.json`. |
| [synthesize-vocal-with-diffsinger](.agents/skills/synthesize_vocal_with_diffsinger/SKILL.md) | Renders planned notes and lyrics as a sung WAV. | Reviewed vocal events + phonemes → Nishiren DiffSinger models via ONNX Runtime. |
| [refine-vocal-with-rvc](.agents/skills/refine_vocal_with_rvc/SKILL.md) | Changes an existing vocal's timbre. | External RVC/SVC tool and voice model → timing and intelligibility review. |

## Adding a skill: bookkeeping

Production skills own their domain methods, scripts and tests.
[Artifact-bookkeeping](.agents/skills/artifact-bookkeeping/SKILL.md) owns artifact
organization and execution. The agent loads it for every artifact operation,
including implicit tool I/O and manual/external work.

A new skill integrates through one short `Bookkeeping` block in `SKILL.md`.
Declare each operation's inputs (including indirect references), outputs versus
scratch, resources, settings and domain constraints. For example:

```markdown
## Bookkeeping

Use artifact-bookkeeping with these local declarations:
- Syllabification: input lyrics text; output lyrics JSON; setting language.
- Use the ordinary script interface documented below. No score is consumed.
```

Keep script interfaces ordinary: explicit paths/settings, domain validation and
clear failures. Scripts must not import or call bookkeeping code or require ledger
flags. The block supplies local declarations; execution procedures stay in the
central skill. No per-skill bookkeeping adapter or runtime registration is needed.

## Setup

Use Python 3.11+ and the repo-root `env/`. Follow
[requirements](requirements/README.md) to create or reuse the environment, then
[configuration](docs/configuration.md) to set local paths and the selected stage's
dependencies in ignored `config.local.toml`.

Run `env/bin/python -m scripts.read_config` from the repo root to check setup.
On Windows, use `env/Scripts/python.exe` for Python calls. Native-tool platform
support is separate from Python support; see the configuration guide.

## Scope

This is not yet a validated end-to-end production workflow. Initial pitched
arrangement creation and final recorded-vocal alignment/mixing remain open;
Flow work is manual and automated image generation/editing is disabled.
Each skill states its own prerequisites and limitations. See
[supported routes](docs/artifact-ledger-entrypoints.md),
[cross-stage contracts](docs/artifact-contracts.md) and
[practical validation](docs/artifact-bookkeeping-decoupling-validation.md).

Run local fixture tests with `env/bin/python scripts/run_tests.py`.
Tests do not require paid API calls or production media/models.
