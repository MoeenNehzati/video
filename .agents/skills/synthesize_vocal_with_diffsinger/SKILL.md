---
name: synthesize-vocal-with-diffsinger
description: Render reviewed vocal_events.json as a sung WAV using an externally configured Nishiren DiffSinger ONNX voicebank and explicit phonemes or a pronunciation lexicon.
allowed-tools: Read Bash Grep Glob Write
metadata:
  argument-hint: "[vocal-events-json]"
  effort: "high"
---

# Synthesize a vocal with Nishiren

This optional workflow converts [vocal events](../../../references/schemas/vocal_events.schema.json)
into Nishiren phoneme/duration/pitch inputs and runs the external voicebank's
ONNX models. It preserves the duration, embedding, acoustic and vocoder method
of the existing adapter. No model or external application is stored in Git.

## Inputs and configuration

Read resolved configuration with `env/bin/python -m bin.read_config` (Windows:
`env/Scripts/python.exe`). Set `[resources].nishiren_root` in `config.local.toml`
to the absolute directory of a complete, separately obtained voicebank. It needs
`dsdur`, `dsmain` and `dsvocoder`; optional `dspitch`/`dsvariance` model groups
must be complete if present. Install the repository's declared Python dependencies.

Every sung event needs either a nonempty `phonemes` list or an entry in the
optional `[resources].pronunciation_lexicon` JSON file. That external file maps
normalized lowercase lyric tokens to phoneme lists. Explicit tokens can be
voicebank-prefixed (`en/aa`) or unprefixed ARPABET-style (`AA1`); the adapter
normalizes stress suffixes and uses `--nishiren-lang` as the prefix. All resulting
tokens must exist in the voicebank's maps. Review pronunciation for the song's
language before rendering. There is no automatic download or demo-song lexicon.

## Python invocation

Implementation: [scripts/synthesize_vocal_with_diffsinger.py](scripts/synthesize_vocal_with_diffsinger.py).
Run from the repository root; on Windows replace the interpreter as above.
Artifact paths must be under `paths.data_root`; relative paths resolve from
that directory. `--config-root` optionally selects the configuration directory.

```bash
env/bin/python .agents/skills/synthesize_vocal_with_diffsinger/scripts/synthesize_vocal_with_diffsinger.py vocal_events.json \
  --nishiren-lang en --nishiren-style Standard \
  --out rough_vocal.wav --debug-out diffsinger_input.json --log synthesis_log.json
```

Choose the embedding, velocity, gender and inference steps deliberately; retain
the reviewed settings with the synthesis output. The WAV, debug input and log
must have distinct paths. Debug output follows the
[payload schema](references/diffsinger_input.schema.json); duration values are
frames, with sample rate and hop size recorded in metadata.

## Validation and limits

Missing resources, invalid paths, unknown pronunciation and unavailable Python
backends fail before output files are written. Inference failure is an error;
there is no placeholder-tone fallback and no advertised OpenVPI execution route.
Optional pitch/variance model omissions are reported in the synthesis log.

The existing inference method concatenates voiced syllables. It supports only
contiguous, nonslurred sung events beginning at measure 1 beat 1 in a constant
meter. Slurs, rests, blank lyrics, gaps and delayed entry are rejected before
writing outputs; extending their timing is separate work. Do not alter a reviewed
score merely to bypass this limitation.

Listen for intelligibility, pitch, timing, silence and clipping
against the approved events. This adapter is an optional existing implementation,
not a validated general-purpose singing system; do not approve output based only
on a successful ONNX call. Keep the original rough vocal if later using RVC.
