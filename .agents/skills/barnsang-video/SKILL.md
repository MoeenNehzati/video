---
name: barnsang-video
description: Make an animated children's music video from its reviewed score and arrangement, using storyboards, consistent character pictures, continuity-chained keyframes, image-to-video clips in Google Flow, and assembly to music. Use when starting or revising a song video.
---

# Children's song video

Read the project's accepted story, arrangement, visual choices and review records
before continuing. Keep decisions and generated files under `paths.data_root`;
never restart accepted work merely because this is a new session. The user supplies
taste and final approval. [Adoption notes](../../../docs/skill-adoption.md) describe
execution boundaries; [artifact contracts](../../../docs/artifact-contracts.md)
describe the pending ledger integration.

Use the repo environment's Python (`env/bin/python` on POSIX,
`env/Scripts/python.exe` on Windows). Commands below use `python` for that interpreter.
Run `python -m scripts.read_config`; paths passed to these scripts are absolute within,
or relative to, its resolved `paths.data_root`. Default configuration loading works
from any current directory; optional `--config-root` selects a repository config.
Configure external commands through `[tools.ffmpeg].command` and
`[tools.ffprobe].command` argument lists in `config.local.toml`.

## Film methods

- Confirm the accepted lyrics, rights decisions and any additional verse before
  storyboarding. Use first editions, reference works and variant comparison when
  researching additions. Keep evidence with the song; do not carry another song's
  rights decisions into this one.
- Choose one shot per lyric line or two, timed to bars. Follow the lyric event order;
  show causes before reactions and make reactions immediate. Keep emotions consistent
  with what has happened. Use gentle, playful language appropriate for young children.
- Record the chosen look and setting in the storyboard. Use cartoon children, no
  on-screen singer, subtitles or text. Human vocals are supplied separately; the
  optional AI-vocal workflow is a separate choice.
- Preserve character identity, clothing, proportions, props, setting and lighting.
  Except at an explicit scene change or time jump, a clip's last image is the next
  clip's first image. Use natural movement, without morphing or transition effects.
- Keep a Flow handoff containing only the selected current pictures and one
  instructions file. Archive earlier revisions elsewhere in project data. Never
  change a picture under an existing filename inside an existing Flow project;
  use a new descriptive filename or a new project.

## Workflow and commands

1. Write and review the storyboard JSON described below.
2. Generate character sheets on plain backgrounds with `scripts/gen_image.py`.
   Supply the actual chosen model, quality and size; there is no fixed model default.
3. Generate keyframes **sequentially** with `scripts/gen_edit.py`. Reference the
   preceding accepted keyframe plus character sheets. Describe what stays the same
   and change only the next story action. Review each result before using it as a
   predecessor. Check anatomy, floating objects and clothing transferred between
   characters; repair defects with targeted edits.
4. Run `scripts/write_flow_instructions.py` to produce the Flow handoff. Review its
   filename-to-picture mapping before generation. The user generates each clip in
   Flow using the specified START/END images, duration, aspect ratio and chosen model.
   This remains a manual workflow; no untested video API is advertised.
5. Request targeted revisions in the same Flow project. For difficult contact or
   landings, compare several options with second-by-second actions. If necessary,
   split the moment into separate wide and close shots.
6. Before assembly, compare downloaded files by hash to avoid duplicate selections;
   inspect first/last frames and contact sheets. Flow's generated names are not proof
   of prompt or image identity. Create an explicit clip map of the accepted files.
7. Run `scripts/assemble_flow.py`. It keeps clips whole unless the reviewed clip map
   gives an end trim, applies a uniform speed per verse group, tempo-adjusts and
   offsets repeated accompaniment, and records the resulting timeline. Confirm final
   timing against the actual vocal recording. Listen and watch the assembled result;
   successful encoding does not establish quality or audiovisual alignment.

```text
python .agents/skills/barnsang-video/scripts/gen_image.py --model MODEL --quality QUALITY --size SIZE --prompt song/character-prompt.txt --output song/character.png
python .agents/skills/barnsang-video/scripts/gen_edit.py --model MODEL --quality QUALITY --size SIZE --prompt song/frame2-prompt.txt --reference song/frame1.png --reference song/character.png --output song/frame2.png
python .agents/skills/barnsang-video/scripts/write_flow_instructions.py --storyboard song/storyboard.json --output song/flow-kit/INSTRUCTIONS.txt
python .agents/skills/barnsang-video/scripts/assemble_flow.py --song-config song/assembly.json --clips song/selected-clips.json --audio song/accompaniment.wav --output song/film.mp4 --output-audio song/prepared-audio.wav --timeline song/timeline.json
```

Image scripts require `OPENAI_API_KEY`, never print it, and create an adjacent
`<output>.json` request record. Use `--input-fidelity high` for editing only when the
chosen model supports it. Validate prompts/references before paid generation. All
outputs must be new paths; keep previous versions while revising. `--clips ID ...`
on the handoff command selects particular clips for regeneration.

## Run-file contracts

Keep these JSON files with the song, not in this skill. Their file paths are relative
to `paths.data_root`, not to the JSON file's directory.

**Storyboard:** required text fields `title`, `context`, `style`, `video_model`,
`aspect_ratio`; optional `rules` list. `images` is a list of
`{id, file, description}` with unique ids and filenames. `clips` is an ordered list
of `{id, start_image, end_image, duration_s, action}` referencing image ids.
`end_image` may be null for a calm ending; a discontinuous join requires
`scene_break_after: true`. Otherwise it must equal the next clip's `start_image`.

**Clip map:** list of `{id, file}`, optionally `trim_end_s` measured from the clip's
start. Every id is unique and appears exactly once in `verse_groups`.

**Assembly settings:** `source_bpm`, `target_bpm`, `beats_per_bar`, `verse_bars`,
`interlude_bars`, `verse_groups` (ordered lists of clip ids), `width`, `height`, `fps`.
These describe repeated accompaniment: verse starts are spaced by
`(verse_bars + interlude_bars) × beats_per_bar × 60 / target_bpm` seconds. Each group
fits its interval with one common speed; the last ends with the adjusted audio.
Optional `end_trim_s` (default 0), `audio_fade_s` (2), `video_fade_in_s` (0.6),
`video_fade_out_s` (1.2), `crf` (16) and `preset` (`slow`) control finishing.
Tempo ratios outside 0.5–2 fail explicitly. The command outputs MP4, prepared WAV
and timeline JSON; it never discovers clips by old filenames or version suffixes.

For a final vocal mix or accompaniment whose structure differs from repeated verses,
review its timing and adapt the assembly contract explicitly before using it. This
adapter is not a generic music mixer. Flow availability, models, resolution and
filter behavior must be checked in the current account; historical results do not
establish current service behavior.
