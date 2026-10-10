# Children's music videos

Skills and reusable code for turning sheet music into children's music videos.
Song artifacts live in the configured Dropbox directory; external software and
models are installed separately.

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

Every skill that accesses song artifacts must use
[artifact-bookkeeping](.agents/skills/artifact-bookkeeping/SKILL.md). This includes
implicit reads and writes by tools, subprocesses, downloads, APIs and GUI actions,
as well as files written by the agent. Repository source/configuration inspection
is outside the song ledger.

The skill's only bookkeeping integration is a short `Bookkeeping` block in its
`SKILL.md`. Name artifact-bookkeeping and declare, per operation:

- **Inputs:** consumed files and their purpose, including files referenced inside
  manifests, prompts and other indirect inputs.
- **Outputs:** deliverables and retained reports/logs, separate scratch files, and
  any outputs with different dependencies or independent revision needs.
- **Resources/settings:** tools, packages, models, libraries and relevant options
  or configuration keys. Never include credentials.
- **Domain constraints:** input relationships, how embedded paths resolve, and
  any manual or external action requiring a handoff.

For example, a lyrics skill could include:

```markdown
## Bookkeeping

Use artifact-bookkeeping with these local declarations:
- Syllabification: input lyrics text; output lyrics JSON; setting language.
- Use the ordinary script interface documented below. No score is consumed.
```

The agent loads artifact-bookkeeping before artifact work and again when resuming,
including after compaction. The central skill supplies revision resolution,
preparation, captured execution or handoff, publication and recovery. Read-only
inspection needs no ledger event; persisted reports and reviews do.

Keep domain methods and ordinary CLI documentation in the production skill. Its
scripts accept explicit input/output/scratch paths and settings, retain domain
validation, and report failures. They must not import or call bookkeeping code,
require ledger flags, or implement ledger lifecycle steps. The Bookkeeping block
contains declarations, not request schemas or bookkeeping commands; no per-skill
bookkeeping adapter or runtime registration is required. See the central skill's
[usage guide](docs/artifact-ledger-usage.md) for execution details and
[supported routes](docs/artifact-ledger-entrypoints.md) for limitations.

## Setup

Use Python 3.11+. On POSIX:

```console
python3 -m venv env
env/bin/python -m pip install -r requirements/requirements-python.txt
```

On Windows use `py -3 -m venv env`, then `env/Scripts/python.exe` for Python calls.
Set an existing absolute `paths.data_root` in ignored `config.local.toml`, then run:

```console
env/bin/python -m scripts.read_config
```

See [configuration](docs/configuration.md) for external tool/resource keys and
[requirements](requirements/README.md) for installation boundaries. Run canonical
skill scripts through bookkeeping for song-artifact work, using the environment's
Python and prepared explicit artifact paths. Shared
path validation checks that inputs and outputs stay beneath `data_root`.

## Scope

The arrangement adapter varies an existing approved baseline. Initial pitched
arrangement creation and final recorded-vocal alignment/mixing remain open.
Arrangement verification requires a separately supplied MIDI audit helper. Video
production includes manual Flow work. Optional synthesis has explicit timing and
model restrictions. These are not claims of an end-to-end production run.

Git contains instructions, skill-used code and its support files. Dropbox contains
all song/run data, including text and JSON. The artifact ledger now records exact
revisions through managed operations; existing Dropbox data is not migrated.
Producer integration remains partial: see [usage and limits](docs/artifact-ledger-usage.md)
and the [entrypoint inventory](docs/artifact-ledger-entrypoints.md).
See [adoption and validation](docs/skill-adoption.md),
[artifact contracts](docs/artifact-contracts.md), and the
[cleanup plan](docs/repository-cleanup-commit-plan.md).

Run local fixture tests with `env/bin/python scripts/run_tests.py`.
Tests do not require paid API calls or production media/models.
