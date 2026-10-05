---
name: analyze-music
description: Use when an arranged MusicXML score needs to be parsed into music_analysis.json — extracting tempo, meter, key, parts, phrases, melody candidates, and harmony — for downstream vocal planning. Does not read lyrics or alter the score.
allowed-tools: Read Bash Grep Glob Write
metadata:
  argument-hint: "[musicxml-file]"
  effort: "medium"
---

# Skill 1: `analyze_music`

## Purpose

Turn `arranged_music.xml` into a compact musical representation that an LLM can reason over without reading raw MusicXML.

This skill is music-analysis-only. It should not read lyrics and should not alter the score.

## Inputs

```text
arranged_music.xml
```

Use `--tempo-bpm` for an explicit tempo override.

## Tools

### music21

Use `music21` to:

- parse MusicXML
- list parts and instruments
- extract measures, notes, rests, voices, and durations
- infer key and meter
- read tempo markings
- chordify the arrangement to infer harmonic context
- find candidate melody lines
- compute ranges and singability features

## Core responsibilities

1. Parse the score.
2. Extract global metadata: tempo, meter, key, measure count.
3. Extract part-level metadata: instrument names, ranges, density, likely role.
4. Identify melody candidates.
5. Estimate phrase boundaries.
6. Infer harmonic context, preferably as chord symbols or roman numerals.
7. Emit `music_analysis.json`.

## Output

Write `music_analysis.json` matching [the shared schema](../../../references/schemas/music_analysis.schema.json).

Example:

```json
{
  "score": {
    "tempo_bpm": 96,
    "meter": "4/4",
    "key": "C major",
    "measure_count": 16,
    "parts": [
      {
        "id": "P1",
        "name": "piano",
        "range": ["C3", "G5"],
        "role_guess": "accompaniment",
        "density_score": 0.72
      },
      {
        "id": "P2",
        "name": "flute",
        "range": ["C4", "A5"],
        "role_guess": "melody_candidate",
        "density_score": 0.31
      }
    ],
    "phrases": [
      {
        "id": "A1",
        "measures": [1, 4],
        "cadence_guess": "half cadence",
        "melody_candidate_part": "P2"
      }
    ],
    "harmony": [
      {
        "measure": 1,
        "beat": 1.0,
        "chord_guess": "I"
      }
    ],
    "melody_candidates": [
      {
        "source_part": "P2",
        "measures": [1, 8],
        "note_count": 32,
        "singability_score": 0.86,
        "range": ["C4", "G5"]
      }
    ]
  },
  "warnings": []
}
```

## Why this output is useful

The next skill needs to decide where and how to sing. It needs compact facts:

- which part probably carries the tune
- where phrases start and end
- whether the melody fits a singable range
- how many melody notes are available
- whether accompaniment conflicts with the vocal register

## Python invocation

Run from the repository root with `env/bin/python` (Windows:
`env/Scripts/python.exe`). Resolve `paths.data_root` through `bin.read_config`.
Artifact arguments are absolute paths under that root or paths relative to it;
the script validates them and never infers an output from the working directory.
`--config-root` optionally selects a directory containing the TOML configuration.


Implementation: [scripts/analyze_music.py](scripts/analyze_music.py).

```bash
env/bin/python .agents/skills/analyze_music/scripts/analyze_music.py arranged_music.xml --out music_analysis.json
```

## Failure modes

The CLI exits nonzero on parse/configuration failures. Review the returned warnings:

- MusicXML cannot be parsed
- no usable note material is found
- tempo is missing (the analysis helper uses its documented default)

If key, chords, or phrases are uncertain, emit warnings instead of failing.
