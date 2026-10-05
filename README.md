# Children's music videos

Skills and reusable code for turning sheet music into children's music videos.
Song artifacts live in the configured Dropbox directory; external software and
models are installed separately.

| Workflow | Skill |
| --- | --- |
| Reviewed sheet transcription | [score-to-musicxml](.agents/skills/score-to-musicxml/SKILL.md) |
| Research and baseline arrangement variations | [song-arrangement-research](.agents/skills/song-arrangement-research/SKILL.md) |
| Storyboards, image generation, manual Flow handoff and assembly | [barnsang-video](.agents/skills/barnsang-video/SKILL.md) |

The collaborator's musical and visual methods are retained. Optional skills cover
[acquisition](.agents/skills/download-scores/SKILL.md),
[analysis](.agents/skills/analyze_music/SKILL.md),
[lyrics](.agents/skills/syllabify_lyrics/SKILL.md),
[vocal planning](.agents/skills/plan_vocals/SKILL.md),
[DiffSinger](.agents/skills/synthesize_vocal_with_diffsinger/SKILL.md) and
[manual RVC refinement](.agents/skills/refine_vocal_with_rvc/SKILL.md).

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
