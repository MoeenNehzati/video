---
name: refine-vocal-with-rvc
description: Optionally refine a rough vocal through a separately installed RVC/SVC tool, preserving the original for comparison and reviewing timing and intelligibility.
allowed-tools: Read Bash Grep Glob Write
metadata:
  argument-hint: "[rough-vocal-wav]"
  effort: "medium"
---

# Refine a vocal with an external RVC tool

## Bookkeeping

Use [artifact-bookkeeping](../artifact-bookkeeping/SKILL.md) with the declarations
below. It owns all artifact access, including implicit tool I/O, and supplies the
execution procedure. Command examples here specify domain arguments for that
skill to execute. Local configuration:

- Inputs: rough vocal and selected model/index; settings: transpose and the
  chosen external tool's supported options; outputs: refined WAV and comparison log.
- Route: manual handoff/import of an externally supplied result; no automated
  RVC adapter is provided. Keep unknown model/production provenance explicit.

RVC converts an existing vocal's timbre. It does not create singing from symbolic
notes. Keep this optional: conversion can blur consonants, introduce artifacts
or reduce lyric intelligibility.

## Configuration and execution

This repository supplies instructions, not an RVC implementation or a local
`refine_vocal_with_rvc` executable. Install the chosen tool externally. Store its
executable argument prefix in `[tools.rvc].command` in `config.local.toml`, and
model/index paths in `[resources].rvc_model` and `[resources].rvc_index` when used.
If the installation needs its own Python, use that interpreter in the command
prefix. Never vendor the tool or models into this repository.

1. Read resolved configuration using `env/bin/python -m scripts.read_config`
   (Windows: `env/Scripts/python.exe`). Inspect the configured tool's supported
   interface; flags differ between RVC installations.
2. Identify the input WAV and required WAV/log deliverables. Validate the input is
   present and nonsilent, and check
   all required executable/model/index paths before creating any outputs.
3. For an enabled execution route, invoke the external tool using an argument list
   and checked return code,
   supplying the reviewed transpose and the resolved input, output and resource
   paths. Do not guess flags or silently use a different backend.
4. Verify the output exists, then compare duration/alignment, intelligibility,
   clipping, silence and audible artifacts with the original rough vocal.
5. Write a log beside the result containing exact inputs, resource identities,
   command/settings, output path, duration comparison and review findings.

Retain both rough and refined vocals for A/B review. A missing or unsupported
external installation is a capability gap: stop before generation and report it.
No successful conversion or quality check is implied by these instructions.
