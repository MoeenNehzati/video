---
name: syllabify-lyrics
description: Use when lyrics.txt needs to be parsed and syllabified into lyrics.json for downstream vocal alignment. Respects explicit hyphens and applies a heuristic syllabifier. Does not inspect or modify the score.
allowed-tools: Read Bash Grep Glob Write
metadata:
  argument-hint: "[lyrics-txt]"
  effort: "low"
---

# Skill: `syllabify_lyrics`

## Purpose

Turn `lyrics.txt` into a structured `lyrics.json` that downstream tools can align against a melody.

This step is lyrics-only. It should not inspect or modify the score.

## Inputs

```text
lyrics.txt
```

Optional config:

```json
{
  "language_hint": "English"
}
```

## Core responsibilities

1. Read lyric lines (preserve original text for each line).
2. Tokenize into words/syllables.
3. Respect explicit hyphenation in the input (e.g., `Twin-kle`).
4. If no explicit hyphens are present, apply a deterministic heuristic syllabifier.
5. Emit `lyrics.json`.

## Output

Write `lyrics.json` matching [the shared schema](../../../references/schemas/lyrics.schema.json).

## Python invocation

Run from the repository root with `env/bin/python` (Windows:
`env/Scripts/python.exe`). Resolve `paths.data_root` through `scripts.read_config`.
Artifact arguments are absolute paths under that root or paths relative to it;
the script validates them and never infers an output from the working directory.
`--config-root` optionally selects a directory containing the TOML configuration.


Implementation: [scripts/syllabify_lyrics.py](scripts/syllabify_lyrics.py).

```bash
env/bin/python .agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py lyrics.txt --language English --out lyrics.json
```

## Failure modes

Warn (do not fail) if:

- the file is empty
- a line contains no usable tokens after cleanup
- syllabification is heuristic and may be inaccurate for the language
