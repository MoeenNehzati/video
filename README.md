# Children's Music Video Pipeline

This project turns sheet music into entertaining music videos for children.
It combines music arrangement, AI-generated singing, and video production.

---

## Getting the project

**Option 1 — Download as a ZIP** (no tools required):
Go to [github.com/MoeenNehzati/video](https://github.com/MoeenNehzati/video),
click the green **Code** button, and choose **Download ZIP**.

**Option 2 — Clone with git** (command line):
```bash
git clone https://github.com/MoeenNehzati/video
```

---

## How the project is organized

This project uses two places to store files.

**This repository (GitHub)** stores text-based files: scripts, skill definitions,
lyrics as plain text, song catalogs, and documentation. Only text files belong
here — things you can open in a text editor and read directly.

**Google Drive** stores large binary files that cannot go into git: sheet music
PDFs, audio files (MP3, WAV), MIDI files, images, and video exports.
See [docs/drive](docs/drive/README.md) for the Drive folder structure.

**The rule:** if you can open it in a text editor and read it as plain text, it
goes in this repository. If it is a PDF, audio file, image, or video, it goes on Drive.

### Project layout

```
assets/          legacy script/test data path (gitignored)
bin/             command wrappers and the shared configuration reader
docs/            project documentation
references/      shared pipeline reference material and schemas
requirements/    pinned Python and tool dependencies
scripts/         shared helpers and standalone utilities
tests/           automated tests
third_party/     external tools (DiffSinger, etc.)
config.toml      shared configuration defaults
config.local.toml  local configuration overrides (gitignored)
AGENTS.md        shared project instructions (canonical)
CLAUDE.md        symlink to AGENTS.md
.agents/skills/  shared skills (canonical; discovered directly by Codex)
.claude/         Claude skill symlink, local settings, and pipeline docs
```

### Pipeline stages

```
Sheet music (PDF/image)
  → sheet2xml      scan with Audiveris → MusicXML
  → arrange-score  arrange/restyle     → MusicXML
  → xml2midi       export              → MIDI
  → midi2music     render              → audio (WAV)
  → [vocals]       DiffSinger + RVC    → vocal WAV
  → mix_validate   mix + validate      → final WAV
```

### Requirements

See [requirements/README.md](requirements/README.md) for setup instructions.
Repo Python scripts use the `env/` virtual environment. Install the listed Python
requirements and system tools (MuseScore, FluidSynth, Audiveris, ffmpeg, etc.);
external voice models and the optional OpenVPI backend require separate setup.

Arrangement tests in `tests/test_arrange_score.py` require local score fixtures
under `assets/`.

---

## Local configuration

`config.toml` contains shared defaults and belongs in Git. Root
`config.local.toml` is ignored by Git. Put all configuration additions and changes
in the local file. Tables merge recursively; local scalars and lists replace
shared values, preserving other shared keys.

Use the shared reader (Python 3.11+) instead of merging files yourself:

```bash
# From the repository root:
env/bin/python -m bin.read_config
# From any directory:
/path/to/repo/env/bin/python /path/to/repo/bin/read_config.py
```

Both commands print the resolved configuration as JSON. Python code with the
repository root on its import path uses the same implementation:

```python
from bin.read_config import load_config

config = load_config()
data_root = config["paths"]["data_root"]
```

The reader never writes files. Imported values retain their TOML types; the JSON
output represents dates and times as ISO strings and rejects non-finite numbers.
Missing shared configuration, malformed files, and invalid data paths fail rather
than silently using defaults. The local file is optional when shared values suffice.

Set `[paths].data_root` in `config.local.toml` to the absolute path of an existing
project-data directory. If the resolved path is missing or invalid, the agent asks
for the directory, creates or updates only the local file, and reruns the reader.
Other local settings are preserved. No template needs to be copied manually.

Agents use the resolved paths in tool calls and explicit script arguments.
Existing pipeline scripts do not yet call the reader automatically; their legacy
`assets/` defaults still apply unless overridden. Check the reader with
`env/bin/python -m unittest discover -s tests -p 'test_read_config.py'`.

---

## Working with Codex and Claude

Launch Codex or Claude Code from the project root. Both use the same project
instructions and skill files, with Codex's discovery paths as the canonical sources:

```text
AGENTS.md                              shared project instructions
CLAUDE.md -> AGENTS.md                  Claude instruction entrypoint
.agents/skills/<skill>/SKILL.md         shared skill definitions
.claude/skills -> ../.agents/skills     Claude skill discovery entrypoint
```

Edit `AGENTS.md` and `.agents/skills/` directly. Adding a skill under
`.agents/skills/` makes it available to both platforms without another symlink.
Restart existing sessions after adding skills to ensure discovery.

Invoke a skill with `$arrange-score` in Codex or `/arrange-score` in Claude Code,
or ask either agent to use it by name. The skill names below work on both platforms.

Use a checkout that preserves symbolic links. If a ZIP extractor or Git checkout
materializes a link as a plain text file, restore the links shown above before
using Claude Code.

Project references (read when needed):

- `AGENTS.md` — shared working instructions
- `.claude/README.md` — overall pipeline flows
- `.agents/skills/*/SKILL.md` — per-stage skill specs
  Code used by one skill lives in that skill’s `scripts/` folder. Code used by
  multiple skills, or with no skill owner, lives under root `scripts/`. Existing
  `bin/` commands invoke the appropriate implementation.
- [references/schemas/](references/schemas/) — schemas read or written by multiple
  skills. A schema used by only one skill lives in that skill’s `references/`
  folder. Legacy schemas without an owning skill also remain here.

### Skills

Each skill is one stage of the pipeline. They pass structured JSON files to each other.

**Acquiring and preparing scores**

- `download-scores` — downloads sheet music and MIDI files for songs listed in a CSV catalog
- `sheet2xml` — converts a sheet music PDF or image into MusicXML using Audiveris (OMR)
- `arrange-score` — takes a MusicXML score and produces a new arranged version based on a style goal (e.g. hip-hop remix, add violin and drums)

**Generating audio from the score**

- `xml2midi` — exports a MusicXML score to MIDI using MuseScore
- `midi2music` — renders a MIDI file to audio (WAV) using FluidSynth and a SoundFont

**Adding vocals**

- `analyze-music` — parses the arranged score into `music_analysis.json`: tempo, key, phrases, melody candidates
- `syllabify-lyrics` — parses `lyrics.txt` into `lyrics.json`: lines broken into syllables
- `plan-vocals` — takes `music_analysis.json` + `lyrics.json` and produces `vocal_events.json`, mapping each syllable to a melody note. This is the main LLM-assisted step.
- `synthesize-vocal-with-diffsinger` — turns `vocal_events.json` into a sung `rough_vocal.wav` using the Nishiren DiffSinger v2.0 ONNX voicebank
- `refine-vocal-with-rvc` — optional step that runs `rough_vocal.wav` through an RVC voice conversion model to improve timbre

**Mixing**

- `mix-validate` — renders the instrumental stem, combines it with the vocal, and exports `final_song.wav` along with a `mix_report.json` flagging timing, level, and masking issues

---

## Documentation

- [docs/drive](docs/drive/README.md) — Google Drive folder structure; where to find and put binary files
- [docs/music](docs/music/README.md) — song catalog, arrangement experiments, and musical insights
