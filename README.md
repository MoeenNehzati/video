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

## Setup

Use Python 3.11+. On POSIX:

```console
python3 -m venv env
env/bin/python -m pip install -r requirements/requirements-python.txt
```

On Windows use `py -3 -m venv env`, then `env/Scripts/python.exe` for Python calls.
Set an existing absolute `paths.data_root` in ignored `config.local.toml`, then run:

```console
env/bin/python -m bin.read_config
```

See [configuration](docs/configuration.md) for external tool/resource keys and
[requirements](requirements/README.md) for installation boundaries. Run canonical
skill scripts with the environment's Python and explicit artifact paths. Shared
path validation checks that inputs and outputs stay beneath `data_root`.

## Scope

The arrangement adapter varies an existing approved baseline. Initial pitched
arrangement creation and final recorded-vocal alignment/mixing remain open.
Arrangement verification requires a separately supplied MIDI audit helper. Video
production includes manual Flow work. Optional synthesis has explicit timing and
model restrictions. These are not claims of an end-to-end production run.

Git contains instructions, skill-used code and its support files. Dropbox contains
all song/run data, including text and JSON. The [artifact ledger plan](docs/artifact-ledger-plan.md)
is a separate implementation task; this cleanup creates no ledger or new Dropbox
layout. See [adoption and validation](docs/skill-adoption.md),
[artifact contracts](docs/artifact-contracts.md), and the
[cleanup plan](docs/repository-cleanup-commit-plan.md).

Run local fixture tests with `env/bin/python -m unittest discover -s tests -v`.
Tests do not require paid API calls or production media/models.
