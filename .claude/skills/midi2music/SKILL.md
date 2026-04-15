---
name: midi2music
description: Render MIDI into audio using an open-source synthesizer stack. Prefer FluidSynth with a SoundFont; optionally convert WAV output to compressed formats with ffmpeg.
allowed-tools: Read Bash Grep Glob Write
argument-hint: [midi-file-or-directory]
effort: medium
---

# MIDI to Audio

Render MIDI into actual audio files.

FluidSynth is the required first-choice tool for this skill.

## Scope

Use this skill when the input is:

- a `.mid` or `.midi` file
- a directory containing MIDI files

## Required tool

- **FluidSynth** + SoundFont (`.sf2` or `.sf3`)
- **Optional post-processing**: ffmpeg for MP3 or other compressed formats

Do not silently switch to another renderer unless the user explicitly wants a fallback.

## First step: prerequisite check

Always begin by resolving a FluidSynth executable.

Typical check:

```bash
command -v fluidsynth
```

If FluidSynth is missing:

- stop before attempting rendering
- tell the user that `fluidsynth` was not found
- ask whether they want help installing it
- only continue after the tool is available

## Input

The input path is provided as `$ARGUMENTS`.

If no argument is given:

- look first in `_build/midi/`
- otherwise search the current working directory for `.mid` and `.midi`

## Output

Write rendered audio under:

```text
_build/audio/
```

Also write render logs under:

```text
_build/audio/logs/
```

Default output should be WAV unless the user explicitly asks for another format.

Examples:

- `_build/midi/foo.mid` -> `_build/audio/foo.wav`
- `demo/bar.mid` -> `_build/audio/bar.wav`

## Required asset

This step requires a SoundFont.

If no SoundFont path is known:

- search the workspace for `.sf2` and `.sf3`
- if none exists, stop and report the blocker

Do not pretend MIDI can be turned into high-quality audio without an actual synth/sound library.

## Default render profile

Unless the user asks otherwise, use this default FluidSynth render profile:

- output format: WAV
- SoundFont: prefer `MuseScore_General_Lite.sf3` if available
- sample rate: `44100`
- gain: `0.5`
- no MIDI input: `-n`
- no interactive shell: `-i`
- fast render to file: `-F`
- explicit audio file type: `-T wav`
- dry render by default:
  - disable reverb with `-R 0`
  - disable chorus with `-C 0`

This corresponds to a command pattern like:

```bash
fluidsynth -ni -F /abs/path/output.wav -T wav -r 44100 -g 0.5 -R 0 -C 0 /abs/path/soundfont.sf3 /abs/path/input.mid
```

## Workflow

1. Resolve MIDI inputs.
2. Resolve a SoundFont.
3. Resolve a FluidSynth executable.
4. Create `_build/audio/logs/` if needed.
5. Render each MIDI file to WAV in `_build/audio/` using the default render profile unless the user asked otherwise.
6. Capture the full FluidSynth output into a per-file log under `_build/audio/logs/`.
7. If the user wants MP3 or another delivery format, convert from WAV with ffmpeg.
8. Verify that output files exist and are non-empty.
9. Read the render log and summarize whether the run succeeded cleanly or with warnings.

## Validation

Minimum validation:

- confirm the audio file exists
- report file size
- if possible, report duration and sample rate
- confirm the render log exists

## Post-conversion check

Do not stop at file existence.

After rendering, inspect both:

- the produced audio file
- the FluidSynth render log

At minimum, report:

- whether rendering succeeded
- output file path
- output file size
- duration if available
- sample rate if available
- the SoundFont used
- whether the log contains warnings or errors

If the output file exists but the log indicates a serious render failure, do not call the run successful.

If the log is clean and the audio file is present and non-empty, report success clearly.

## Failure handling

If FluidSynth is unavailable:

- say so plainly
- report the missing command
- ask whether the user wants help installing it
- do not proceed until the tool is available

If the SoundFont is missing:

- mark that as the primary blocker

## Installation help

If the user wants installation help, first identify the platform.

### Linux

Prefer one of:

- the system package if it is reasonably current
- a standard repository package for `fluidsynth`

After installation, re-check with:

```bash
command -v fluidsynth
```

### Windows

Prefer an official or standard packaged FluidSynth build.

Help the user:

- obtain a Windows build of FluidSynth
- ensure the executable is callable, or explain that they may need to run it by full path

## Final response

Report:

- input MIDI path(s)
- SoundFont used
- output audio path(s)
- log path(s)
- tool used
- target format(s)
- success or failure
- any warnings or errors seen in the logs
- any blockers or quality limitations
