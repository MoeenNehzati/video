---
name: song-arrangement-research
description: Research a song's background, approved lyrics and documented recordings, then create an evidence-linked arrangement brief and implement tailored JJazzLab/MIDI arrangements. Use for song-specific arranging and repeatable research-to-production workflows.
---

# Song arrangement research

## Bookkeeping

Use [artifact-bookkeeping](../artifact-bookkeeping/SKILL.md) with these declarations
and the ordinary CLI interfaces below:

- Brief compilation consumes brief/research JSON, `source_xml`, and the baseline's
  `parameters.json` plus its named MIDI; produces `execution_plan.json` and
  `PROMPT.md`. Source, baseline and research hashes must match. Paths in JSON
  resolve under configured `paths.data_root` unless absolute. Brief `output_root`
  is destination metadata validated for containment, not a consumed input; native
  execution selects its actual destination with explicit `--output-root`.
- Native execution consumes each plan, its sibling `PROMPT.md`, research, source
  XML/MIDI, baseline parameters/MIDI, `input.properties`, `chords.tsv`, `melody.tsv`,
  `upper.tsv`, `tracks.tsv`, `native_reload_verified.txt`, plus `bass.tsv` for
  trio/chamber and `strings.tsv` for chamber. Parameters identify the source files.
  Outputs under `--output-root/song_id/variant_id` are native project/mix,
  MIDI/backing MIDI, parameters, copied prompt/tables, participation and native
  verification reports, plus the explicit folder manifest. Native creation
  precedes frozen MIDI and `verification.json`. Native, MIDI and verification
  require independent revisions with those dependencies; a complete reusable
  folder bundle depends on all three, and the folder manifest refers to that
  bundle. `--scratch` is a new private
  compiler/preferences directory. Resources are Java/Javac, the toolkit jar,
  the complete rhythms directory and external MIDI auditor; Python needs mido.
- Rendering consumes the folder-list JSON, each listed folder's parameters, MIDI,
  backing MIDI, tracks and native reload report, and parameters' source XML/MIDI,
  baseline MIDI and child plan. Folder-list and parameter paths follow the same
  data-root rule. Outputs are audio/credits under `--audio-dir` (or `out-dir/audio`)
  and `verification.json` plus per-variant render logs under `--out-dir`; reports
  depend on their audio. Resources are the MIDI auditor, FluidSynth library,
  FFmpeg, soundfont manifest and every bank it names, and sample credits; relative
  bank paths resolve beside the manifest. Settings are target LUFS, peak ceiling,
  room and instrument routing; Python needs mido, NumPy, SoundFile, pyloudnorm,
  SciPy. Missing mapped samples fail; guide/backing share gain and frame count.
- Listening delivery consumes each render report plus its audio (full/backing
  WAV/MP3, credits), arrangement parameters, native project/mix, full/backing MIDI,
  prompt and participation text. Produces one portable bundle containing copies,
  HTML, catalogues and parameter logs; resource is `listening_page.html`, Python
  needs SoundFile. Report folder paths use the data-root rule; generated catalogue
  links resolve relative to the page and remain inside the delivery bundle.
- Browser checks consume reports, their referenced full/backing WAV/MP3/MIDI and
  native project/mix, plus the complete delivered page and linked files. Output
  is the explicit JSON report; `--scratch` holds private browser preferences.
  Resources are Chromium with its data/font/plugin closure, Playwright and
  SoundFile. No profile override or remote page links; actual human listening
  remains a separate review.
- Manual research, baseline creation and GUI edits declare inspected references,
  prompts, source files and exact returned deliverables before those actions.
  Tools/models, settings and external effects belong to the chosen stage.

All stages use resolved project configuration, ordinary explicit paths and reject
existing deliverables. Persistent plans, parameters and reports contain dependency
paths and hash checks; retained references must remain usable after publication.

## Repository execution

Read [adoption notes](../../../docs/skill-adoption.md) and
[artifact contracts](../../../docs/artifact-contracts.md). Resolve configuration
with `python -m scripts.read_config` using the activated repo environment (POSIX:
`env/bin/python`; Windows: `env/Scripts/python.exe`). All script commands below
use that Python. Inputs/outputs must be explicit and inside `paths.data_root`;
external tools, sound libraries and installation paths belong in `config.local.toml`.
Never write song artifacts beside this skill. See [adapter setup](references/barnsang-adapter.md).
The current route makes controlled percussion variants of an approved baseline;
it does not create an initial pitched arrangement. Missing external verification
code is a blocking prerequisite, not permission to skip checks.

