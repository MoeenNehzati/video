---
name: song-arrangement-research
description: Research a song's background, approved lyrics and documented recordings, then create an evidence-linked arrangement brief and implement tailored JJazzLab/MIDI arrangements. Use for song-specific arranging and repeatable research-to-production workflows.
---

# Song arrangement research

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

Read project AGENTS.md, current context/history and user decisions. Identify the exact approved score, MIDI melody, chord timing, baseline arrangement and output directory. Preserve source hashes. Keep existing full chord accompaniment, bass movement and beat when adding motifs unless the user requests a thinner arrangement. Allocate new version names without overwriting earlier work unless revision is authorized.

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
python .agents/skills/song-arrangement-research/scripts/compile_brief.py song/arrangement_brief.json song/research.json --out song/compiled
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/execute_child_plans.py song/compiled/execution_plan.json --out song/variant_folders.json
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/render_child_versions.py song/variant_folders.json --out-dir song/render-comparison
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/publish_experiments.py song/render-comparison/verification.json --out-dir song/listening
python .agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/check_delivery.py song/render-comparison/verification.json --page-dir song/listening --out song/delivery_checks.json
```

Use new output locations; these commands refuse existing delivery directories or
reports. All support `--config-root` when configuration is in another checkout.
`ChildExperiment.java` is compiled from source into a temporary directory on each
execution. No compiled classes or external software belong in this repository.
`verification.py` preserves the source/event checks; `sample_renderer.py` provides
sample routing and rendering; `listening_page.html` is the reusable page template.
The bookkeeping ledger is separate planned work; these commands do not register it.