Turn song-specific evidence into concrete musical decisions and reproducible arrangements. JJazzLab does not accept natural-language prompts: Codex interprets the brief, implements supported toolkit/MIDI operations, and renders with explicitly mapped sample libraries. Do not pretend that a prompt alone was executed by JJazzLab or launch another Codex/API session unnecessarily.

## Establish the source and scope

Read project AGENTS.md, current context/history and user decisions. Identify the exact approved score, MIDI melody, chord timing, baseline arrangement. Preserve source hashes. Keep existing full chord accompaniment, bass movement and beat when adding motifs unless the user requests a thinner arrangement.

Resolve age and use context when material; otherwise record assumptions. For the default children's workflow, record an age range and keep supporting details subordinate to the melody. User will add vocals: do not synthesize or recruit singers. Keep the guide melody separate and deliver an accompaniment-only export alongside the instrumental listening preview.

## Research the actual song

- Extract lyrics and credits from the approved local score. Summarize imagery, narrative, emotional trajectory, phrase repetition and opportunities for gestures. Web lyric variants do not replace local words, chords or attribution. Do not reopen unrelated rights/lyric decisions.
- Verify background through archives, libraries, scholarly sources or original publishers; record uncertainty rather than guessing authorship.
- Look for relevant recordings on original artist/publisher pages. When discussing popularity, record platform, exact recording, visible metric, retrieval date and limitations. A view count mixes distribution, age, video and musical appeal; it is not evidence that an arrangement feature caused popularity.
- Describe instrumentation, entrances, groove, transitions or dynamics only when inspected in audio/score or explicitly documented by a reliable source. Search snippets and thumbnails are not listening. Mark inaccessible audio as not auditioned. Do not invent BPM, timbres, timestamps or transcriptions.
- Separate verified song facts, empirical findings (with ages/context), observed arrangement features, and creative hypotheses. Infant studies do not automatically generalize to ages 2-8. Small or mixed evidence stays qualified.
- Translate lyrics into a small number of optional musical gestures: recurring sparkle, bell answers, rocking bass, movement cues. Avoid constant effects and competing foreground lines. No fixed ban on expressive dissonance: review its context and resolution.

## Produce an executable brief

Read [the brief contract](references/brief-contract.md). Save research.json and arrangement_brief.json per song, with evidence IDs linked to decisions, exact baseline and source hashes, changed axis, timeline, instrument mapping and verification criteria. Use scripts/compile_brief.py to validate and write PROMPT.md and execution_plan.json. The prompt is the auditable instruction to Codex; the plan is its deterministic handoff to the local adapter.

Use baseline-preserving comparisons when requested: change groove, a recurring signature, or participation cues independently, keeping tempo, harmony, melody, sample palette and room stable. Make participation optional: maintain the beat and accompaniment during response windows. Reserve space for future vocals without changing the approved melody.

## Implement and verify

Read [the configured adapter](references/barnsang-adapter.md) and validate its prerequisites before generation. Use JJazzLab for supported style/part/user-phrase operations; custom scripts may implement motifs, automation and frozen reference MIDI. Log that boundary. Never invent toolkit features or silently replace an unavailable sample.

Deliver a full listening preview, editable MIDI/project where supported, backing-only audio/MIDI for vocals, and a per-version log identifying every change and source. Keep instrument licenses/provenance. Record any native-project versus rendered-MIDI differences, including post-export automation and regenerated guitar voicings.

Verify source immutability; original melody/chord/meter/tempo; intended baseline differences; sample coverage; note pairing; playback; explicit loudness/peak targets and backing-only alignment. Check musical registers, phrase breathing, cadence, and whether added lines obscure melody or future vocals. Technical checks are not an artistic endorsement: say whether human listening and child preference testing have occurred. Preserve previous artifacts, update catalogue/listening links and durable project history.

## Executable steps

From the repository root, replace the illustrative data-relative arguments:

```text
python .agents/skills/song-arrangement-research/scripts/compile_brief.py song/arrangement_brief.json song/research.json --out compiled
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/execute_child_plans.py song/compiled/execution_plan.json --out variant_folders.json --output-root variants --scratch scratch/native
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/render_child_versions.py song/variant_folders.json --out-dir render-comparison
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/publish_experiments.py song/render-comparison/verification.json --out-dir listening
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/check_delivery.py song/render-comparison/verification.json --page-dir song/listening --out delivery_checks.json --scratch scratch/browser
```

All commands support `--config-root` when configuration is in another checkout.
`ChildExperiment.java` is compiled from source into the explicit scratch directory on each
execution. No compiled classes or external software belong in this repository.
`verification.py` preserves the source/event checks; `sample_renderer.py` provides
sample routing and rendering; `listening_page.html` is the reusable page template.
